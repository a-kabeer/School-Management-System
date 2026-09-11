"""Delivery transports.

Each channel is resolved from ``settings.NOTIFICATION_BACKENDS`` by dotted
path, so adding SMS or WhatsApp later is configuration plus one class - no
change to the modules that raise notifications.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class NotificationBackend:
    """Interface every transport implements."""

    #: Channel key this backend serves.
    channel = ""

    def address_for(self, user):
        """Where to send - email, phone, device token. Empty means skip."""
        return ""

    def send(self, recipient):
        """Deliver one :class:`NotificationRecipient`. Return True on success."""
        raise NotImplementedError


class InAppBackend(NotificationBackend):
    """Nothing to transmit: the row itself is the notification."""

    channel = "in_app"

    def address_for(self, user):
        return str(user.pk)

    def send(self, recipient):
        return True


class EmailBackend(NotificationBackend):
    channel = "email"

    def address_for(self, user):
        return user.email or ""

    def send(self, recipient):
        if not recipient.address:
            return False
        send_mail(
            subject=recipient.notification.title,
            message=recipient.notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.address],
            fail_silently=False,
        )
        return True


class NullBackend(NotificationBackend):
    """Records the attempt without sending.

    This is the default for SMS, WhatsApp and push so the rest of the system
    can raise those notifications today and a real provider can be dropped in
    later without touching any caller.
    """

    channel = "null"

    def address_for(self, user):
        return getattr(user, "phone", "") or ""

    def send(self, recipient):
        logger.info(
            "No provider configured for %s; notification %s not transmitted.",
            recipient.channel,
            recipient.pk,
        )
        return False


def get_backend(channel):
    """Instantiate the configured backend for a channel, or ``None``."""
    path = settings.NOTIFICATION_BACKENDS.get(channel)
    if not path:
        return None
    try:
        return import_string(path)()
    except ImportError:
        logger.exception("Notification backend %s could not be loaded.", path)
        return None


def deliver(recipient):
    """Send one recipient row and record the outcome on it."""
    from .models import NotificationRecipient

    backend = get_backend(recipient.channel)
    recipient.attempts += 1

    if backend is None:
        recipient.status = NotificationRecipient.Status.SKIPPED
        recipient.error_message = "No backend configured."
        recipient.save(update_fields=["status", "error_message", "attempts", "updated_at"])
        return False

    try:
        ok = backend.send(recipient)
    except Exception as error:  # pragma: no cover - transport failures vary
        logger.exception("Notification %s failed.", recipient.pk)
        recipient.status = NotificationRecipient.Status.FAILED
        recipient.error_message = str(error)[:500]
        recipient.save(update_fields=["status", "error_message", "attempts", "updated_at"])
        return False

    if ok:
        recipient.status = NotificationRecipient.Status.SENT
        recipient.sent_at = timezone.now()
        recipient.error_message = ""
    else:
        recipient.status = NotificationRecipient.Status.SKIPPED
    recipient.save(
        update_fields=["status", "sent_at", "error_message", "attempts", "updated_at"]
    )
    return ok
