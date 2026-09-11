"""Payroll: salary structures, periods, runs and payments."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BranchOwnedModel, money_field
from apps.staff.models import Staff


class SalaryComponent(BranchOwnedModel):
    """An earning or deduction line available to salary structures."""

    class ComponentType(models.TextChoices):
        EARNING = "earning", _("Earning")
        DEDUCTION = "deduction", _("Deduction")

    class CalculationType(models.TextChoices):
        FIXED = "fixed", _("Fixed Amount")
        PERCENT_OF_BASIC = "percent_basic", _("Percentage of Basic")

    name = models.CharField(_("name"), max_length=150)
    code = models.CharField(_("code"), max_length=40)
    component_type = models.CharField(
        _("type"), max_length=20, choices=ComponentType.choices
    )
    calculation_type = models.CharField(
        _("calculation"),
        max_length=20,
        choices=CalculationType.choices,
        default=CalculationType.FIXED,
    )
    default_value = models.DecimalField(
        _("default value"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    is_taxable = models.BooleanField(_("taxable"), default=False)
    expense_account = models.ForeignKey(
        "finance.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_components",
        verbose_name=_("expense account"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("salary component")
        verbose_name_plural = _("salary components")
        ordering = ["component_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "code"], name="uq_salary_component_code"
            ),
            models.CheckConstraint(
                condition=models.Q(default_value__gte=0),
                name="ck_salary_component_value",
            ),
        ]

    def __str__(self):
        return self.name


class SalaryStructure(BranchOwnedModel):
    """A reusable template of components, e.g. "Senior Teacher"."""

    name = models.CharField(_("name"), max_length=150)
    description = models.CharField(_("description"), max_length=255, blank=True)
    basic_salary = money_field(_("basic salary"), default=Decimal("0.00"))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("salary structure")
        verbose_name_plural = _("salary structures")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"], name="uq_salary_structure_name"
            ),
            models.CheckConstraint(
                condition=models.Q(basic_salary__gte=0),
                name="ck_salary_structure_basic",
            ),
        ]

    def __str__(self):
        return self.name


class SalaryStructureLine(BranchOwnedModel):
    """A component inside a structure, with the value to use."""

    structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("structure"),
    )
    component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.PROTECT,
        related_name="structure_lines",
        verbose_name=_("component"),
    )
    value = models.DecimalField(
        _("value"), max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    sequence = models.PositiveSmallIntegerField(_("sequence"), default=1)

    class Meta:
        verbose_name = _("structure line")
        verbose_name_plural = _("structure lines")
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["structure", "component"], name="uq_structure_component"
            )
        ]

    def __str__(self):
        return f"{self.structure} — {self.component}"


class EmployeeSalary(BranchOwnedModel):
    """The salary a staff member is on, from a given date."""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="salaries",
        verbose_name=_("staff"),
    )
    structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.PROTECT,
        related_name="employee_salaries",
        verbose_name=_("structure"),
    )
    basic_salary = money_field(_("basic salary"))
    effective_from = models.DateField(_("effective from"))
    effective_to = models.DateField(_("effective to"), null=True, blank=True)
    bank_account_number = models.CharField(
        _("bank account"), max_length=60, blank=True
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("employee salary")
        verbose_name_plural = _("employee salaries")
        ordering = ["-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "effective_from"], name="uq_employee_salary_from"
            ),
            models.UniqueConstraint(
                fields=["staff"],
                condition=models.Q(is_active=True),
                name="uq_employee_single_active_salary",
            ),
            models.CheckConstraint(
                condition=models.Q(basic_salary__gte=0),
                name="ck_employee_salary_basic",
            ),
        ]
        indexes = [models.Index(fields=["branch", "staff", "is_active"])]

    def __str__(self):
        return f"{self.staff} — {self.basic_salary}"


class PayrollPeriod(BranchOwnedModel):
    """A payroll month. Closing it stops further runs."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        PROCESSING = "processing", _("Processing")
        CLOSED = "closed", _("Closed")

    name = models.CharField(_("name"), max_length=100)
    month = models.DateField(_("month"), help_text=_("First day of the month."))
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    payment_date = models.DateField(_("payment date"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.OPEN
    )

    class Meta:
        verbose_name = _("payroll period")
        verbose_name_plural = _("payroll periods")
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "month"], name="uq_payroll_period_month"
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ck_payroll_period_dates",
            ),
        ]
        indexes = [models.Index(fields=["branch", "status", "month"])]

    def __str__(self):
        return self.name


