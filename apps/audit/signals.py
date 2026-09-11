"""Authentication signals.

Model CRUD is logged from the service layer, where the actor, branch and
request are known. Only the auth signals are handled here, because Django
raises them before any of our code runs.
"""

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

from .services import log_activity


@receiver(user_logged_in)
def on_logged_in(sender, request, user, **kwargs):
    log_activity(action="login", request=request, user=user)


@receiver(user_logged_out)
def on_logged_out(sender, request, user, **kwargs):
    if user is not None:
        log_activity(action="logout", request=request, user=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    log_activity(
        action="login_failed",
        request=request,
        metadata={"username": str(credentials.get("username", ""))[:150]},
    )
