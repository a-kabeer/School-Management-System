"""Parent portal.

The parent↔student relationship itself lives in :mod:`apps.students` (a
guardian is a school record, not a portal artefact). This app owns what is
purely portal-side: preferences and the requests parents raise.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BranchOwnedModel
from apps.students.models import Guardian, Student


class ParentPortalProfile(BranchOwnedModel):
    """Per-guardian portal settings."""

    guardian = models.OneToOneField(
        Guardian,
        on_delete=models.CASCADE,
        related_name="portal_profile",
        verbose_name=_("guardian"),
    )
    default_student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_guardians",
        verbose_name=_("default child"),
    )
    receives_attendance_alerts = models.BooleanField(
        _("attendance alerts"), default=True
    )
    receives_fee_reminders = models.BooleanField(_("fee reminders"), default=True)
    receives_result_alerts = models.BooleanField(_("result alerts"), default=True)
    last_seen_at = models.DateTimeField(_("last seen"), null=True, blank=True)

    class Meta:
        verbose_name = _("parent portal profile")
        verbose_name_plural = _("parent portal profiles")

    def __str__(self):
        return f"{self.guardian} — {_('portal')}"


class ParentRequest(BranchOwnedModel):
    """A leave request or query a parent raises about their own child."""

    class RequestType(models.TextChoices):
        LEAVE = "leave", _("Leave Request")
        QUERY = "query", _("General Query")
        DOCUMENT = "document", _("Document Request")
        MEETING = "meeting", _("Meeting Request")
        COMPLAINT = "complaint", _("Complaint")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        IN_REVIEW = "in_review", _("In Review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        CLOSED = "closed", _("Closed")

    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name="requests",
        verbose_name=_("guardian"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_requests",
        verbose_name=_("student"),
    )
    request_type = models.CharField(
        _("type"),
        max_length=20,
        choices=RequestType.choices,
        default=RequestType.QUERY,
    )
    subject = models.CharField(_("subject"), max_length=200)
    message = models.TextField(_("message"))
    start_date = models.DateField(_("from"), null=True, blank=True)
    end_date = models.DateField(_("to"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.OPEN
    )
    response = models.TextField(_("response"), blank=True)
    responded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parent_request_responses",
        verbose_name=_("responded by"),
    )
    responded_at = models.DateTimeField(_("responded at"), null=True, blank=True)

    class Meta:
        verbose_name = _("parent request")
        verbose_name_plural = _("parent requests")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "status", "created_at"]),
            models.Index(fields=["guardian", "status"]),
            models.Index(fields=["student", "status"]),
        ]

    def __str__(self):
        return f"{self.subject} — {self.student}"