class PayrollRun(BranchOwnedModel):
    """One execution of payroll for a period."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        APPROVED = "approved", _("Approved")
        PAID = "paid", _("Paid")
        CANCELLED = "cancelled", _("Cancelled")

    period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.PROTECT,
        related_name="runs",
        verbose_name=_("period"),
    )
    reference = models.CharField(_("reference"), max_length=50)
    run_date = models.DateField(_("run date"))
    total_gross = money_field(_("total gross"), default=Decimal("0.00"))
    total_deductions = money_field(_("total deductions"), default=Decimal("0.00"))
    total_net = money_field(_("total net"), default=Decimal("0.00"))
    employee_count = models.PositiveIntegerField(_("employees"), default=0)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    journal_entry = models.OneToOneField(
        "finance.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_run",
        verbose_name=_("journal entry"),
    )
    processed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs",
        verbose_name=_("processed by"),
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("payroll run")
        verbose_name_plural = _("payroll runs")
        ordering = ["-run_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "reference"], name="uq_payroll_run_reference"
            ),
            models.CheckConstraint(
                condition=models.Q(total_net__gte=0), name="ck_payroll_run_net"
            ),
        ]
        indexes = [models.Index(fields=["branch", "status", "run_date"])]

    def __str__(self):
        return self.reference


class PayrollItem(BranchOwnedModel):
    """One staff member's payslip inside a run."""

    run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("run"),
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.PROTECT,
        related_name="payroll_items",
        verbose_name=_("staff"),
    )
    basic_salary = money_field(_("basic salary"), default=Decimal("0.00"))
    total_allowances = money_field(_("allowances"), default=Decimal("0.00"))
    total_deductions = money_field(_("deductions"), default=Decimal("0.00"))
    gross_salary = money_field(_("gross salary"), default=Decimal("0.00"))
    net_salary = money_field(_("net salary"), default=Decimal("0.00"))
    days_present = models.DecimalField(
        _("days present"), max_digits=5, decimal_places=1, default=Decimal("0.0")
    )
    days_absent = models.DecimalField(
        _("days absent"), max_digits=5, decimal_places=1, default=Decimal("0.0")
    )
    #: ``[{"code": "HRA", "name": ..., "type": "earning", "amount": "1200.00"}]``
    breakdown = models.JSONField(_("breakdown"), default=list, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("payroll item")
        verbose_name_plural = _("payroll items")
        ordering = ["staff__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["run", "staff"], name="uq_payroll_run_staff"),
            models.CheckConstraint(
                condition=models.Q(net_salary__gte=0), name="ck_payroll_item_net"
            ),
        ]
        indexes = [models.Index(fields=["branch", "run", "staff"])]

    def __str__(self):
        return f"{self.staff} — {self.net_salary}"


class SalaryPayment(BranchOwnedModel):
    """Money actually disbursed against a payslip."""

    payroll_item = models.ForeignKey(
        PayrollItem,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("payroll item"),
    )
    payment_method = models.ForeignKey(
        "finance.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="salary_payments",
        verbose_name=_("payment method"),
    )
    voucher_number = models.CharField(_("voucher number"), max_length=50)
    amount = money_field(_("amount"))
    payment_date = models.DateField(_("payment date"))
    reference = models.CharField(_("reference"), max_length=150, blank=True)
    journal_entry = models.OneToOneField(
        "finance.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_payment",
        verbose_name=_("journal entry"),
    )
    paid_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_payments_made",
        verbose_name=_("paid by"),
    )

    class Meta:
        verbose_name = _("salary payment")
        verbose_name_plural = _("salary payments")
        ordering = ["-payment_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "voucher_number"], name="uq_salary_voucher_number"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="ck_salary_payment_amount"
            ),
        ]
        indexes = [models.Index(fields=["branch", "payment_date"])]

    def __str__(self):
        return self.voucher_number
