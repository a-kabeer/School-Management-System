from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, TemplateView

from apps.core.filters import FilterSpec
from apps.core.mixins import BreadcrumbMixin, TenantListView, TenantUpdateView
from apps.core.permissions import PermissionRequiredMixin

from .forms import ParentRequestForm, ParentRequestResponseForm
from .models import ParentPortalProfile, ParentRequest
from .selectors import (
    accessible_students,
    child_attendance,
    child_hifz,
    child_invoices,
    child_payments,
    child_results,
    get_child,
    guardian_for,
)


class ParentPortalMixin(LoginRequiredMixin, BreadcrumbMixin):
    """Base for portal pages: requires a guardian record on the account."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and guardian_for(request.user) is None:
            raise PermissionDenied(_("This area is for parent accounts."))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["children"] = accessible_students(self.request.user)
        context["guardian"] = guardian_for(self.request.user)
        return context


class PortalHomeView(ParentPortalMixin, TemplateView):
    template_name = "parents/portal_home.html"
    page_title = _("My Children")

    def get(self, request, *args, **kwargs):
        profile = ParentPortalProfile.objects.filter(
            guardian=guardian_for(request.user)
        ).first()
        if profile is not None:
            profile.last_seen_at = timezone.now()
            profile.save(update_fields=["last_seen_at", "updated_at"])
        return super().get(request, *args, **kwargs)


class ChildDetailView(ParentPortalMixin, TemplateView):
    template_name = "parents/child_detail.html"

    def get_page_title(self):
        return getattr(self, "child", None) and self.child.full_name or _("Child")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.child = get_child(self.request.user, self.kwargs["pk"])
        hifz_profile, hifz_progress = child_hifz(self.request.user, self.child)
        context.update(
            {
                "child": self.child,
                "attendance": child_attendance(self.request.user, self.child),
                "invoices": child_invoices(self.request.user, self.child),
                "payments": child_payments(self.request.user, self.child),
                "results": child_results(self.request.user, self.child),
                "hifz_profile": hifz_profile,
                "hifz_progress": hifz_progress,
                "page_title": self.child.full_name,
            }
        )
        return context


class ParentRequestCreateView(ParentPortalMixin, CreateView):
    model = ParentRequest
    form_class = ParentRequestForm
    template_name = "components/object_form.html"
    success_url = reverse_lazy("parents:portal_home")
    page_title = _("New Request")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        guardian = guardian_for(self.request.user)
        form.instance.guardian = guardian
        form.instance.branch = form.cleaned_data["student"].branch
        form.instance.organization = form.instance.branch.organization
        response = super().form_valid(form)

        from apps.audit.services import log_activity, snapshot

        log_activity(
            action="create",
            request=self.request,
            instance=self.object,
            new_values=snapshot(self.object),
        )
        messages.success(self.request, _("Your request has been submitted."))
        return response


# --------------------------------------------------------------------------
# Staff-facing screens
# --------------------------------------------------------------------------
class GuardianAccountListView(TenantListView):
    """Back-office view of parent accounts and their children."""

    model = ParentPortalProfile
    required_permission = "core.access_parents"
    create_permission = None
    page_title = _("Parent Accounts")
    select_related = ("guardian", "default_student")
    ordering = ["guardian__full_name"]
    filter_spec = FilterSpec(
        search_fields=("guardian__full_name", "guardian__phone")
    )
    table_columns = (
        {"label": _("Guardian"), "field": "guardian.full_name"},
        {"label": _("Phone"), "field": "guardian.phone"},
        {"label": _("Default Child"), "field": "default_student.full_name"},
        {"label": _("Last Seen"), "field": "last_seen_at", "type": "datetime"},
    )


class ParentRequestListView(TenantListView):
    model = ParentRequest
    required_permission = "core.access_parents"
    page_title = _("Parent Requests")
    select_related = ("guardian", "student", "responded_by")
    ordering = ["-created_at"]
    update_url_name = "parents:request_respond"
    filter_spec = FilterSpec(
        search_fields=("subject", "student__full_name", "guardian__full_name"),
        choices={"status": "status", "request_type": "request_type"},
        selects={
            "status": {"label": _("Status"), "options": ParentRequest.Status.choices},
            "request_type": {
                "label": _("Type"),
                "options": ParentRequest.RequestType.choices,
            },
        },
    )
    table_columns = (
        {"label": _("Received"), "field": "created_at", "type": "datetime"},
        {"label": _("Guardian"), "field": "guardian.full_name"},
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Type"), "field": "request_type", "type": "choice"},
        {"label": _("Subject"), "field": "subject"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class ParentRequestRespondView(TenantUpdateView):
    model = ParentRequest
    form_class = ParentRequestResponseForm
    required_permission = "parents.change_parentrequest"
    success_url = reverse_lazy("parents:request_list")
    page_title = _("Respond to Request")

    def form_valid(self, form):
        form.instance.responded_by = self.request.user
        form.instance.responded_at = timezone.now()
        return super().form_valid(form)
