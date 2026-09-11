"""Raising notifications from anywhere in the system.

Modules call :func:`notify`; they never touch a transport. Preferences and
templates are applied here, once.
"""

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .backends import deliver
from .models import (
    Channel,
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)

logger = logging.getLogger(__name__)

# Event keys other modules raise.
EVENT_FEE_DUE = "fee.due"
EVENT_PAYMENT_RECEIVED = "fee.payment_received"
EVENT_ATTENDANCE_ABSENT = "attendance.absent"
EVENT_RESULT_PUBLISHED = "exam.result_published"
EVENT_HIFZ_PROGRESS = "hifz.progress"
EVENT_ANNOUNCEMENT = "general.announcement"


def _channel_enabled(user, event, channel):
    """Preferences: the most specific rule wins, default is enabled."""
    preference = (
        NotificationPreference.objects.filter(user=user, channel=channel)
        .filter(event__in=[event, ""])
        .order_by("-event")
        .first()
    )
    return preference.is_enabled if preference else True


def _render(organization, event, channel, language, context, fallback_title, fallback_body):
    template = (
        NotificationTemplate.objects.filter(
            organization=organization,
            event=event,
            channel=channel,
            language=language,
            is_active=True,
        ).first()
        or NotificationTemplate.objects.filter(
            organization=organization, event=event, channel=channel, is_active=True
        ).first()
    )
    if template is None:
        return fallback_title, fallback_body
    return template.render(context)


@transaction.atomic
def notify(
    *,
    branch,
    event,
    title,
    body,
    users,
    channels=(Channel.IN_APP,),
    context=None,
    link_url="",
    priority=Notification.Priority.NORMAL,
    actor=None,
    send_now=True,
):
    """Create one notification and a recipient row per user per channel."""
    users = [u for u in users if u is not None]
    if not users:
        return None

    notification = Notification.objects.create(
        branch=branch,
        organization=branch.organization,
        event=event,
        title=title[:255],
        body=body,
        priority=priority,
        link_url=link_url[:500],
        context=context or {},
        created_by=actor,
    )

    from .backends import get_backend

    recipients = []
    for user in users:
        for channel in channels:
            if not _channel_enabled(user, event, channel):
                continue
            backend = get_backend(channel)
            address = backend.address_for(user) if backend else ""
            rendered_title, rendered_body = _render(
                branch.organization,
                event,
                channel,
                getattr(user, "preferred_language", "en"),
                context or {},
                title,
                body,
            )
            recipients.append(
                NotificationRecipient(
                    branch=branch,
                    organization=branch.organization,
                    notification=notification,
                    user=user,
                    channel=channel,
                    address=address[:255],
                )
            )
            # Per-recipient rendering is stored on the notification only when
            # a template changed it; in-app readers see the notification body.
            if channel == Channel.IN_APP and (
                rendered_title != title or rendered_body != body
            ):
                notification.title = rendered_title[:255]
                notification.body = rendered_body
                notification.save(update_fields=["title", "body", "updated_at"])

    NotificationRecipient.objects.bulk_create(recipients, ignore_conflicts=True)

    if send_now:
        # Delivery happens after the surrounding transaction commits, so a
        # rolled-back payment never leaves a "payment received" SMS behind.
        stored = list(
            NotificationRecipient.objects.filter(
                notification=notification, status=NotificationRecipient.Status.PENDING
            )
        )
        transaction.on_commit(lambda: [deliver(r) for r in stored])

    return notification


def mark_read(user, recipient_ids=None):
    queryset = NotificationRecipient.objects.filter(
        user=user, channel=Channel.IN_APP
    ).exclude(status=NotificationRecipient.Status.READ)
    if recipient_ids:
        queryset = queryset.filter(pk__in=recipient_ids)
    return queryset.update(status=NotificationRecipient.Status.READ, read_at=timezone.now())


def unread_count(user):
    if user is None or not user.is_authenticated:
        return 0
    return (
        NotificationRecipient.objects.filter(user=user, channel=Channel.IN_APP)
        .exclude(status=NotificationRecipient.Status.READ)
        .count()
    )


# --------------------------------------------------------------------------
# Event helpers used by the other modules
# --------------------------------------------------------------------------
def guardians_of(student):
    """Portal users attached to a student, for parent-facing alerts."""
    from apps.accounts.models import User

    return User.objects.filter(
        guardian_profile__student_links__student=student,
        guardian_profile__student_links__can_view_portal=True,
        is_active=True,
    ).distinct()


def notify_payment_received(*, payment, actor=None):
    users = list(guardians_of(payment.student))
    if not users:
        return None
    return notify(
        branch=payment.branch,
        event=EVENT_PAYMENT_RECEIVED,
        title=_("Payment received"),
        body=_("We have received %(amount)s for %(student)s. Receipt %(receipt)s.")
        % {
            "amount": payment.amount,
            "student": payment.student.full_name,
            "receipt": payment.receipt_number,
        },
        users=users,
        context={
            "amount": str(payment.amount),
            "student": payment.student.full_name,
            "receipt": payment.receipt_number,
        },
        actor=actor,
    )


def notify_absence(*, attendance, actor=None):
    users = list(guardians_of(attendance.student))
    if not users:
        return None
    return notify(
        branch=attendance.branch,
        event=EVENT_ATTENDANCE_ABSENT,
        title=_("Absence recorded"),
        body=_("%(student)s was marked absent on %(date)s.")
        % {"student": attendance.student.full_name, "date": attendance.date},
        users=users,
        context={
            "student": attendance.student.full_name,
            "date": str(attendance.date),
        },
        priority=Notification.Priority.HIGH,
        actor=actor,
    )


def notify_result_published(*, exam, actor=None):
    from apps.accounts.models import User

    users = User.objects.filter(
        guardian_profile__student_links__student__student_exams__exam=exam,
        guardian_profile__student_links__can_view_portal=True,
        is_active=True,
    ).distinct()
    if not users.exists():
        return None
    return notify(
        branch=exam.branch,
        event=EVENT_RESULT_PUBLISHED,
        title=_("Results published"),
        body=_("Results for %(exam)s are now available in the parent portal.")
        % {"exam": exam.name},
        users=list(users),
        context={"exam": exam.name},
        actor=actor,
    )
