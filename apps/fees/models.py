"""Fee billing and collection.

Invoices are the ledger of what a student owes; payments, discounts, waivers
and refunds all adjust an invoice rather than standing alone, so an
outstanding balance is always reconstructable.
"""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, SchoolClass, Term
from apps.core.models import BranchOwnedModel, money_field
from apps.students.models import Student


class FeeType(BranchOwnedModel):
    """A billable item: monthly tuition, admission, exam, hostel, and so on."""

    class Frequency(models.TextChoices):
        ONE_TIME = "one_time", _("One Time")
        MONTHLY = "monthly", _("Monthly")
        TERM = "term", _("Per Term")
        ANNUAL = "annual", _("Annual")

    name = models.CharField(_("name"), max_length=150)
    code = models.CharField(_("code"), max_length=40, blank=True)
    frequency = models.CharField(
        _("frequency"),
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.MONTHLY,
    )
    description = models.CharField(_("description"), max_length=255, blank=True)
    income_account = models.ForeignKey(
        "finance.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_types",
        verbose_name=_("income account"),
    )
    is_refundable = models.BooleanField(_("refundable"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("fee type")
        verbose_name_plural = _("fee types")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="uq_fee_type_name")
        ]
        indexes = [models.Index(fields=["branch", "is_active"])]

    def __str__(self):
        return self.name


class FeeStructure(BranchOwnedModel):
    """What a class is charged for a fee type in a given academic year."""

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="fee_structures",
        verbose_name=_("academic year"),
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name="fee_structures",
        verbose_name=_("class"),
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name="structures",
        verbose_name=_("fee type"),
    )
    amount = money_field(_("amount"))
    is_mandatory = models.BooleanField(_("mandatory"), default=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("fee structure")
        verbose_name_plural = _("fee structures")
        ordering = ["school_class__level", "fee_type__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "school_class", "fee_type"],
                name="uq_fee_structure",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="ck_fee_structure_amount"
            ),
        ]
        indexes = [models.Index(fields=["branch", "academic_year", "school_class"])]

    def __str__(self):
        return f"{self.school_class} — {self.fee_type} — {self.amount}"


class StudentFee(BranchOwnedModel):
    """A per-student override or extra charge outside the class structure."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="fees",
        verbose_name=_("student"),
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="student_fees",
        verbose_name=_("academic year"),
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name="student_fees",
        verbose_name=_("fee type"),
    )
    amount = money_field(_("amount"))
    effective_from = models.DateField(_("effective from"))
    effective_to = models.DateField(_("effective to"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("student fee")
        verbose_name_plural = _("student fees")
        ordering = ["-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year", "fee_type", "effective_from"],
                name="uq_student_fee",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0), name="ck_student_fee_amount"
            ),
        ]
        indexes = [models.Index(fields=["branch", "student", "is_active"])]

    def __str__(self):
        return f"{self.student} — {self.fee_type}"


class FeeInvoice(BranchOwnedModel):
    """What a student owes for one billing period."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ISSUED = "issued", _("Issued")
        PARTIALLY_PAID = "partially_paid", _("Partially Paid")
        PAID = "paid", _("Paid")
        OVERDUE = "overdue", _("Overdue")
        CANCELLED = "cancelled", _("Cancelled")

    invoice_number = models.CharField(_("invoice number"), max_length=50)
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("student"),
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("academic year"),
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("term"),
    )
    period_month = models.DateField(
        _("billing month"),
        null=True,
        blank=True,
        help_text=_("First day of the month this invoice covers."),
    )
    issue_date = models.DateField(_("issue date"))
    due_date = models.DateField(_("due date"))
    subtotal = money_field(_("subtotal"), default=Decimal("0.00"))
    discount_amount = money_field(_("discount"), default=Decimal("0.00"))
    waiver_amount = money_field(_("waiver"), default=Decimal("0.00"))
    total_amount = money_field(_("total"), default=Decimal("0.00"))
    paid_amount = money_field(_("paid"), default=Decimal("0.00"))
    refunded_amount = money_field(_("refunded"), default=Decimal("0.00"))
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
        verbose_name=_("created by"),
    )

    class Meta:
        verbose_name = _("fee invoice")
        verbose_name_plural = _("fee invoices")
        ordering = ["-issue_date", "-invoice_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "invoice_number"], name="uq_fee_invoice_number"
            ),
            models.UniqueConstraint(
                fields=["student", "academic_year", "period_month"],
                condition=models.Q(period_month__isnull=False),
                name="uq_student_monthly_invoice",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0)
                & models.Q(paid_amount__gte=0),
                name="ck_fee_invoice_amounts",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "status", "due_date"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["branch", "issue_date"]),
            models.Index(fields=["branch", "academic_year", "period_month"]),
        ]

    def __str__(self):
        return self.invoice_number

    @property
    def balance(self):
        return self.total_amount - self.paid_amount

    @property
    def is_settled(self):
        return self.balance <= Decimal("0.00")


