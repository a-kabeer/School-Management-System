"""Organization and Branch - the two tenancy boundaries.

Organization is the customer. Branch is the operational boundary that almost
every business record is filed under.
"""

from django.core.validators import MinLengthValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.validators import validate_phone


class Organization(BaseModel):
    class Status(models.TextChoices):
        TRIAL = "trial", _("Trial")
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspended")
        CLOSED = "closed", _("Closed")

    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(_("slug"), max_length=255, unique=True)
    legal_name = models.CharField(_("legal name"), max_length=255, blank=True)
    logo = models.ImageField(
        _("logo"), upload_to="organizations/logos/", blank=True, null=True
    )
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(
        _("phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    address = models.TextField(_("address"), blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    country = models.CharField(_("country"), max_length=120, default="Pakistan")
    timezone = models.CharField(_("timezone"), max_length=100, default="Asia/Karachi")
    currency = models.CharField(_("currency"), max_length=10, default="PKR")
    default_language = models.CharField(
        _("default language"),
        max_length=5,
        choices=[("en", _("English")), ("ur", _("Urdu")), ("ar", _("Arabic"))],
        default="en",
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.TRIAL
    )

    class Meta:
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")
        ordering = ["name"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return self.name

    @property
    def is_operational(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE}


class Branch(BaseModel):
    """A campus, centre or the central administration office.

    ``is_central_administration`` marks the head office. Users attached to it
    are the "central administrators" of the brief: they still need explicit
    :class:`~apps.accounts.models.UserBranchAccess` rows for the branches they
    oversee, so access stays auditable instead of implicit.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="branches",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("name"), max_length=255)
    code = models.CharField(
        _("code"), max_length=50, validators=[MinLengthValidator(2)]
    )
    phone = models.CharField(
        _("phone"), max_length=40, validators=[validate_phone], blank=True
    )
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_central_administration = models.BooleanField(
        _("central administration"), default=False
    )
    opened_on = models.DateField(_("opened on"), null=True, blank=True)
    working_weekdays = models.JSONField(
        _("working days"), default=list,
        help_text=_("Days used by this branch for recurring weekly timetables. Monday=0 through Sunday=6."),
    )

    class Meta:
        verbose_name = _("branch")
        verbose_name_plural = _("branches")
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="uq_branch_code"
            ),
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_branch_name"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["organization", "is_central_administration"]),
        ]

    def __str__(self):
        return self.name

    @property
    def full_name(self):
        return f"{self.organization.name} — {self.name}"
