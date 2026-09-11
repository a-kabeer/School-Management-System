"""Role resolution and branch-access checks.

Everything that answers "may this user do X, here?" lives in this module.
Results are cached on the user object for the life of the request, so a page
with a large sidebar does not re-query permissions for every menu item.
"""

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _


def accessible_branches(user):
    """Every branch the user may enter, as a queryset."""
    from apps.tenants.models import Branch

    if user is None or not getattr(user, "is_authenticated", False):
        return Branch.objects.none()

    if user.is_superuser:
        return Branch.objects.select_related("organization").all()

    if user.organization_id is None:
        return Branch.objects.none()

    return (
        Branch.objects.filter(
            organization_id=user.organization_id,
            is_active=True,
            user_accesses__user=user,
            user_accesses__is_active=True,
        )
        .select_related("organization")
        .distinct()
    )


def accessible_branch_ids(user):
    """Cached set of branch primary keys the user may enter."""
    cached = getattr(user, "_accessible_branch_ids", None)
    if cached is None:
        cached = set(accessible_branches(user).values_list("pk", flat=True))
        user._accessible_branch_ids = cached
    return cached


def user_can_access_branch(user, branch):
    if user is None or not getattr(user, "is_authenticated", False) or branch is None:
        return False
    if user.is_superuser:
        return True
    if user.organization_id != branch.organization_id:
        return False
    return branch.pk in accessible_branch_ids(user)


def require_branch_access(user, branch):
    if not user_can_access_branch(user, branch):
        raise PermissionDenied(_("You are not authorized to access this branch."))


def permissions_for_user(user, branch=None):
    """Permission codenames (``app_label.codename``) the user holds.

    A role assigned without a branch applies everywhere the user can reach; a
    branch-scoped role only counts while working in that branch.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return set()

    if user.is_superuser:
        cached = getattr(user, "_all_permissions_cache", None)
        if cached is None:
            from django.contrib.auth.models import Permission

            cached = {
                f"{app_label}.{codename}"
                for app_label, codename in Permission.objects.values_list(
                    "content_type__app_label", "codename"
                )
            }
            user._all_permissions_cache = cached
        return cached

    branch_key = str(branch.pk) if branch is not None else "__global__"
    cache = getattr(user, "_permission_cache", None)
    if cache is None:
        cache = {}
        user._permission_cache = cache
    if branch_key in cache:
        return cache[branch_key]

    from django.db.models import Q

    from .models import UserRole

    scope = Q(branch__isnull=True)
    if branch is not None:
        scope |= Q(branch=branch)

    codenames = (
        UserRole.objects.filter(user=user, is_active=True, role__is_active=True)
        .filter(scope)
        .values_list(
            "role__permissions__content_type__app_label",
            "role__permissions__codename",
        )
    )
    resolved = {
        f"{app_label}.{codename}"
        for app_label, codename in codenames
        if app_label and codename
    }
    cache[branch_key] = resolved
    return resolved


def user_has_role(user, role_name, branch=None):
    """Present for administrative screens only - never for authorization."""
    from django.db.models import Q

    from .models import UserRole

    scope = Q(branch__isnull=True)
    if branch is not None:
        scope |= Q(branch=branch)
    return (
        UserRole.objects.filter(user=user, role__name=role_name, is_active=True)
        .filter(scope)
        .exists()
    )


def grant_branch_access(user, branch, *, is_default=False, actor=None):
    from apps.audit.services import log_activity

    from .models import UserBranchAccess

    access, created = UserBranchAccess.objects.get_or_create(
        user=user, branch=branch, defaults={"is_default": is_default}
    )
    if not created and not access.is_active:
        access.is_active = True
        access.save(update_fields=["is_active", "updated_at"])
    if is_default and not access.is_default:
        access.is_default = True
        access.save(update_fields=["is_default", "updated_at"])

    user._accessible_branch_ids = None
    if actor is not None:
        log_activity(
            user=actor,
            organization=branch.organization,
            branch=branch,
            action="permission_change",
            instance=access,
            new_values={"user": str(user), "branch": str(branch)},
        )
    return access


def assign_role(user, role, *, branch=None, actor=None):
    from apps.audit.services import log_activity

    from .models import UserRole

    assignment, _created = UserRole.objects.get_or_create(
        user=user, role=role, branch=branch, defaults={"is_active": True}
    )
    user._permission_cache = None
    if actor is not None:
        log_activity(
            user=actor,
            organization=role.organization,
            branch=branch,
            action="role_change",
            instance=assignment,
            new_values={"user": str(user), "role": role.name},
        )
    return assignment