class FeeInvoiceItem(BranchOwnedModel):
    invoice = models.ForeignKey(
        FeeInvoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("invoice"),
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        related_name="invoice_items",
        verbose_name=_("fee type"),
    )
    description = models.CharField(_("description"), max_length=255, blank=True)
    quantity = models.PositiveSmallIntegerField(_("quantity"), default=1)
    unit_amount = money_field(_("unit amount"))
    discount_amount = money_field(_("discount"), default=Decimal("0.00"))
    line_total = money_field(_("line total"), default=Decimal("0.00"))

    class Meta:
        verbose_name = _("invoice item")
        verbose_name_plural = _("invoice items")
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(unit_amount__gte=0)
                & models.Q(discount_amount__gte=0),
                name="ck_invoice_item_amounts",
            )
        ]
        indexes = [models.Index(fields=["invoice", "fee_type"])]

    def __str__(self):
        return f"{self.fee_type} — {self.line_total}"

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_amount * self.quantity) - self.discount_amount
        super().save(*args, **kwargs)


class FeeDiscount(BranchOwnedModel):
    """A recurring concession, e.g. sibling or merit."""

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FIXED = "fixed", _("Fixed Amount")

    name = models.CharField(_("name"), max_length=150)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="discounts",
        verbose_name=_("student"),
    )
    fee_type = models.ForeignKey(
        FeeType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discounts",
        verbose_name=_("fee type"),
        help_text=_("Leave empty to apply to every fee type."),
    )
    discount_type = models.CharField(
        _("discount type"),
        max_length=20,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    value = models.DecimalField(_("value"), max_digits=9, decimal_places=2)
    valid_from = models.DateField(_("valid from"))
    valid_to = models.DateField(_("valid to"), null=True, blank=True)
    reason = models.CharField(_("reason"), max_length=255, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_discounts",
        verbose_name=_("approved by"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("fee discount")
        verbose_name_plural = _("fee discounts")
        ordering = ["-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(value__gte=0), name="ck_fee_discount_value"
            )
        ]
        indexes = [models.Index(fields=["branch", "student", "is_active"])]

    def __str__(self):
        return f"{self.student} — {self.name}"


class FeeWaiver(BranchOwnedModel):
    """A one-off write-off against a specific invoice."""

    invoice = models.ForeignKey(
        FeeInvoice,
        on_delete=models.PROTECT,
        related_name="waivers",
        verbose_name=_("invoice"),
    )
    amount = money_field(_("amount"))
    reason = models.CharField(_("reason"), max_length=255)
    waived_on = models.DateField(_("waived on"))
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_waivers",
        verbose_name=_("approved by"),
    )

    class Meta:
        verbose_name = _("fee waiver")
        verbose_name_plural = _("fee waivers")
        ordering = ["-waived_on"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ck_fee_waiver_amount"
            )
        ]
        indexes = [models.Index(fields=["branch", "waived_on"])]

    def __str__(self):
        return f"{self.invoice} — {self.amount}"


class FeePayment(BranchOwnedModel):
    """Money received against an invoice."""

    receipt_number = models.CharField(_("receipt number"), max_length=50)
    invoice = models.ForeignKey(
        FeeInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("invoice"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("student"),
    )
    payment_method = models.ForeignKey(
        "finance.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="fee_payments",
        verbose_name=_("payment method"),
    )
    amount = money_field(_("amount"))
    payment_date = models.DateField(_("payment date"), db_index=True)
    reference = models.CharField(_("reference"), max_length=150, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    journal_entry = models.OneToOneField(
        "finance.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_payment",
        verbose_name=_("journal entry"),
    )
    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments",
        verbose_name=_("received by"),
    )
    is_void = models.BooleanField(_("void"), default=False)
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    void_reason = models.CharField(_("void reason"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("fee payment")
        verbose_name_plural = _("fee payments")
        ordering = ["-payment_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "receipt_number"], name="uq_fee_receipt_number"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ck_fee_payment_amount"
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "payment_date"]),
            models.Index(fields=["student", "payment_date"]),
            models.Index(fields=["invoice", "is_void"]),
            models.Index(fields=["branch", "is_void", "payment_date"]),
        ]

    def __str__(self):
        return self.receipt_number


class FeeRefund(BranchOwnedModel):
    """Money returned from a previously collected payment."""

    refund_number = models.CharField(_("refund number"), max_length=50)
    payment = models.ForeignKey(
        FeePayment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("payment"),
    )
    amount = money_field(_("amount"))
    refund_date = models.DateField(_("refund date"))
    reason = models.CharField(_("reason"), max_length=255)
    payment_method = models.ForeignKey(
        "finance.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="fee_refunds",
        verbose_name=_("payment method"),
    )
    journal_entry = models.OneToOneField(
        "finance.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_refund",
        verbose_name=_("journal entry"),
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_refunds",
        verbose_name=_("approved by"),
    )

    class Meta:
        verbose_name = _("fee refund")
        verbose_name_plural = _("fee refunds")
        ordering = ["-refund_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "refund_number"], name="uq_fee_refund_number"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ck_fee_refund_amount"
            ),
        ]
        indexes = [models.Index(fields=["branch", "refund_date"])]

    def __str__(self):
        return self.refund_number
