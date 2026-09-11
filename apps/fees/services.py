"""Fee service layer.

Collecting money touches three things at once: the payment row, the invoice
balance, and the ledger. All three move inside one transaction, and the
invoice is locked with ``select_for_update`` so two cashiers taking payment
for the same student cannot both read a stale balance.
"""

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity, snapshot
from apps.core.utils import money, next_sequence_number
from apps.finance.models import Journal
from apps.finance.services import (
    CODE_FEE_DISCOUNT,
    CODE_RECEIVABLE,
    get_account,
    post_journal_entry,
    reverse_journal_entry,
)

from .models import (
    FeeDiscount,
    FeeInvoice,
    FeeInvoiceItem,
    FeePayment,
    FeeRefund,
    FeeStructure,
    FeeType,
    FeeWaiver,
    StudentFee,
)

ZERO = Decimal("0.00")


# --------------------------------------------------------------------------
# Numbering
# --------------------------------------------------------------------------
def next_invoice_number(branch):
    return next_sequence_number(
        FeeInvoice.objects.filter(branch=branch),
        "invoice_number",
        prefix=f"INV-{branch.code.upper()}-",
        width=6,
    )


def next_receipt_number(branch):
    return next_sequence_number(
        FeePayment.objects.filter(branch=branch),
        "receipt_number",
        prefix=f"RCP-{branch.code.upper()}-",
        width=6,
    )


def next_refund_number(branch):
    return next_sequence_number(
        FeeRefund.objects.filter(branch=branch),
        "refund_number",
        prefix=f"REF-{branch.code.upper()}-",
        width=6,
    )


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------
def applicable_charges(student, academic_year, on_date=None):
    """What this student should be billed: class structure plus overrides.

    A per-student :class:`StudentFee` replaces the class amount for that fee
    type rather than adding to it, which is what "override" has to mean for
    the totals to make sense.
    """
    on_date = on_date or timezone.localdate()
    enrollment = student.enrollments.filter(is_current=True).first()
    charges = {}

    if enrollment is not None:
        structures = FeeStructure.objects.filter(
            branch=student.branch,
            academic_year=academic_year,
            school_class=enrollment.school_class,
            is_active=True,
        ).select_related("fee_type")
        for structure in structures:
            charges[structure.fee_type_id] = {
                "fee_type": structure.fee_type,
                "amount": money(structure.amount),
            }

    overrides = StudentFee.objects.filter(
        student=student, academic_year=academic_year, is_active=True
    ).select_related("fee_type")
    for override in overrides:
        if override.effective_from > on_date:
            continue
        if override.effective_to and override.effective_to < on_date:
            continue
        charges[override.fee_type_id] = {
            "fee_type": override.fee_type,
            "amount": money(override.amount),
        }

    return list(charges.values())


def discount_for(student, fee_type, amount, on_date=None):
    """Concession to apply to one line, as a 2dp Decimal."""
    on_date = on_date or timezone.localdate()
    discounts = FeeDiscount.objects.filter(
        student=student, is_active=True, valid_from__lte=on_date
    ).filter(fee_type__isnull=True) | FeeDiscount.objects.filter(
        student=student, is_active=True, valid_from__lte=on_date, fee_type=fee_type
    )

    total = ZERO
    for discount in discounts.distinct():
        if discount.valid_to and discount.valid_to < on_date:
            continue
        if discount.discount_type == FeeDiscount.DiscountType.PERCENTAGE:
            total += money(amount * discount.value / Decimal("100"))
        else:
            total += money(discount.value)
    return min(money(total), money(amount))


# --------------------------------------------------------------------------
# Invoicing
# --------------------------------------------------------------------------
@transaction.atomic
def generate_invoice(
    *,
    student,
    academic_year,
    issue_date,
    due_date,
    term=None,
    period_month=None,
    fee_types=None,
    actor=None,
    request=None,
):
    """Build one invoice from the student's applicable charges."""
    charges = applicable_charges(student, academic_year, issue_date)
    if fee_types is not None:
        wanted = {ft.pk for ft in fee_types}
        charges = [c for c in charges if c["fee_type"].pk in wanted]
    if not charges:
        raise ValidationError(_("There is nothing to bill for this student."))

    invoice = FeeInvoice.objects.create(
        branch=student.branch,
        organization=student.organization,
        invoice_number=next_invoice_number(student.branch),
        student=student,
        academic_year=academic_year,
        term=term,
        period_month=period_month,
        issue_date=issue_date,
        due_date=due_date,
        status=FeeInvoice.Status.ISSUED,
        created_by=actor,
    )

    subtotal = ZERO
    discount_total = ZERO
    for charge in charges:
        amount = money(charge["amount"])
        discount = discount_for(student, charge["fee_type"], amount, issue_date)
        FeeInvoiceItem.objects.create(
            branch=invoice.branch,
            organization=invoice.organization,
            invoice=invoice,
            fee_type=charge["fee_type"],
            description=charge["fee_type"].name,
            quantity=1,
            unit_amount=amount,
            discount_amount=discount,
        )
        subtotal += amount
        discount_total += discount

    invoice.subtotal = money(subtotal)
    invoice.discount_amount = money(discount_total)
    invoice.total_amount = money(subtotal - discount_total)
    invoice.save(
        update_fields=["subtotal", "discount_amount", "total_amount", "updated_at"]
    )

    _post_invoice_to_ledger(invoice, actor=actor, request=request)

    log_activity(
        action="create",
        request=request,
        user=actor,
        instance=invoice,
        new_values=snapshot(invoice),
        metadata={"event": "invoice_generated"},
    )
    return invoice


