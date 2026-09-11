"""The single entry point for writing audit records.

Every module calls :func:`log_activity`; none of them build ``ActivityLog``
rows themselves. That keeps redaction, actor resolution and tenancy in one
place instead of repeated (and eventually diverging) per app.
"""

import logging
from decimal import Decimal
from uuid import UUID

from django.db import models

logger = logging.getLogger(__name__)

#: Never written to the log, whatever model they appear on.
SENSITIVE_FIELDS = {
    "password",
    "token",
    "secret",
    "access_token",
    "refresh_token",
    "api_key",
    "session_key",
}

REDACTED = "***"


def _coerce(value):
    """Make a field value JSON-safe without losing precision."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, models.Model):
        return str(value.pk)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def snapshot(instance, fields=None):
    """A redacted, JSON-safe dict of an instance's concrete fields."""
    if instance is None:
        return None

    data = {}
    for field in instance._meta.concrete_fields:
        name = field.name
        if fields is not None and name not in fields:
            continue
        if name.lower() in SENSITIVE_FIELDS:
            data[name] = REDACTED
            continue
        if field.is_relation:
            data[name] = _coerce(getattr(instance, f"{name}_id", None))
        else:
            data[name] = _coerce(getattr(instance, name, None))
    return data


def diff(previous, new):
    """Only the keys whose values actually changed."""
    if not previous or not new:
        return previous, new
    changed = {k for k in new if previous.get(k) != new.get(k)}
    return (
        {k: previous.get(k) for k in changed},
        {k: new.get(k) for k in changed},
    )


def log_activity(
    *,
    action,
    request=None,
    user=None,
    instance=None,
    organization=None,
    branch=None,
    previous_values=None,
    new_values=None,
    metadata=None,
    object_repr=None,
):
    """Write one activity record. Never raises into the caller's transaction."""
    from .models import ActivityLog

    if user is None and request is not None:
        candidate = getattr(request, "user", None)
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            user = candidate

    if organization is None:
        organization = (
            getattr(instance, "organization", None)
            or getattr(user, "organization", None)
            or getattr(request, "organization", None)
        )
    if branch is None:
        branch = getattr(instance, "branch", None) or getattr(
            request, "active_branch", None
        )

    role_name = ""
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            role_name = ", ".join(user.role_names)[:150]
        except Exception:  # pragma: no cover - never block on a label
            role_name = ""

    try:
        return ActivityLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            username=getattr(user, "username", "")[:150] if user else "",
            role_name=role_name,
            organization=organization,
            branch=branch,
            action=action,
            app_label=instance._meta.app_label if instance is not None else "",
            model_name=instance._meta.model_name if instance is not None else "",
            object_id=str(instance.pk) if instance is not None and instance.pk else "",
            object_repr=(object_repr or (str(instance) if instance is not None else ""))[:500],
            previous_values=previous_values,
            new_values=new_values,
            ip_address=getattr(request, "audit_ip", None) if request else None,
            # Django raises the auth signals with a bare HttpRequest whose
            # path and method are None, so each of these needs its own
            # fallback rather than one "is there a request?" check.
            user_agent=(getattr(request, "audit_user_agent", None) or "")[:1000],
            request_path=(getattr(request, "path", None) or "")[:500],
            request_method=(getattr(request, "method", None) or "")[:10],
            metadata=_coerce(metadata or {}),
        )
    except Exception:  # pragma: no cover - auditing must not break the action
        logger.exception("Failed to write activity log for action %s", action)
        return None


def log_model_change(instance, *, request=None, user=None, previous=None, action=None):
    """Convenience wrapper used by service functions around a save."""
    current = snapshot(instance)
    if action is None:
        action = "update" if previous else "create"
    if previous:
        previous, current = diff(previous, current)
    return log_activity(
        action=action,
        request=request,
        user=user,
        instance=instance,
        previous_values=previous,
        new_values=current,
    )
