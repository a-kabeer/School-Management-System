"""Double-entry guarantees."""

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.core.tests.factories import build_branch, build_user, two_branches
from apps.finance.models import Account, JournalEntry, Transaction
from apps.finance.services import (
    CODE_CASH,
    CODE_TUITION_INCOME,
    close_fiscal_period,
    get_account,
    income_statement,
    post_journal_entry,
    reverse_journal_entry,
    trial_balance,
)

DATE = dt.date(2026, 6, 1)


class JournalPostingTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="accountant")
        self.cash = get_account(self.fixture.branch, CODE_CASH)
        self.income = get_account(self.fixture.branch, CODE_TUITION_INCOME)

    def test_a_balanced_entry_posts(self):
        entry = post_journal_entry(
            branch=self.fixture.branch,
            date=DATE,
            lines=[
                {"account": self.cash, "debit": Decimal("1000.00")},
                {"account": self.income, "credit": Decimal("1000.00")},
            ],
            actor=self.actor,
        )
        self.assertEqual(entry.status, JournalEntry.Status.POSTED)
        self.assertEqual(entry.total_debit, entry.total_credit)
        self.assertEqual(entry.lines.count(), 2)

    def test_an_unbalanced_entry_is_refused(self):
        with self.assertRaises(ValidationError):
            post_journal_entry(
                branch=self.fixture.branch,
                date=DATE,
                lines=[
                    {"account": self.cash, "debit": Decimal("1000.00")},
                    {"account": self.income, "credit": Decimal("900.00")},
                ],
                actor=self.actor,
            )
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_a_line_cannot_be_both_debit_and_credit(self):
        with self.assertRaises(ValidationError):
            post_journal_entry(
                branch=self.fixture.branch,
                date=DATE,
                lines=[
                    {
                        "account": self.cash,
                        "debit": Decimal("100.00"),
                        "credit": Decimal("100.00"),
                    }
                ],
                actor=self.actor,
            )

    def test_an_account_from_another_branch_is_refused(self):
        other = build_branch(self.fixture.organization, name="Other", code="OTH")
        foreign = get_account(other.branch, CODE_CASH)
        with self.assertRaises(ValidationError):
            post_journal_entry(
                branch=self.fixture.branch,
                date=DATE,
                lines=[
                    {"account": foreign, "debit": Decimal("100.00")},
                    {"account": self.income, "credit": Decimal("100.00")},
                ],
                actor=self.actor,
            )

    def test_a_date_outside_any_fiscal_period_is_refused(self):
        with self.assertRaises(ValidationError):
            post_journal_entry(
                branch=self.fixture.branch,
                date=dt.date(2099, 1, 1),
                lines=[
                    {"account": self.cash, "debit": Decimal("100.00")},
                    {"account": self.income, "credit": Decimal("100.00")},
                ],
                actor=self.actor,
            )

    def test_a_closed_period_refuses_new_entries(self):
        from apps.finance.models import FiscalPeriod

        period = FiscalPeriod.objects.get(branch=self.fixture.branch)
        close_fiscal_period(period=period, actor=self.actor)
        with self.assertRaises(ValidationError):
            post_journal_entry(
                branch=self.fixture.branch,
                date=DATE,
                lines=[
                    {"account": self.cash, "debit": Decimal("100.00")},
                    {"account": self.income, "credit": Decimal("100.00")},
                ],
                actor=self.actor,
            )

    def test_a_reversal_mirrors_the_original(self):
        entry = post_journal_entry(
            branch=self.fixture.branch,
            date=DATE,
            lines=[
                {"account": self.cash, "debit": Decimal("750.00")},
                {"account": self.income, "credit": Decimal("750.00")},
            ],
            actor=self.actor,
        )
        reversal = reverse_journal_entry(entry=entry, date=DATE, actor=self.actor)

        entry.refresh_from_db()
        self.assertEqual(entry.status, JournalEntry.Status.REVERSED)
        self.assertEqual(reversal.reversal_of_id, entry.pk)

        cash_lines = reversal.lines.filter(account=self.cash)
        self.assertEqual(cash_lines.first().credit, Decimal("750.00"))
        self.assertTrue(trial_balance(self.actor, self.fixture.branch)["is_balanced"])

    def test_an_entry_cannot_be_reversed_twice(self):
        entry = post_journal_entry(
            branch=self.fixture.branch,
            date=DATE,
            lines=[
                {"account": self.cash, "debit": Decimal("10.00")},
                {"account": self.income, "credit": Decimal("10.00")},
            ],
            actor=self.actor,
        )
        reverse_journal_entry(entry=entry, date=DATE, actor=self.actor)
        entry.refresh_from_db()
        with self.assertRaises(ValidationError):
            reverse_journal_entry(entry=entry, date=DATE, actor=self.actor)

    def test_the_database_refuses_a_two_sided_line(self):
        entry = post_journal_entry(
            branch=self.fixture.branch,
            date=DATE,
            lines=[
                {"account": self.cash, "debit": Decimal("10.00")},
                {"account": self.income, "credit": Decimal("10.00")},
            ],
            actor=self.actor,
        )
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                journal_entry=entry,
                account=self.cash,
                debit=Decimal("5.00"),
                credit=Decimal("5.00"),
            )


class ReportingTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="reader")
        post_journal_entry(
            branch=self.fixture.branch,
            date=DATE,
            lines=[
                {
                    "account": get_account(self.fixture.branch, CODE_CASH),
                    "debit": Decimal("3000.00"),
                },
                {
                    "account": get_account(self.fixture.branch, CODE_TUITION_INCOME),
                    "credit": Decimal("3000.00"),
                },
            ],
            actor=self.actor,
        )

    def test_the_trial_balance_balances(self):
        report = trial_balance(self.actor, self.fixture.branch)
        self.assertTrue(report["is_balanced"])
        self.assertEqual(report["total_debit"], Decimal("3000.00"))
        self.assertEqual(report["total_credit"], Decimal("3000.00"))

    def test_the_income_statement_reports_the_surplus(self):
        statement = income_statement(self.actor, self.fixture.branch)
        self.assertEqual(statement["income_total"], Decimal("3000.00"))
        self.assertEqual(statement["surplus"], Decimal("3000.00"))

    def test_another_branch_ledger_is_invisible(self):
        branch_a, branch_b = two_branches()
        actor_a = build_user(branch_a.branch, username="branch_a_accountant")
        post_journal_entry(
            branch=branch_b.branch,
            date=DATE,
            lines=[
                {
                    "account": get_account(branch_b.branch, CODE_CASH),
                    "debit": Decimal("999.00"),
                },
                {
                    "account": get_account(branch_b.branch, CODE_TUITION_INCOME),
                    "credit": Decimal("999.00"),
                },
            ],
        )
        report = trial_balance(actor_a, branch_a.branch)
        self.assertEqual(report["total_debit"], Decimal("0.00"))
        self.assertEqual(
            Account.objects.for_user(actor_a, branch_a.branch)
            .filter(branch=branch_b.branch)
            .count(),
            0,
        )