def _post_invoice_to_ledger(invoice, *, actor=None, request=None):
    """Debit receivable, credit each fee type's income account."""
    if invoice.total_amount <= ZERO:
        return None

    receivable = get_account(invoice.branch, CODE_RECEIVABLE)
    lines = [
        {
            "account": receivable,
            "debit": invoice.total_amount,
            "description": f"{invoice.invoice_number} — {invoice.student.full_name}",
        }
    ]

    for item in invoice.items.select_related("fee_type__income_account"):
        income = item.fee_type.income_account
        if income is None:
            from apps.finance.services import CODE_TUITION_INCOME

            income = get_account(invoice.branch, CODE_TUITION_INCOME)
        net = money(item.line_total)
        if net <= ZERO:
            continue
        lines.append(
            {"account": income, "credit": net, "description": item.fee_type.name}
        )

    if invoice.discount_amount > ZERO:
        # A concession is an expense of the school, not a missing receivable.
        discount_account = get_account(invoice.branch, CODE_FEE_DISCOUNT)
        lines.append(
            {
                "account": discount_account,
                "debit": invoice.discount_amount,
                "description": str(_("Fee concession")),
            }
        )
        lines.append(
            {
                "account": receivable,
                "credit": invoice.discount_amount,
                "description": str(_("Fee concession")),
            }
        )

    return post_journal_entry(
        branch=invoice.branch,
        date=invoice.issue_date,
        lines=lines,
        journal_type=Journal.JournalType.GENERAL,
        description=f"{_('Fee invoice')} {invoice.invoice_number}",
        reference=invoice.invoice_number,
        source_module="fees.invoice",
        source_id=invoice.pk,
        actor=actor,
        request=request,
    )


@transaction.atomic
def generate_invoices_for_class(
    *,
    branch,
    academic_year,
    school_class,
    issue_date,
    due_date,
    period_month=None,
    term=None,
    actor=None,
    request=None,
):
    """Bill a whole class, skipping anyone already invoiced for the period."""
    from apps.students.models import Student

    students = Student.objects.filter(
        branch=branch,
        status=Student.Status.ACTIVE,
        enrollments__school_class=school_class,
        enrollments__is_current=True,
    ).distinct()

    created, skipped = [], []
    for student in students:
        if period_month and FeeInvoice.objects.filter(
            student=student, academic_year=academic_year, period_month=period_month
        ).exists():
            skipped.append(student)
            continue
        try:
            created.append(
                generate_invoice(
                    student=student,
                    academic_year=academic_year,
                    issue_date=issue_date,
                    due_date=due_date,
                    term=term,
                    period_month=period_month,
                    actor=actor,
                    request=request,
                )
            )
        except ValidationError:
            skipped.append(student)
    return created, skipped


