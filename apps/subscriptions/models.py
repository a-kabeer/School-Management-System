"""Plans and organization subscriptions."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, OrganizationOwnedModel, money_field


class Plan(BaseModel):
    """A commercial plan. Global, not owned by any one organization."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    code = models.SlugField(_("code"), max_length=60, unique=True)
    description = models.CharField(_("description"), max_length=255, blank=True)
    monthly_price = money_field(_("monthly price"), default=Decimal("0.00"))
    yearly_price = money_field(_("yearly price"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=10, default="PKR")
    max_branches = models.PositiveIntegerField(_("branch limit"), null=True, blank=True)
    max_students = models.PositiveIntegerField(_("student limit"), null=True, blank=True)
    max_users = models.PositiveIntegerField(_("user limit"), null=True, blank=True)
    storage_limit_mb = models.PositiveIntegerField(
        _("storage limit (MB)"), null=True, blank=True
    )
    monthly_sms_limit = models.PositiveIntegerField(_("SMS per month"), default=0)
    monthly_whatsapp_limit = models.PositiveIntegerField(
        _("WhatsApp per month"), default=0
    )
    #: ``{"hifz": true, "payroll": true, ...}`` - feature switches per plan.
    features = models.JSONField(_("features"), default=dict, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["sort_order", "monthly_price"]

    def __str__(self):
        return self.name


class Subscription(OrganizationOwnedModel):
    class Status(models.TextChoices):
        TRIAL = "trial", _("Trial")
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Past Due")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", _("Monthly")
        YEARLY = "yearly", _("Yearly")

    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name=_("plan"),
    )
    billing_cycle = models.CharField(
        _("billing cycle"),
        max_length=20,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    trial_ends_on = models.DateField(_("trial ends"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.TRIAL
    )
    auto_renew = models.BooleanField(_("auto renew"), default=False)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(status__in=["trial", "active", "past_due"]),
                name="uq_organization_live_subscription",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ck_subscription_dates",
            ),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return f"{self.organization} — {self.plan}"

    @property
    def is_live(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE, self.Status.PAST_DUE}


class SubscriptionInvoice(OrganizationOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ISSUED = "issued", _("Issued")
        PAID = "paid", _("Paid")
        OVERDUE = "overdue", _("Overdue")
        VOID = "void", _("Void")

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("subscription"),
    )
    invoice_number = models.CharField(_("invoice number"), max_length=50)
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))
    amount = money_field(_("amount"))
    tax_amount = money_field(_("tax"), default=Decimal("0.00"))
    total_amount = money_field(_("total"))
    issue_date = models.DateField(_("issue date"))
    due_date = models.DateField(_("due date"))
    paid_on = models.DateField(_("paid on"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    class Meta:
        verbose_name = _("subscription invoice")
        verbose_name_plural = _("subscription invoices")
        ordering = ["-issue_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "invoice_number"],
                name="uq_subscription_invoice_number",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="ck_subscription_invoice_total",
            ),
        ]

    def __str__(self):
        return self.invoice_number


class FeatureUsage(OrganizationOwnedModel):
    """Monthly counters checked against the plan's limits."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="usage",
        verbose_name=_("subscription"),
    )
    metric = models.CharField(_("metric"), max_length=60)
    period_month = models.DateField(_("month"))
    used = models.PositiveIntegerField(_("used"), default=0)
    limit = models.PositiveIntegerField(_("limit"), null=True, blank=True)

    class Meta:
        verbose_name = _("feature usage")
        verbose_name_plural = _("feature usage")
        ordering = ["-period_month", "metric"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "metric", "period_month"],
                name="uq_feature_usage",
            )
        ]
        indexes = [models.Index(fields=["organization", "metric", "period_month"])]

    def __str__(self):
        return f"{self.metric} — {self.used}"

    @property
    def is_exceeded(self):
        return self.limit is not None and self.used > self.limit
