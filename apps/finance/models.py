"""Double-entry accounting.

Money moves as balanced journal entries: every :class:`JournalEntry` owns two
or more :class:`Transaction` lines whose debits equal their credits. Nothing
writes a bare "income row"; fees, payroll and manual entries all post here.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.constants import PaymentMethodType
from apps.core.models import BranchOwnedModel, OrganizationOwnedModel, money_field


class AccountType(OrganizationOwnedModel):
    """Asset / Liability / Equity / Income / Expense, with its normal side."""

    class Nature(models.TextChoices):
        ASSET = "asset", _("Asset")
        LIABILITY = "liability", _("Liability")
        EQUITY = "equity", _("Equity")
        INCOME = "income", _("Income")
        EXPENSE = "expense", _("Expense")

    class NormalBalance(models.TextChoices):
        DEBIT = "debit", _("Debit")
        CREDIT = "credit", _("Credit")

    name = models.CharField(_("name"), max_length=120)
    code = models.CharField(_("code"), max_length=20)
    nature = models.CharField(_("nature"), max_length=20, choices=Nature.choices)
    normal_balance = models.CharField(
        _("normal balance"), max_length=10, choices=NormalBalance.choices
    )

    class Meta:
        verbose_name = _("account type")
        verbose_name_plural = _("account types")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="uq_account_type_code"
            )
        ]

    def __str__(self):
        return self.name


class Account(BranchOwnedModel):
    """A ledger account in the chart of accounts."""

    account_type = models.ForeignKey(
        AccountType,
        on_delete=models.PROTECT,
        related_name="accounts",
        verbose_name=_("account type"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent account"),
    )
    code = models.CharField(_("code"), max_length=30)
    name = models.CharField(_("name"), max_length=200)
    description = models.CharField(_("description"), max_length=255, blank=True)
    opening_balance = money_field(_("opening balance"), default=Decimal("0.00"))
    is_bank_account = models.BooleanField(_("bank/cash account"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("account")
        verbose_name_plural = _("chart of accounts")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="uq_account_code"),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active"]),
            models.Index(fields=["organization", "branch", "account_type"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def balance(self):
        from django.db.models import Sum

        totals = self.transactions.filter(
            journal_entry__status=JournalEntry.Status.POSTED
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        debit = totals["debit"] or Decimal("0.00")
        credit = totals["credit"] or Decimal("0.00")
        if self.account_type.normal_balance == AccountType.NormalBalance.DEBIT:
            return self.opening_balance + debit - credit
        return self.opening_balance + credit - debit


class FiscalPeriod(BranchOwnedModel):
    """An accounting period. Closed periods reject new postings."""

    name = models.CharField(_("name"), max_length=100)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    is_closed = models.BooleanField(_("closed"), default=False)
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_fiscal_periods",
        verbose_name=_("closed by"),
    )

    class Meta:
        verbose_name = _("fiscal period")
        verbose_name_plural = _("fiscal periods")
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"], name="uq_fiscal_period_name"
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ck_fiscal_period_dates",
            ),
        ]
        indexes = [models.Index(fields=["branch", "is_closed"])]

    def __str__(self):
        return self.name

    def contains(self, date_value):
        return self.start_date <= date_value <= self.end_date


class PaymentMethod(BranchOwnedModel):
    """How money physically arrives, and which account it lands in."""

    name = models.CharField(_("name"), max_length=100)
    method_type = models.CharField(
        _("type"),
        max_length=20,
        choices=PaymentMethodType.choices,
        default=PaymentMethodType.CASH,
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="payment_methods",
        verbose_name=_("ledger account"),
    )
    requires_reference = models.BooleanField(_("reference required"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("payment method")
        verbose_name_plural = _("payment methods")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"], name="uq_payment_method_name"
            )
        ]

    def __str__(self):
        return self.name


class Journal(BranchOwnedModel):
    """A book of entries: general, cash receipts, payroll, and so on."""

    class JournalType(models.TextChoices):
        GENERAL = "general", _("General")
        CASH_RECEIPT = "cash_receipt", _("Cash Receipt")
        CASH_PAYMENT = "cash_payment", _("Cash Payment")
        PAYROLL = "payroll", _("Payroll")
        ADJUSTMENT = "adjustment", _("Adjustment")

    name = models.CharField(_("name"), max_length=120)
    code = models.CharField(_("code"), max_length=20)
    journal_type = models.CharField(
        _("type"),
        max_length=20,
        choices=JournalType.choices,
        default=JournalType.GENERAL,
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("journal")
        verbose_name_plural = _("journals")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="uq_journal_code")
        ]

    def __str__(self):
        return self.name


class JournalEntry(BranchOwnedModel):
    """A balanced document. Its lines are :class:`Transaction` rows."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        POSTED = "posted", _("Posted")
        REVERSED = "reversed", _("Reversed")

    journal = models.ForeignKey(
        Journal,
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name=_("journal"),
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        related_name="entries",
        verbose_name=_("fiscal period"),
    )
    entry_number = models.CharField(_("entry number"), max_length=40)
    date = models.DateField(_("date"), db_index=True)
    reference = models.CharField(_("reference"), max_length=150, blank=True)
    description = models.TextField(_("description"), blank=True)
    total_debit = money_field(_("total debit"), default=Decimal("0.00"))
    total_credit = money_field(_("total credit"), default=Decimal("0.00"))
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    #: Where this entry came from, so a payment can be traced to its ledger.
    source_module = models.CharField(_("source module"), max_length=50, blank=True)
    source_id = models.CharField(_("source id"), max_length=64, blank=True)
    reversal_of = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_by",
        verbose_name=_("reversal of"),
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entries",
        verbose_name=_("created by"),
    )
    posted_at = models.DateTimeField(_("posted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("journal entry")
        verbose_name_plural = _("journal entries")
        ordering = ["-date", "-entry_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "entry_number"], name="uq_journal_entry_number"
            ),
            # A posted entry that does not balance is a data-integrity bug;
            # the database refuses to store one.
            models.CheckConstraint(
                condition=models.Q(status="draft")
                | models.Q(total_debit=models.F("total_credit")),
                name="ck_journal_entry_balanced",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["branch", "status", "date"]),
            models.Index(fields=["source_module", "source_id"]),
        ]

    def __str__(self):
        return f"{self.entry_number} — {self.date}"

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit

    def clean(self):
        super().clean()
        if self.fiscal_period_id and self.date and not self.fiscal_period.contains(self.date):
            raise ValidationError(
                {"date": _("The date falls outside the selected fiscal period.")}
            )


class Transaction(BranchOwnedModel):
    """One debit-or-credit line of a journal entry."""

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("journal entry"),
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("account"),
    )
    debit = money_field(_("debit"), default=Decimal("0.00"))
    credit = money_field(_("credit"), default=Decimal("0.00"))
    description = models.CharField(_("description"), max_length=255, blank=True)
    line_number = models.PositiveSmallIntegerField(_("line"), default=1)

    class Meta:
        verbose_name = _("transaction line")
        verbose_name_plural = _("transaction lines")
        ordering = ["journal_entry", "line_number"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name="ck_transaction_non_negative",
            ),
            # Exactly one side carries the amount.
            models.CheckConstraint(
                condition=(
                    (models.Q(debit__gt=0) & models.Q(credit=0))
                    | (models.Q(credit__gt=0) & models.Q(debit=0))
                ),
                name="ck_transaction_single_side",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "journal_entry"]),
            models.Index(fields=["branch", "account"]),
        ]

    def __str__(self):
        side = _("Dr") if self.debit else _("Cr")
        return f"{self.account.code} {side} {self.debit or self.credit}"
