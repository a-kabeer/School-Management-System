"""Tenant service layer."""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.constants import ACTIVE_BRANCH_SESSION_KEY


@transaction.atomic
def switch_branch(request, branch_id):
    """Move the session to another branch the user is authorized for.

    Authorization is proven server-side from ``UserBranchAccess``; the id in
    the request is only a lookup key, never a grant.
    """
    from apps.accounts.rbac import accessible_branches
    from apps.audit.services import log_activity

    user = request.user
    branch = accessible_branches(user).filter(pk=branch_id).first()
    if branch is None:
        raise PermissionDenied(_("You do not have access to that branch."))

    previous = getattr(request, "active_branch", None)
    request.session[ACTIVE_BRANCH_SESSION_KEY] = str(branch.pk)
    request.active_branch = branch

    log_activity(
        request=request,
        action="branch_change",
        instance=branch,
        branch=branch,
        previous_values={"branch": str(previous) if previous else None},
        new_values={"branch": str(branch)},
    )
    return branch


@transaction.atomic
def create_branch(*, organization, actor, **fields):
    from apps.audit.services import log_activity, snapshot
    from apps.tenants.models import Branch

    branch = Branch.objects.create(organization=organization, **fields)
    log_activity(
        user=actor,
        organization=organization,
        branch=branch,
        action="create",
        instance=branch,
        new_values=snapshot(branch),
    )
    return branch
