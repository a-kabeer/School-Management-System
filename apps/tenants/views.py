from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin
from apps.core.utils import safe_redirect_target
from django.views.generic import UpdateView

from .forms import BranchForm, OrganizationForm
from .models import Branch
from .services import switch_branch


@require_POST
@login_required
def switch_branch_view(request):
    """Change the working branch. Rejects any branch the user cannot enter."""
    branch_id = request.POST.get("branch")
    if not branch_id:
        return HttpResponseBadRequest("branch is required")

    try:
        branch = switch_branch(request, branch_id)
    except PermissionDenied:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": str(_("Branch not available."))}, status=403)
        raise

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"branch": branch.name, "id": str(branch.pk)})

    messages.success(request, _("Now working in %(branch)s.") % {"branch": branch.name})
    target = safe_redirect_target(
        request, request.POST.get("next"), fallback=str(reverse_lazy("core:dashboard"))
    )
    return redirect(target)


class BranchListView(TenantListView):
    model = Branch
    required_permission = "core.access_settings"
    create_permission = "core.manage_branches"
    requires_branch = False
    template_name = "tenants/branch_list.html"
    page_title = _("Branches")
    ordering = ["name"]
    create_url_name = "tenants:branch_create"
    update_url_name = "tenants:branch_update"
    filter_spec = FilterSpec(search_fields=("name", "code", "city"))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Code"), "field": "code"},
        {"label": _("City"), "field": "city"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )

    def get_queryset(self):
        # Branch is the tenancy anchor itself, so it is filtered by the
        # organization and the user's access list rather than by `branch`.
        from apps.accounts.rbac import accessible_branches

        queryset = accessible_branches(self.request.user)
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        return queryset.order_by("name")


class BranchCreateView(TenantCreateView):
    model = Branch
    form_class = BranchForm
    required_permission = "core.manage_branches"
    requires_branch = False
    success_url = reverse_lazy("tenants:branch_list")
    page_title = _("New Branch")

    def form_valid(self, form):
        response = super().form_valid(form)
        # The creator must be able to enter the branch they just opened.
        from apps.accounts.models import UserBranchAccess

        UserBranchAccess.objects.get_or_create(
            user=self.request.user, branch=self.object, defaults={"is_active": True}
        )
        return response


class BranchUpdateView(TenantUpdateView):
    model = Branch
    form_class = BranchForm
    required_permission = "core.manage_branches"
    requires_branch = False
    success_url = reverse_lazy("tenants:branch_list")
    page_title = _("Edit Branch")

    def get_queryset(self):
        from apps.accounts.rbac import accessible_branches

        return accessible_branches(self.request.user)


class OrganizationUpdateView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, UpdateView
):
    form_class = OrganizationForm
    required_permission = "core.access_settings"
    requires_branch = False
    template_name = "components/object_form.html"
    success_url = reverse_lazy("core:dashboard")
    page_title = _("Organization Profile")

    def get_object(self, queryset=None):
        organization = self.request.user.organization
        if organization is None:
            raise PermissionDenied(_("No organization is attached to your account."))
        return organization

    def form_valid(self, form):
        from apps.audit.services import log_activity, snapshot

        response = super().form_valid(form)
        log_activity(
            request=self.request,
            action="settings_change",
            instance=self.object,
            new_values=snapshot(self.object),
        )
        messages.success(self.request, _("Organization updated."))
        return response
