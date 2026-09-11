"""Subscription limits and usage."""

from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import FeatureUsage, Subscription


def current_subscription(organization):
    if organization is None:
        return None
    return (
        Subscription.objects.filter(
            organization=organization,
            status__in=[
                Subscription.Status.TRIAL,
                Subscription.Status.ACTIVE,
                Subscription.Status.PAST_DUE,
            ],
        )
        .select_related("plan")
        .first()
    )


def plan_limits(organization):
    """Current usage against the plan's limits, for the subscription page."""
    from apps.accounts.models import User
    from apps.students.models import Student
    from apps.tenants.models import Branch

    subscription = current_subscription(organization)
    if subscription is None:
        return None

    plan = subscription.plan
    used = {
        "branches": Branch.objects.filter(organization=organization).count(),
        "students": Student.objects.filter(
            organization=organization, status=Student.Status.ACTIVE
        ).count(),
        "users": User.objects.filter(organization=organization, is_active=True).count(),
    }
    limits = {
        "branches": plan.max_branches,
        "students": plan.max_students,
        "users": plan.max_users,
    }
    return {
        "subscription": subscription,
        "rows": [
            {
                "metric": metric,
                "used": used[metric],
                "limit": limits[metric],
                "exceeded": limits[metric] is not None and used[metric] > limits[metric],
                "percent": (
                    round(used[metric] / limits[metric] * 100, 1)
                    if limits[metric]
                    else None
                ),
            }
            for metric in ("branches", "students", "users")
        ],
        "days_remaining": (subscription.end_date - timezone.localdate()).days,
    }


def has_feature(organization, feature):
    """Feature switches let a plan turn a module off without code changes."""
    subscription = current_subscription(organization)
    if subscription is None:
        return False
    return bool(subscription.plan.features.get(feature, True))


@transaction.atomic
def record_usage(organization, metric, amount=1, month=None):
    """Increment a metered counter (SMS, WhatsApp) for the month."""
    subscription = current_subscription(organization)
    if subscription is None:
        return None

    month = month or timezone.localdate().replace(day=1)
    limits = {
        "sms": subscription.plan.monthly_sms_limit,
        "whatsapp": subscription.plan.monthly_whatsapp_limit,
    }
    usage, _created = FeatureUsage.objects.select_for_update().get_or_create(
        subscription=subscription,
        metric=metric,
        period_month=month,
        defaults={"organization": organization, "limit": limits.get(metric)},
    )
    usage.used += amount
    usage.save(update_fields=["used", "updated_at"])
    return usage


def expire_due_subscriptions(today: date | None = None):
    """Mark subscriptions past their end date as expired."""
    today = today or timezone.localdate()
    return Subscription.objects.filter(
        end_date__lt=today,
        status__in=[Subscription.Status.TRIAL, Subscription.Status.ACTIVE],
    ).update(status=Subscription.Status.EXPIRED)
