"""Tenant information available to every template."""

from apps.accounts.rbac import accessible_branches


def tenant_context(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {
            "current_organization": None,
            "current_branch": None,
            "available_branches": [],
        }
    return {
        "current_organization": getattr(request, "organization", None),
        "current_branch": getattr(request, "active_branch", None),
        "available_branches": accessible_branches(user),
    }
