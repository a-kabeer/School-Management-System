"""Unread badge for the navbar."""

from .services import unread_count


def unread_notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"unread_notifications": 0}
    return {"unread_notifications": unread_count(user)}
