"""Payroll computation, approval and disbursement."""

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.tests.factories import build_branch, build_staff, build_user
from apps.finance.models import PaymentMethod
from apps.finance.services import trial_balance
from apps.payroll.models import (
    EmployeeSalary,
    PayrollPeriod,
    PayrollRun,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
)
from apps.payroll.services import approve_payroll_run, compute_payslip, pay_salary, process_payroll

MONTH = dt.date(2026, 6, 1)


class PayrollTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="payroll_officer")
        self.staff = build_staff(self.fixture, salary=Decimal("50000.00"))

        self.structure = SalaryStructure.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Teacher Grade 1",
            basic_salary=Decimal("50000.00"),
        )
        housing = SalaryComponent.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Housing",
            code="HRA",
            component_type=SalaryComponent.ComponentType.EARNING,
            calculation_type=SalaryComponent.CalculationType.PERCENT_OF_BASIC,
        )
        tax = SalaryComponent.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Income Tax",
            code="TAX",
            component_type=SalaryComponent.ComponentType.DEDUCTION,
        )
        SalaryStructureLine.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            structure=self.structure,
            component=housing,
            value=Decimal("20.00"),
            sequence=1,
        )
        SalaryStructureLine.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            structure=self.structure,
            component=tax,
            value=Decimal("2500.00"),
            sequence=2,
        )

        self.salary = EmployeeSalary.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            staff=self.staff,
            structure=self.structure,
            basic_salary=Decimal("50000.00"),
            effective_from=MONTH,
        )
        self.period = PayrollPeriod.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="June 2026",
            month=MONTH,
            start_date=MONTH,
            end_date=dt.date(2026, 6, 30),
        )

    def test_payslip_arithmetic_uses_decimals(self):
        figures = compute_payslip(self.salary)
        self.assertEqual(figures["basic_salary"], Decimal("50000.00"))
        self.assertEqual(figures["total_allowances"], Decimal("10000.00"))
        self.assertEqual(figures["total_deductions"], Decimal("2500.00"))
        self.assertEqual(figures["gross_salary"], Decimal("60000.00"))
        self.assertEqual(figures["net_salary"], Decimal("57500.00"))
        for value in figures.values():
            self.assertNotIsInstance(value, float)

    def test_deductions_greater_than_earnings_are_refused(self):
        SalaryStructureLine.objects.filter(
            structure=self.structure, component__code="TAX"
        ).update(value=Decimal("999999.00"))
        with self.assertRaises(ValidationError):
            compute_payslip(self.salary)

    def test_a_run_creates_one_payslip_per_active_salary(self):
        run = process_payroll(period=self.period, actor=self.actor)
        self.assertEqual(run.employee_count, 1)
        self.assertEqual(run.total_net, Decimal("57500.00"))
        self.assertEqual(run.status, PayrollRun.Status.DRAFT)

    def test_approval_posts_a_balanced_ledger_entry(self):
        run = process_payroll(period=self.period, actor=self.actor)
        approve_payroll_run(run=run, actor=self.actor)

        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRun.Status.APPROVED)
        self.assertIsNotNone(run.journal_entry)
        self.assertEqual(
            run.journal_entry.total_debit, run.journal_entry.total_credit
        )
        self.assertTrue(trial_balance(self.actor, self.fixture.branch)["is_balanced"])

    def test_an_unapproved_run_cannot_be_paid(self):
        run = process_payroll(period=self.period, actor=self.actor)
        method = PaymentMethod.objects.get(
            branch=self.fixture.branch, method_type="cash"
        )
        with self.assertRaises(ValidationError):
            pay_salary(
                payroll_item=run.items.first(),
                payment_method=method,
                actor=self.actor,
            )

    def test_paying_every_payslip_closes_the_run(self):
        run = process_payroll(period=self.period, actor=self.actor)
        approve_payroll_run(run=run, actor=self.actor)
        method = PaymentMethod.objects.get(
            branch=self.fixture.branch, method_type="cash"
        )
        payment = pay_salary(
            payroll_item=run.items.first(),
            payment_method=method,
            payment_date=MONTH,
            actor=self.actor,
        )
        run.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("57500.00"))
        self.assertEqual(run.status, PayrollRun.Status.PAID)
        self.assertTrue(trial_balance(self.actor, self.fixture.branch)["is_balanced"])

    def test_paying_more_than_the_net_salary_is_refused(self):
        run = process_payroll(period=self.period, actor=self.actor)
        approve_payroll_run(run=run, actor=self.actor)
        method = PaymentMethod.objects.get(
            branch=self.fixture.branch, method_type="cash"
        )
        with self.assertRaises(ValidationError):
            pay_salary(
                payroll_item=run.items.first(),
                payment_method=method,
                amount=Decimal("99999.00"),
                actor=self.actor,
            )

    def test_a_closed_period_cannot_be_processed(self):
        self.period.status = PayrollPeriod.Status.CLOSED
        self.period.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            process_payroll(period=self.period, actor=self.actor)
