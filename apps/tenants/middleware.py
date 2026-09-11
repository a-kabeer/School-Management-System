"""Resolves the organization and branch every request is scoped to.

The active branch is read from the session and then *re-verified* against
``UserBranchAccess`` on every request. A session value that is no longer
authorized is dropped rather than trusted.
"""

from threading import local

from apps.core.constants import ACTIVE_BRANCH_SESSION_KEY

_state = local()


def get_current_organization():
    return getattr(_state, "organization", None)


def get_current_branch():
    return getattr(_state, "branch", None)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        organization = None
        branch = None

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            organization = user.organization
            branch = self._resolve_branch(request, user)

        request.organization = organization
        request.active_branch = branch
        _state.organization = organization
        _state.branch = branch
        try:
            return self.get_response(request)
        finally:
            _state.organization = None
            _state.branch = None

    @staticmethod
    def _resolve_branch(request, user):
        from apps.accounts.rbac import accessible_branches
        from apps.tenants.models import Branch

        branches = accessible_branches(user)
        session_branch_id = request.session.get(ACTIVE_BRANCH_SESSION_KEY)

        if session_branch_id:
            branch = branches.filter(pk=session_branch_id).first()
            if branch is not None:
                return branch
            # Access was revoked (or the id was tampered with) - forget it.
            request.session.pop(ACTIVE_BRANCH_SESSION_KEY, None)

        default_access = (
            user.branch_accesses.filter(is_active=True, is_default=True)
            .select_related("branch", "branch__organization")
            .first()
        )
        branch = default_access.branch if default_access else branches.first()
        if branch is None and user.is_superuser:
            branch = Branch.objects.filter(is_active=True).first()
        if branch is not None:
            request.session[ACTIVE_BRANCH_SESSION_KEY] = str(branch.pk)
        return branch