def _refresh_invoice_status(invoice):
    paid = invoice.payments.filter(is_void=False).aggregate(total=Sum("amount"))[
        "total"
    ]
    refunded = FeeRefund.objects.filter(payment__invoice=invoice).aggregate(
        total=Sum("amount")
    )["total"]
    waived = invoice.waivers.aggregate(total=Sum("amount"))["total"]

    invoice.paid_amount = money(money(paid) - money(refunded))
    invoice.refunded_amount = money(refunded)
    invoice.waiver_amount = money(waived)

    outstanding = invoice.total_amount - invoice.paid_amount - invoice.waiver_amount
    if invoice.status != FeeInvoice.Status.CANCELLED:
        if outstanding <= ZERO:
            invoice.status = FeeInvoice.Status.PAID
        elif invoice.paid_amount > ZERO:
            invoice.status = FeeInvoice.Status.PARTIALLY_PAID
        elif invoice.due_date < timezone.localdate():
            invoice.status = FeeInvoice.Status.OVERDUE
        else:
            invoice.status = FeeInvoice.Status.ISSUED

    invoice.save(
        update_fields=[
            "paid_amount",
            "refunded_amount",
            "waiver_amount",
            "status",
            "updated_at",
        ]
    )
    return invoice


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------
@transaction.atomic
def record_payment(
    *,
    invoice,
    amount,
    payment_method,
    payment_date,
    reference="",
    notes="",
    actor=None,
    request=None,
):
    """Take money against an invoice and post it to the ledger."""
    # Lock the invoice for the rest of the transaction so a concurrent
    # payment cannot overpay it from a stale balance.
    invoice = FeeInvoice.objects.select_for_update().get(pk=invoice.pk)

    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({"amount": _("Amount must be greater than zero.")})
    if invoice.status == FeeInvoice.Status.CANCELLED:
        raise ValidationError(_("This invoice has been cancelled."))
    if payment_method.branch_id != invoice.branch_id:
        raise PermissionDenied(_("That payment method belongs to a different branch."))

    outstanding = money(
        invoice.total_amount - invoice.paid_amount - invoice.waiver_amount
    )
    if amount > outstanding:
        raise ValidationError(
            {
                "amount": _("That is more than the outstanding balance of %(bal)s.")
                % {"bal": outstanding}
            }
        )
    if payment_method.requires_reference and not reference:
        raise ValidationError({"reference": _("A reference is required for this method.")})

    payment = FeePayment.objects.create(
        branch=invoice.branch,
        organization=invoice.organization,
        receipt_number=next_receipt_number(invoice.branch),
        invoice=invoice,
        student=invoice.student,
        payment_method=payment_method,
        amount=amount,
        payment_date=payment_date,
        reference=reference,
        notes=notes,
        received_by=actor,
    )

    entry = post_journal_entry(
        branch=invoice.branch,
        date=payment_date,
        lines=[
            {
                "account": payment_method.account,
                "debit": amount,
                "description": f"{payment.receipt_number} — {invoice.student.full_name}",
            },
            {
                "account": get_account(invoice.branch, CODE_RECEIVABLE),
                "credit": amount,
                "description": invoice.invoice_number,
            },
        ],
        journal_type=Journal.JournalType.CASH_RECEIPT,
        description=f"{_('Fee payment')} {payment.receipt_number}",
        reference=payment.receipt_number,
        source_module="fees.payment",
        source_id=payment.pk,
        actor=actor,
        request=request,
    )
    payment.journal_entry = entry
    payment.save(update_fields=["journal_entry", "updated_at"])

    _refresh_invoice_status(invoice)

    from apps.notifications.services import notify_payment_received

    notify_payment_received(payment=payment, actor=actor)

    log_activity(
        action="payment",
        request=request,
        user=actor,
        instance=payment,
        new_values={
            "receipt": payment.receipt_number,
            "amount": str(amount),
            "invoice": invoice.invoice_number,
            "method": payment_method.name,
        },
    )
    return payment


@transaction.atomic
def void_payment(*, payment, reason, actor=None, request=None):
    """Cancel a payment and reverse its ledger entry."""
    if payment.is_void:
        return payment
    if payment.refunds.exists():
        raise ValidationError(_("Refund the payment instead; it has refunds against it."))

    previous = snapshot(payment)
    payment.is_void = True
    payment.voided_at = timezone.now()
    payment.void_reason = reason[:255]
    payment.save(update_fields=["is_void", "voided_at", "void_reason", "updated_at"])

    if payment.journal_entry_id:
        reverse_journal_entry(
            entry=payment.journal_entry,
            reason=f"{_('Void')} {payment.receipt_number}",
            actor=actor,
            request=request,
        )

    _refresh_invoice_status(
        FeeInvoice.objects.select_for_update().get(pk=payment.invoice_id)
    )

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=payment,
        previous_values=previous,
        new_values=snapshot(payment),
        metadata={"event": "payment_voided", "reason": reason},
    )
    return payment


