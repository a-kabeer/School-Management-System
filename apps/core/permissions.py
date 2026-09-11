"""Reusable authorization utilities.

Authorization is expressed as permission codenames resolved through roles, so
no view ever asks "is this user a Teacher?". Adding a role is a database
change; it never requires editing application code.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

#: Custom (non-model) permissions attached to apps.core.models via a stub
#: model. These cover module entry points, financial operations and reports -
#: the things Django's per-model permissions do not describe on their own.
MODULE_PERMISSIONS = [
    ("access_dashboard", _("Can access the dashboard")),
    ("access_academics", _("Can access academics")),
    ("access_students", _("Can access students")),
    ("access_staff", _("Can access staff")),
    ("access_attendance", _("Can access attendance")),
    ("access_hifz", _("Can access hifz")),
    ("access_fees", _("Can access fees")),
    ("access_finance", _("Can access finance")),
    ("access_payroll", _("Can access payroll")),
    ("access_exams", _("Can access exams")),
    ("access_parents", _("Can access the parent portal")),
    ("access_notifications", _("Can access notifications")),
    ("access_reports", _("Can access reports")),
    ("access_subscriptions", _("Can access subscriptions")),
    ("access_audit", _("Can access audit logs")),
    ("access_settings", _("Can access administrative settings")),
    ("collect_fee_payment", _("Can collect fee payments")),
    ("refund_fee_payment", _("Can refund fee payments")),
    ("waive_fee", _("Can waive or discount fees")),
    ("post_journal_entry", _("Can post finance journal entries")),
    ("run_payroll", _("Can run payroll")),
    ("publish_exam_result", _("Can publish exam results")),
    ("restore_record", _("Can restore deleted records")),
    ("export_report", _("Can export reports")),
    ("import_data", _("Can import data")),
    ("manage_roles", _("Can manage roles and permissions")),
    ("manage_branches", _("Can manage branches")),
    ("switch_branch", _("Can switch between branches")),
    ("view_all_branches", _("Can view data across all accessible branches")),
]

MODULE_PERMISSION_CODENAMES = [codename for codename, _label in MODULE_PERMISSIONS]


def perm(codename):
    """Fully qualify a core module permission codename."""
    return f"core.{codename}"


def user_has_permission(user, permission, branch=None):
    """True when ``user`` holds ``permission``, optionally within ``branch``.

    Superusers pass everything. Everyone else is checked against the
    permissions their active roles grant.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True

    from apps.accounts.rbac import permissions_for_user

    if branch is None:
        from apps.tenants.middleware import get_current_branch

        branch = get_current_branch()
    return permission in permissions_for_user(user, branch)


def user_has_any_permission(user, permissions, branch=None):
    return any(user_has_permission(user, p, branch) for p in permissions)


def require_permission(user, permission, branch=None):
    """Raise :class:`PermissionDenied` unless the user holds ``permission``."""
    if not user_has_permission(user, permission, branch):
        raise PermissionDenied(_("You do not have permission to perform this action."))


def permission_required(permission, raise_exception=True):
    """Function-view decorator enforcing a single permission."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            from django.contrib.auth.views import redirect_to_login

            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not user_has_permission(
                request.user, permission, getattr(request, "active_branch", None)
            ):
                if raise_exception:
                    raise PermissionDenied(
                        _("You do not have permission to view this page.")
                    )
                return redirect_to_login(request.get_full_path())
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class PermissionRequiredMixin:
    """Class-based-view counterpart of :func:`permission_required`.

    Set ``required_permission`` (or ``required_permissions`` for "any of").
    """

    required_permission = None
    required_permissions = ()

    def get_required_permissions(self):
        if self.required_permission:
            return (self.required_permission,)
        return tuple(self.required_permissions)

    def dispatch(self, request, *args, **kwargs):
        from django.contrib.auth.views import redirect_to_login

        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        required = self.get_required_permissions()
        if required:
            branch = getattr(request, "active_branch", None)
            if not user_has_any_permission(request.user, required, branch):
                raise PermissionDenied(
                    _("You do not have permission to view this page.")
                )
        return super().dispatch(request, *args, **kwargs)
