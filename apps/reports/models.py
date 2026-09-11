"""Saved report definitions and an export trail."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import OrganizationOwnedModel


class SavedReport(OrganizationOwnedModel):
    """A named set of filters for one of the registered reports."""

    name = models.CharField(_("name"), max_length=200)
    report_key = models.CharField(_("report"), max_length=150)
    filters = models.JSONField(_("filters"), default=dict, blank=True)
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="saved_reports",
        verbose_name=_("branch"),
        help_text=_("Leave empty for an organization-wide report."),
    )
    is_shared = models.BooleanField(_("shared with colleagues"), default=False)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="saved_reports",
        verbose_name=_("created by"),
    )

    class Meta:
        verbose_name = _("saved report")
        verbose_name_plural = _("saved reports")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "created_by", "name"],
                name="uq_saved_report_name",
            )
        ]
        indexes = [models.Index(fields=["organization", "report_key"])]

    def __str__(self):
        return self.name


class ReportExport(OrganizationOwnedModel):
    """Who exported what, and with which filters.

    Exports leave the system, so they are recorded here as well as in the
    central audit log.
    """

    report_key = models.CharField(_("report"), max_length=150)
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_exports",
        verbose_name=_("branch"),
    )
    filters = models.JSONField(_("filters"), default=dict, blank=True)
    row_count = models.PositiveIntegerField(_("rows"), default=0)
    exported_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="report_exports",
        verbose_name=_("exported by"),
    )

    class Meta:
        verbose_name = _("report export")
        verbose_name_plural = _("report exports")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "report_key", "created_at"]),
            models.Index(fields=["exported_by", "created_at"]),
        ]

    def __str__(self):
        return f"{self.report_key} — {self.created_at:%Y-%m-%d}"
