from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantDeleteView,
    TenantDetailView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin

from .forms import (
    StaffAssignmentForm,
    StaffDepartmentForm,
    StaffDesignationForm,
    StaffDocumentForm,
    StaffForm,
    StaffStatusForm,
)
from .models import (
    Staff,
    StaffAssignment,
    StaffDepartment,
    StaffDesignation,
    StaffDocument,
)
from .services import change_staff_status

STAFF = "core.access_staff"


class StaffListView(TenantListView):
    model = Staff
    required_permission = STAFF
    create_permission = "staff.add_staff"
    page_title = _("Staff")
    select_related = ("department", "designation")
    ordering = ["full_name"]
    create_url_name = "staff:staff_create"
    detail_url_name = "staff:staff_detail"
    update_url_name = "staff:staff_update"
    filter_spec = FilterSpec(
        search_fields=("full_name", "employee_no", "phone", "email"),
        choices={"status": "status", "staff_type": "staff_type"},
        selects={
            "status": {"label": _("Status"), "options": Staff.Status.choices},
            "staff_type": {"label": _("Type"), "options": Staff.StaffType.choices},
        },
    )
    table_columns = (
        {"label": _("Employee #"), "field": "employee_no"},
        {"label": _("Name"), "field": "full_name"},
        {"label": _("Type"), "field": "staff_type", "type": "choice"},
        {"label": _("Designation"), "field": "designation.name"},
        {"label": _("Phone"), "field": "phone"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class StaffDetailView(TenantDetailView):
    model = Staff
    required_permission = STAFF
    template_name = "staff/staff_detail.html"
    select_related = ("department", "designation", "profile")
    prefetch_related = ("documents", "assignments", "status_history")

    def get_page_title(self):
        return self.object.full_name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["teaching"] = self.object.teaching_assignments.select_related(
            "class_subject__subject", "class_subject__school_class", "section"
        ).filter(is_active=True)
        return context


class StaffCreateView(TenantCreateView):
    model = Staff
    form_class = StaffForm
    required_permission = "staff.add_staff"
    page_title = _("New Staff Member")

    def get_success_url(self):
        return reverse("staff:staff_detail", args=[self.object.pk])


class StaffUpdateView(TenantUpdateView):
    model = Staff
    form_class = StaffForm
    required_permission = "staff.change_staff"
    page_title = _("Edit Staff Member")

    def get_success_url(self):
        return reverse("staff:staff_detail", args=[self.object.pk])


class StaffDeleteView(TenantDeleteView):
    model = Staff
    required_permission = "staff.delete_staff"
    success_url = reverse_lazy("staff:staff_list")
    page_title = _("Delete Staff Member")


class StaffStatusView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = StaffStatusForm
    template_name = "components/object_form.html"
    required_permission = "staff.change_staff"
    page_title = _("Change Staff Status")

    def form_valid(self, form):
        staff = get_object_or_404(
            Staff.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        change_staff_status(
            staff=staff,
            new_status=form.cleaned_data["status"],
            effective_date=form.cleaned_data["effective_date"],
            reason=form.cleaned_data.get("reason", ""),
            actor=self.request.user,
            request=self.request,
        )
        messages.success(self.request, _("Status updated."))
        return redirect("staff:staff_detail", pk=staff.pk)


class DepartmentListView(TenantListView):
    model = StaffDepartment
    required_permission = STAFF
    create_permission = "staff.add_staffdepartment"
    page_title = _("Departments")
    ordering = ["name"]
    create_url_name = "staff:department_create"
    update_url_name = "staff:department_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Description"), "field": "description"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class DepartmentCreateView(TenantCreateView):
    model = StaffDepartment
    form_class = StaffDepartmentForm
    required_permission = "staff.add_staffdepartment"
    success_url = reverse_lazy("staff:department_list")
    page_title = _("New Department")


class DepartmentUpdateView(TenantUpdateView):
    model = StaffDepartment
    form_class = StaffDepartmentForm
    required_permission = "staff.change_staffdepartment"
    success_url = reverse_lazy("staff:department_list")
    page_title = _("Edit Department")


class DesignationListView(TenantListView):
    model = StaffDesignation
    required_permission = STAFF
    create_permission = "staff.add_staffdesignation"
    page_title = _("Designations")
    select_related = ("department",)
    ordering = ["name"]
    create_url_name = "staff:designation_create"
    update_url_name = "staff:designation_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Department"), "field": "department.name"},
        {"label": _("Teaching"), "field": "is_teaching", "type": "bool"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class DesignationCreateView(TenantCreateView):
    model = StaffDesignation
    form_class = StaffDesignationForm
    required_permission = "staff.add_staffdesignation"
    success_url = reverse_lazy("staff:designation_list")
    page_title = _("New Designation")


class DesignationUpdateView(TenantUpdateView):
    model = StaffDesignation
    form_class = StaffDesignationForm
    required_permission = "staff.change_staffdesignation"
    success_url = reverse_lazy("staff:designation_list")
    page_title = _("Edit Designation")


class StaffDocumentCreateView(TenantCreateView):
    model = StaffDocument
    form_class = StaffDocumentForm
    required_permission = "staff.add_staffdocument"
    success_url = reverse_lazy("staff:staff_list")
    page_title = _("Upload Staff Document")


class StaffAssignmentCreateView(TenantCreateView):
    model = StaffAssignment
    form_class = StaffAssignmentForm
    required_permission = "staff.add_staffassignment"
    success_url = reverse_lazy("staff:staff_list")
    page_title = _("New Staff Assignment")
