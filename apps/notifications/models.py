"""Centralized notifications.

A :class:`Notification` is the message; a :class:`NotificationRecipient` is one
delivery of it over one channel. That split is what lets the same announcement
go in-app to one parent and by SMS to another without duplicating the content
or hard-coding a provider.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BranchOwnedModel, OrganizationOwnedModel


class Channel(models.TextChoices):
    IN_APP = "in_app", _("In App")
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    WHATSAPP = "whatsapp", _("WhatsApp")
    PUSH = "push", _("Push")


class NotificationTemplate(OrganizationOwnedModel):
    """Reusable subject/body per event and channel, with placeholders."""

    event = models.CharField(_("event"), max_length=100)
    channel = models.CharField(_("channel"), max_length=20, choices=Channel.choices)
    language = models.CharField(
        _("language"),
        max_length=5,
        choices=[("en", _("English")), ("ur", _("Urdu")), ("ar", _("Arabic"))],
        default="en",
    )
    title = models.CharField(_("title"), max_length=255)
    body = models.TextField(
        _("body"), help_text=_("Use {placeholders} for context values.")
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("notification template")
        verbose_name_plural = _("notification templates")
        ordering = ["event", "channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "event", "channel", "language"],
                name="uq_notification_template",
            )
        ]
        indexes = [models.Index(fields=["organization", "event", "is_active"])]

    def __str__(self):
        return f"{self.event} — {self.get_channel_display()}"

    def render(self, context):
        def _fill(text):
            try:
                return text.format(**context)
            except (KeyError, IndexError, ValueError):
                # A template with an unknown placeholder should still deliver.
                return text

        return _fill(self.title), _fill(self.body)


class Notification(BranchOwnedModel):
    """One message, possibly delivered to many recipients."""

    class Priority(models.TextChoices):
        LOW = "low", _("Low")
        NORMAL = "normal", _("Normal")
        HIGH = "high", _("High")
        URGENT = "urgent", _("Urgent")

    event = models.CharField(_("event"), max_length=100)
    title = models.CharField(_("title"), max_length=255)
    body = models.TextField(_("body"))
    priority = models.CharField(
        _("priority"), max_length=20, choices=Priority.choices, default=Priority.NORMAL
    )
    link_url = models.CharField(_("link"), max_length=500, blank=True)
    context = models.JSONField(_("context"), default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
        verbose_name=_("created by"),
    )

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["organization", "event"]),
        ]

    def __str__(self):
        return self.title


class NotificationRecipient(BranchOwnedModel):
    """One delivery attempt of a notification to one user on one channel."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        READ = "read", _("Read")
        FAILED = "failed", _("Failed")
        SKIPPED = "skipped", _("Skipped")

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name=_("notification"),
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notification_receipts",
        verbose_name=_("user"),
    )
    channel = models.CharField(_("channel"), max_length=20, choices=Channel.choices)
    address = models.CharField(
        _("address"),
        max_length=255,
        blank=True,
        help_text=_("Email, phone number or device token used."),
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    error_message = models.TextField(_("error"), blank=True)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)

    class Meta:
        verbose_name = _("notification recipient")
        verbose_name_plural = _("notification recipients")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "user", "channel"],
                name="uq_notification_recipient",
            )
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "channel", "status"]),
            models.Index(fields=["branch", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} — {self.notification.title}"

    @property
    def is_read(self):
        return self.status == self.Status.READ


class NotificationPreference(BranchOwnedModel):
    """Per-user opt-in/out for an event and channel."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name=_("user"),
    )
    event = models.CharField(
        _("event"),
        max_length=100,
        blank=True,
        help_text=_("Leave empty to apply to every event."),
    )
    channel = models.CharField(_("channel"), max_length=20, choices=Channel.choices)
    is_enabled = models.BooleanField(_("enabled"), default=True)

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event", "channel"], name="uq_notification_preference"
            )
        ]
        indexes = [models.Index(fields=["user", "channel"])]

    def __str__(self):
        return f"{self.user} — {self.channel}"
