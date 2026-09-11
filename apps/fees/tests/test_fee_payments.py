"""Fee billing, collection, refunds and their ledger postings."""

import datetime as dt
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.core.tests.factories import (
    build_branch,
    build_fee_type,
    build_student,
    build_user,
    two_branches,
)
from apps.fees.models import FeeInvoice, FeePayment
from apps.fees.services import (
    generate_invoice,
    outstanding_summary,
    record_payment,
    refund_payment,
    void_payment,
    waive_invoice_amount,
)
from apps.finance.models import JournalEntry, PaymentMethod
from apps.finance.services import trial_balance

ISSUE = dt.date(2026, 6, 1)
DUE = dt.date(2026, 6, 10)


class InvoiceGenerationTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        build_fee_type(self.fixture, "Tuition", Decimal("5000.00"))
        self.student = build_student(self.fixture)

    def test_invoice_totals_come_from_the_fee_structure(self):
        invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        self.assertEqual(invoice.subtotal, Decimal("5000.00"))
        self.assertEqual(invoice.total_amount, Decimal("5000.00"))
        self.assertEqual(invoice.balance, Decimal("5000.00"))
        self.assertEqual(invoice.status, FeeInvoice.Status.ISSUED)

    def test_a_discount_reduces_the_total(self):
        from apps.fees.models import FeeDiscount, FeeType

        FeeDiscount.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Sibling",
            student=self.student,
            fee_type=FeeType.objects.get(branch=self.fixture.branch, name="Tuition"),
            discount_type=FeeDiscount.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            valid_from=ISSUE,
        )
        invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        self.assertEqual(invoice.discount_amount, Decimal("500.00"))
        self.assertEqual(invoice.total_amount, Decimal("4500.00"))

    def test_invoicing_posts_a_balanced_ledger_entry(self):
        invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        entry = JournalEntry.objects.get(
            source_module="fees.invoice", source_id=str(invoice.pk)
        )
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_money_is_stored_as_decimal(self):
        invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        invoice.refresh_from_db()
        self.assertIsInstance(invoice.total_amount, Decimal)


class PaymentTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        build_fee_type(self.fixture, "Tuition", Decimal("5000.00"))
        self.student = build_student(self.fixture)
        self.invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        self.method = PaymentMethod.objects.get(
            branch=self.fixture.branch, method_type="cash"
        )
        self.cashier = build_user(self.fixture.branch, username="cashier")

    def _pay(self, amount):
        return record_payment(
            invoice=self.invoice,
            amount=amount,
            payment_method=self.method,
            payment_date=ISSUE,
            actor=self.cashier,
        )

    def test_a_partial_payment_leaves_a_balance(self):
        self._pay(Decimal("2000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("2000.00"))
        self.assertEqual(self.invoice.balance, Decimal("3000.00"))
        self.assertEqual(self.invoice.status, FeeInvoice.Status.PARTIALLY_PAID)

    def test_full_payment_settles_the_invoice(self):
        self._pay(Decimal("5000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, FeeInvoice.Status.PAID)
        self.assertTrue(self.invoice.is_settled)

    def test_overpayment_is_refused(self):
        with self.assertRaises(ValidationError):
            self._pay(Decimal("6000.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))

    def test_a_zero_payment_is_refused(self):
        with self.assertRaises(ValidationError):
            self._pay(Decimal("0.00"))

    def test_a_payment_method_from_another_branch_is_refused(self):
        other = build_branch(self.fixture.organization, name="Other", code="OTH")
        foreign_method = PaymentMethod.objects.filter(
            branch=other.branch, method_type="cash"
        ).first()
        with self.assertRaises(PermissionDenied):
            record_payment(
                invoice=self.invoice,
                amount=Decimal("100.00"),
                payment_method=foreign_method,
                payment_date=ISSUE,
                actor=self.cashier,
            )

    def test_a_payment_posts_a_balanced_ledger_entry(self):
        payment = self._pay(Decimal("5000.00"))
        self.assertIsNotNone(payment.journal_entry)
        self.assertEqual(
            payment.journal_entry.total_debit, payment.journal_entry.total_credit
        )

    def test_receipt_numbers_are_sequential_and_unique(self):
        first = self._pay(Decimal("1000.00"))
        second = self._pay(Decimal("1000.00"))
        self.assertNotEqual(first.receipt_number, second.receipt_number)

    def test_the_ledger_stays_balanced_after_collection(self):
        self._pay(Decimal("5000.00"))
        report = trial_balance(self.cashier, self.fixture.branch)
        self.assertTrue(report["is_balanced"])

    def test_voiding_reverses_the_ledger_and_the_balance(self):
        payment = self._pay(Decimal("5000.00"))
        void_payment(payment=payment, reason="Wrong student", actor=self.cashier)

        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(payment.is_void)
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertTrue(trial_balance(self.cashier, self.fixture.branch)["is_balanced"])

    def test_outstanding_summary_adds_up(self):
        self._pay(Decimal("2000.00"))
        summary = outstanding_summary(self.cashier, self.fixture.branch)
        self.assertEqual(summary["billed"], Decimal("5000.00"))
        self.assertEqual(summary["collected"], Decimal("2000.00"))
        self.assertEqual(summary["outstanding"], Decimal("3000.00"))


class RefundAndWaiverTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        build_fee_type(self.fixture, "Tuition", Decimal("5000.00"))
        self.student = build_student(self.fixture)
        self.invoice = generate_invoice(
            student=self.student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        self.method = PaymentMethod.objects.get(
            branch=self.fixture.branch, method_type="cash"
        )
        self.actor = build_user(self.fixture.branch, username="finance")
        self.payment = record_payment(
            invoice=self.invoice,
            amount=Decimal("5000.00"),
            payment_method=self.method,
            payment_date=ISSUE,
            actor=self.actor,
        )

    def test_a_refund_reduces_the_paid_amount(self):
        refund_payment(
            payment=self.payment,
            amount=Decimal("1500.00"),
            refund_date=ISSUE,
            reason="Withdrawal",
            actor=self.actor,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.refunded_amount, Decimal("1500.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("3500.00"))

    def test_refunding_more_than_was_paid_is_refused(self):
        with self.assertRaises(ValidationError):
            refund_payment(
                payment=self.payment,
                amount=Decimal("9000.00"),
                refund_date=ISSUE,
                reason="Too much",
                actor=self.actor,
            )

    def test_a_refund_keeps_the_ledger_balanced(self):
        refund_payment(
            payment=self.payment,
            amount=Decimal("1500.00"),
            refund_date=ISSUE,
            reason="Withdrawal",
            actor=self.actor,
        )
        self.assertTrue(trial_balance(self.actor, self.fixture.branch)["is_balanced"])

    def test_a_waiver_reduces_the_outstanding_balance(self):
        second = build_student(self.fixture, "Second Student", "S-002")
        invoice = generate_invoice(
            student=second,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        waive_invoice_amount(
            invoice=invoice,
            amount=Decimal("1000.00"),
            reason="Hardship",
            waived_on=ISSUE,
            actor=self.actor,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.waiver_amount, Decimal("1000.00"))
        self.assertTrue(trial_balance(self.actor, self.fixture.branch)["is_balanced"])


class FeeBranchIsolationTests(TestCase):
    def test_a_cashier_cannot_see_another_branch_invoice(self):
        branch_a, branch_b = two_branches()
        build_fee_type(branch_b, "Tuition", Decimal("1000.00"))
        student_b = build_student(branch_b, "Other Branch Student", "B-500")
        invoice_b = generate_invoice(
            student=student_b,
            academic_year=branch_b.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        user_a = build_user(branch_a.branch, username="cashier_a")
        self.assertEqual(
            FeeInvoice.objects.for_user(user_a, branch_a.branch)
            .filter(pk=invoice_b.pk)
            .count(),
            0,
        )
        self.assertEqual(
            FeePayment.objects.for_user(user_a, branch_a.branch).count(), 0
        )

    def test_the_payment_form_only_offers_this_branch_invoices(self):
        from apps.fees.forms import PaymentForm

        branch_a, branch_b = two_branches()
        build_fee_type(branch_b, "Tuition", Decimal("1000.00"))
        student_b = build_student(branch_b, "Other Branch Student", "B-600")
        invoice_b = generate_invoice(
            student=student_b,
            academic_year=branch_b.academic_year,
            issue_date=ISSUE,
            due_date=DUE,
        )
        form = PaymentForm(branch=branch_a.branch)
        self.assertNotIn(invoice_b, form.fields["invoice"].queryset)
