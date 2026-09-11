"""Account and RBAC service layer."""

from django.contrib.auth.models import Permission
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.constants import SYSTEM_ROLES

from .models import Role, User, UserBranchAccess, UserRole
from .role_presets import ROLE_PRESETS


def _permissions_for_preset(codenames):
    if codenames == "*":
        return Permission.objects.all()
    lookups = []
    for dotted in codenames:
        app_label, codename = dotted.split(".", 1)
        lookups.append((app_label, codename))
    query = Permission.objects.none()
    from django.db.models import Q

    clause = Q()
    for app_label, codename in lookups:
        clause |= Q(content_type__app_label=app_label, codename=codename)
    if clause:
        query = Permission.objects.filter(clause)
    return query


@transaction.atomic
def seed_roles(organization, *, reset=False):
    """Create (or refresh) the standard roles for one organization."""
    created = []
    for name in SYSTEM_ROLES:
        preset = ROLE_PRESETS.get(name, {})
        role, was_created = Role.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={
                "is_system": True,
                "description": preset.get("description", ""),
            },
        )
        if was_created or reset:
            role.permissions.set(_permissions_for_preset(preset.get("permissions", [])))
            created.append(role)
    return created


@transaction.atomic
def create_user(
    *,
    organization,
    username,
    password,
    actor=None,
    roles=(),
    branches=(),
    default_branch=None,
    **fields,
):
    """Create a user with roles and branch access in one transaction."""
    from apps.audit.services import log_activity, snapshot

    from .rbac import assign_role, grant_branch_access

    user = User(organization=organization, username=username, **fields)
    user.set_password(password)
    user.full_clean(exclude=["password"])
    user.save()

    for branch in branches:
        grant_branch_access(
            user, branch, is_default=(branch == default_branch), actor=actor
        )
    for role in roles:
        assign_role(user, role, actor=actor)

    log_activity(
        user=actor,
        organization=organization,
        action="create",
        instance=user,
        new_values=snapshot(user),
    )
    return user


@transaction.atomic
def set_user_roles(user, roles, *, branch=None, actor=None):
    """Replace the user's role assignments for one scope."""
    from apps.audit.services import log_activity

    previous = sorted(
        UserRole.objects.filter(user=user, branch=branch).values_list(
            "role__name", flat=True
        )
    )
    UserRole.objects.filter(user=user, branch=branch).delete()
    for role in roles:
        UserRole.objects.create(user=user, role=role, branch=branch, is_active=True)

    user._permission_cache = None
    log_activity(
        user=actor,
        organization=user.organization,
        branch=branch,
        action="role_change",
        instance=user,
        previous_values={"roles": previous},
        new_values={"roles": sorted(r.name for r in roles)},
    )


@transaction.atomic
def set_branch_access(user, branches, *, actor=None, default_branch=None):
    """Replace the user's branch access list."""
    from apps.audit.services import log_activity

    previous = sorted(
        UserBranchAccess.objects.filter(user=user).values_list("branch__name", flat=True)
    )
    UserBranchAccess.objects.filter(user=user).delete()
    for branch in branches:
        UserBranchAccess.objects.create(
            user=user,
            branch=branch,
            is_active=True,
            is_default=(default_branch is not None and branch.pk == default_branch.pk),
        )

    user._accessible_branch_ids = None
    log_activity(
        user=actor,
        organization=user.organization,
        action="permission_change",
        instance=user,
        previous_values={"branches": previous},
        new_values={"branches": sorted(b.name for b in branches)},
    )


@transaction.atomic
def set_role_permissions(role, permissions, *, actor=None):
    from apps.audit.services import log_activity

    previous = sorted(role.permissions.values_list("codename", flat=True))
    role.permissions.set(permissions)
    log_activity(
        user=actor,
        organization=role.organization,
        action="permission_change",
        instance=role,
        previous_values={"permissions": previous},
        new_values={"permissions": sorted(p.codename for p in permissions)},
    )
    return role
