"""Abstract base models every other app builds on."""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from .managers import SoftDeleteManager, TenantManager, TenantQuerySet
from .permissions import MODULE_PERMISSIONS


def money_field(verbose_name=None, **kwargs):
    """A Decimal money column. Money is never stored as a float."""
    kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
    kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
    if verbose_name is not None:
        return models.DecimalField(verbose_name, **kwargs)
    return models.DecimalField(**kwargs)


class UUIDModel(models.Model):
    """Opaque primary keys, so a guessed URL id never lands on a real row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """UUID primary key plus timestamps - the default for new models."""

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Rows are retired, not erased, so audit history stays meaningful."""

    is_deleted = models.BooleanField(_("deleted"), default=False, db_index=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = TenantManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        return (1, {self._meta.label: 1})

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class OrganizationOwnedModel(BaseModel):
    """Organization-wide record: shared by every branch of one tenant."""

    organization = models.ForeignKey(
        "tenants.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name=_("organization"),
        db_index=True,
    )

    objects = TenantManager()

    class Meta:
        abstract = True


class BranchOwnedModel(OrganizationOwnedModel):
    """Operational record belonging to exactly one branch.

    ``branch`` is PROTECTed: a branch with live records cannot be deleted out
    from under them.
    """

    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name=_("branch"),
        db_index=True,
    )

    objects = TenantManager()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["organization", "branch"]),
        ]

    def save(self, *args, **kwargs):
        # The organization is implied by the branch; deriving it removes a way
        # for a crafted form to pair a branch with someone else's organization.
        if self.branch_id and not self.organization_id:
            self.organization_id = self.branch.organization_id
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        if (
            self.branch_id
            and self.organization_id
            and self.branch.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"branch": _("This branch belongs to a different organization.")}
            )


class BranchOwnedSoftDeleteModel(SoftDeleteModel, BranchOwnedModel):
    """Branch record that supports delete/restore."""

    objects = SoftDeleteManager()
    all_objects = TenantManager()

    class Meta(BranchOwnedModel.Meta):
        abstract = True


class SystemSetting(BaseModel):
    """Key/value configuration, optionally scoped to one organization.

    This model also carries the project's non-model permissions (module entry
    points, financial operations, reports). Django needs a model to hang them
    on, and settings are the natural owner of "can access administrative
    settings".
    """

    organization = models.ForeignKey(
        "tenants.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="settings",
        verbose_name=_("organization"),
    )
    key = models.CharField(_("key"), max_length=150)
    value = models.JSONField(_("value"), default=dict, blank=True)
    description = models.CharField(_("description"), max_length=255, blank=True)
    is_editable = models.BooleanField(_("editable"), default=True)

    objects = models.Manager()

    class Meta:
        verbose_name = _("system setting")
        verbose_name_plural = _("system settings")
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"], name="uq_system_setting_key"
            )
        ]
        permissions = [
            (codename, str(label)) for codename, label in MODULE_PERMISSIONS
        ]

    def __str__(self):
        return self.key


__all__ = [
    "BaseModel",
    "SystemSetting",
    "BranchOwnedModel",
    "BranchOwnedSoftDeleteModel",
    "OrganizationOwnedModel",
    "SoftDeleteModel",
    "TimeStampedModel",
    "UUIDModel",
    "TenantQuerySet",
    "money_field",
]