@transaction.atomic
def refund_payment(
    *,
    payment,
    amount,
    refund_date,
    reason,
    payment_method=None,
    actor=None,
    request=None,
):
    """Return money from a payment, posting the mirror ledger entry."""
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({"amount": _("Amount must be greater than zero.")})
    if payment.is_void:
        raise ValidationError(_("This payment has been voided."))

    already = money(
        payment.refunds.aggregate(total=Sum("amount"))["total"]
    )
    if amount > money(payment.amount - already):
        raise ValidationError(
            {"amount": _("That is more than the refundable amount.")}
        )

    method = payment_method or payment.payment_method
    if method.branch_id != payment.branch_id:
        raise PermissionDenied(_("That payment method belongs to a different branch."))

    refund = FeeRefund.objects.create(
        branch=payment.branch,
        organization=payment.organization,
        refund_number=next_refund_number(payment.branch),
        payment=payment,
        amount=amount,
        refund_date=refund_date,
        reason=reason[:255],
        payment_method=method,
        approved_by=actor,
    )

    entry = post_journal_entry(
        branch=payment.branch,
        date=refund_date,
        lines=[
            {
                "account": get_account(payment.branch, CODE_RECEIVABLE),
                "debit": amount,
                "description": refund.refund_number,
            },
            {
                "account": method.account,
                "credit": amount,
                "description": f"{_('Refund')} {payment.receipt_number}",
            },
        ],
        journal_type=Journal.JournalType.CASH_PAYMENT,
        description=f"{_('Fee refund')} {refund.refund_number}",
        reference=refund.refund_number,
        source_module="fees.refund",
        source_id=refund.pk,
        actor=actor,
        request=request,
    )
    refund.journal_entry = entry
    refund.save(update_fields=["journal_entry", "updated_at"])

    _refresh_invoice_status(
        FeeInvoice.objects.select_for_update().get(pk=payment.invoice_id)
    )

    log_activity(
        action="refund",
        request=request,
        user=actor,
        instance=refund,
        new_values={
            "refund": refund.refund_number,
            "amount": str(amount),
            "payment": payment.receipt_number,
            "reason": reason,
        },
    )
    return refund


@transaction.atomic
def waive_invoice_amount(*, invoice, amount, reason, waived_on, actor=None, request=None):
    """Write off part of an invoice."""
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({"amount": _("Amount must be greater than zero.")})

    invoice = FeeInvoice.objects.select_for_update().get(pk=invoice.pk)
    outstanding = money(
        invoice.total_amount - invoice.paid_amount - invoice.waiver_amount
    )
    if amount > outstanding:
        raise ValidationError(
            {"amount": _("That is more than the outstanding balance.")}
        )

    waiver = FeeWaiver.objects.create(
        branch=invoice.branch,
        organization=invoice.organization,
        invoice=invoice,
        amount=amount,
        reason=reason[:255],
        waived_on=waived_on,
        approved_by=actor,
    )

    post_journal_entry(
        branch=invoice.branch,
        date=waived_on,
        lines=[
            {
                "account": get_account(invoice.branch, CODE_FEE_DISCOUNT),
                "debit": amount,
                "description": f"{_('Waiver')} {invoice.invoice_number}",
            },
            {
                "account": get_account(invoice.branch, CODE_RECEIVABLE),
                "credit": amount,
                "description": invoice.invoice_number,
            },
        ],
        journal_type=Journal.JournalType.ADJUSTMENT,
        description=f"{_('Fee waiver')} {invoice.invoice_number}",
        reference=invoice.invoice_number,
        source_module="fees.waiver",
        source_id=waiver.pk,
        actor=actor,
        request=request,
    )

    _refresh_invoice_status(invoice)

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=waiver,
        new_values={"amount": str(amount), "reason": reason},
        metadata={"event": "fee_waived"},
    )
    return waiver


# --------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------
def outstanding_summary(user, branch=None, *, academic_year=None):
    queryset = FeeInvoice.objects.for_user(user, branch).exclude(
        status=FeeInvoice.Status.CANCELLED
    )
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)

    totals = queryset.aggregate(
        billed=Sum("total_amount"),
        collected=Sum("paid_amount"),
        waived=Sum("waiver_amount"),
    )
    billed = money(totals["billed"])
    collected = money(totals["collected"])
    waived = money(totals["waived"])
    return {
        "billed": billed,
        "collected": collected,
        "waived": waived,
        "outstanding": money(billed - collected - waived),
        "invoice_count": queryset.count(),
    }


def defaulters(user, branch=None, *, as_of=None, minimum=ZERO):
    """Students with an unpaid balance, worst first."""
    as_of = as_of or timezone.localdate()
    from django.db.models import F

    # Named `outstanding_balance`, not `balance`: FeeInvoice already exposes a
    # `balance` property, and an annotation of the same name cannot be set on
    # the instance.
    return (
        FeeInvoice.objects.for_user(user, branch)
        .exclude(status__in=[FeeInvoice.Status.CANCELLED, FeeInvoice.Status.PAID])
        .filter(due_date__lte=as_of)
        .annotate(
            outstanding_balance=F("total_amount") - F("paid_amount") - F("waiver_amount")
        )
        .filter(outstanding_balance__gt=minimum)
        .select_related("student", "academic_year")
        .order_by("-outstanding_balance")
    )
