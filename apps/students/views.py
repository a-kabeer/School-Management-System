from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from apps.academics.models import SchoolClass
from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantDeleteView,
    TenantDetailView,
    TenantListView,
    TenantRestoreView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin

from .forms import (
    EnrollmentForm,
    GuardianForm,
    StudentDocumentForm,
    StudentForm,
    StudentGuardianForm,
    StudentStatusForm,
    StudentTransferForm,
)
from .models import Guardian, Student, StudentDocument, StudentEnrollment, StudentGuardian
from .selectors import search_students, student_detail, students_for
from .services import admit_student, change_student_status, transfer_student

STUDENTS = "core.access_students"


class StudentListView(TenantListView):
    model = Student
    required_permission = STUDENTS
    create_permission = "students.add_student"
    template_name = "students/student_list.html"
    page_title = _("Students")
    ordering = ["full_name"]
    exportable = True
    create_url_name = "students:student_create"
    detail_url_name = "students:student_detail"
    update_url_name = "students:student_update"
    filter_spec = FilterSpec(
        search_fields=("full_name", "admission_no", "father_name", "phone"),
        choices={
            "status": "status",
            "school_class": "enrollments__school_class_id",
            "gender": "gender",
        },
    )
    table_columns = (
        {"label": _("Admission #"), "field": "admission_no"},
        {"label": _("Name"), "field": "full_name"},
        {"label": _("Father"), "field": "father_name"},
        {"label": _("Class"), "field": "current_class_display"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )

    def get_list_queryset(self):
        queryset = students_for(self.request.user, self.active_branch)
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        if self.request.GET.get("school_class"):
            queryset = queryset.filter(enrollments__is_current=True).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_selects"] = context.get("filter_selects", []) + [
            {
                "param": "status",
                "label": _("Status"),
                "options": Student.Status.choices,
                "value": self.request.GET.get("status", ""),
            },
            {
                "param": "school_class",
                "label": _("Class"),
                "options": [
                    (str(c.pk), c.name)
                    for c in SchoolClass.objects.for_user(
                        self.request.user, self.active_branch
                    ).filter(is_active=True)
                ],
                "value": self.request.GET.get("school_class", ""),
            },
        ]
        return context


class StudentDetailView(TenantDetailView):
    model = Student
    required_permission = STUDENTS
    template_name = "students/student_detail.html"

    def get_object(self, queryset=None):
        student = student_detail(self.request.user, self.kwargs["pk"], self.active_branch)
        if student is None:
            raise Http404(_("Record not found."))
        return student

    def get_page_title(self):
        return self.object.full_name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.object
        context["enrollments"] = student.enrollments.all()
        context["guardians"] = student.guardian_links.all()
        context["documents"] = student.documents.all()
        context["status_history"] = student.status_history.all()[:10]
        context["invoices"] = student.invoices.order_by("-issue_date")[:10]
        context["hifz_profile"] = getattr(student, "hifz_profile", None)
        return context


class StudentCreateView(TenantCreateView):
    model = Student
    form_class = StudentForm
    required_permission = "students.add_student"
    page_title = _("New Admission")

    def form_valid(self, form):
        data = form.cleaned_data
        placement = {
            key: data.pop(key, None)
            for key in ("academic_year", "school_class", "section", "roll_number")
        }
        fields = {
            key: value
            for key, value in data.items()
            if key in {f.name for f in Student._meta.fields}
        }
        student, _enrollment = admit_student(
            branch=self.active_branch,
            academic_year=placement["academic_year"],
            school_class=placement["school_class"],
            section=placement["section"],
            roll_number=placement["roll_number"] or "",
            actor=self.request.user,
            request=self.request,
            **fields,
        )
        self.object = student
        messages.success(
            self.request,
            _("%(name)s admitted with number %(no)s.")
            % {"name": student.full_name, "no": student.admission_no},
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("students:student_detail", args=[self.object.pk])


class StudentUpdateView(TenantUpdateView):
    model = Student
    form_class = StudentForm
    required_permission = "students.change_student"
    page_title = _("Edit Student")

    def get_success_url(self):
        return reverse("students:student_detail", args=[self.object.pk])


class StudentDeleteView(TenantDeleteView):
    model = Student
    required_permission = "students.delete_student"
    success_url = reverse_lazy("students:student_list")
    page_title = _("Delete Student")


class StudentArchiveListView(TenantListView):
    """Deleted students, so an administrator can put one back."""

    model = Student
    required_permission = "core.restore_record"
    page_title = _("Deleted Students")
    ordering = ["full_name"]
    filter_spec = FilterSpec(search_fields=("full_name", "admission_no"))
    table_columns = (
        {"label": _("Admission #"), "field": "admission_no"},
        {"label": _("Name"), "field": "full_name"},
        {"label": _("Deleted"), "field": "deleted_at", "type": "datetime"},
    )
    template_name = "students/archive_list.html"
    row_actions_template = "students/_restore_action.html"
    empty_message = _("Nothing has been deleted")

    def get_base_queryset(self):
        return Student.all_objects.filter(is_deleted=True)


class StudentRestoreView(TenantRestoreView):
    model = Student
    success_url_name = "students:student_archive"


class StudentStatusView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = StudentStatusForm
    template_name = "components/object_form.html"
    required_permission = "students.change_student"
    page_title = _("Change Student Status")

    def get_student(self):
        return get_object_or_404(
            Student.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )

    def form_valid(self, form):
        student = self.get_student()
        change_student_status(
            student=student,
            new_status=form.cleaned_data["status"],
            effective_date=form.cleaned_data["effective_date"],
            reason=form.cleaned_data.get("reason", ""),
            actor=self.request.user,
            request=self.request,
        )
        messages.success(self.request, _("Status updated."))
        return redirect("students:student_detail", pk=student.pk)


class StudentTransferView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = StudentTransferForm
    template_name = "components/object_form.html"
    required_permission = "students.change_student"
    page_title = _("Transfer Student")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["branch"] = self.active_branch
        return kwargs

    def form_valid(self, form):
        student = get_object_or_404(
            Student.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        transfer_student(
            student=student,
            school_class=form.cleaned_data["school_class"],
            section=form.cleaned_data.get("section"),
            moved_on=form.cleaned_data["moved_on"],
            reason=form.cleaned_data.get("reason", ""),
            actor=self.request.user,
            request=self.request,
        )
        messages.success(self.request, _("Student transferred."))
        return redirect("students:student_detail", pk=student.pk)


class GuardianListView(TenantListView):
    model = Guardian
    required_permission = STUDENTS
    create_permission = "students.add_guardian"
    page_title = _("Guardians")
    ordering = ["full_name"]
    create_url_name = "students:guardian_create"
    update_url_name = "students:guardian_update"
    filter_spec = FilterSpec(search_fields=("full_name", "phone", "national_id"))
    table_columns = (
        {"label": _("Name"), "field": "full_name"},
        {"label": _("Relation"), "field": "relation", "type": "choice"},
        {"label": _("Phone"), "field": "phone"},
        {"label": _("Email"), "field": "email"},
    )


class GuardianCreateView(TenantCreateView):
    model = Guardian
    form_class = GuardianForm
    required_permission = "students.add_guardian"
    success_url = reverse_lazy("students:guardian_list")
    page_title = _("New Guardian")


class GuardianUpdateView(TenantUpdateView):
    model = Guardian
    form_class = GuardianForm
    required_permission = "students.change_guardian"
    success_url = reverse_lazy("students:guardian_list")
    page_title = _("Edit Guardian")


class StudentGuardianCreateView(TenantCreateView):
    model = StudentGuardian
    form_class = StudentGuardianForm
    required_permission = "students.add_studentguardian"
    success_url = reverse_lazy("students:student_list")
    page_title = _("Link Guardian")


class DocumentCreateView(TenantCreateView):
    model = StudentDocument
    form_class = StudentDocumentForm
    required_permission = "students.add_studentdocument"
    success_url = reverse_lazy("students:student_list")
    page_title = _("Upload Document")


class EnrollmentListView(TenantListView):
    model = StudentEnrollment
    required_permission = STUDENTS
    create_permission = "students.add_studentenrollment"
    page_title = _("Enrollments")
    select_related = ("student", "school_class", "section", "academic_year")
    ordering = ["-start_date"]
    create_url_name = "students:enrollment_create"
    update_url_name = "students:enrollment_update"
    filter_spec = FilterSpec(
        search_fields=("student__full_name", "student__admission_no", "roll_number"),
        choices={"school_class": "school_class_id"},
    )
    table_columns = (
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Roll #"), "field": "roll_number"},
        {"label": _("Current"), "field": "is_current", "type": "bool"},
    )


class EnrollmentCreateView(TenantCreateView):
    model = StudentEnrollment
    form_class = EnrollmentForm
    required_permission = "students.add_studentenrollment"
    success_url = reverse_lazy("students:enrollment_list")
    page_title = _("New Enrollment")


class EnrollmentUpdateView(TenantUpdateView):
    model = StudentEnrollment
    form_class = EnrollmentForm
    required_permission = "students.change_studentenrollment"
    success_url = reverse_lazy("students:enrollment_list")
    page_title = _("Edit Enrollment")


def student_search_api(request):
    """Type-ahead endpoint. Scoped to the caller's branch, like every view."""
    from apps.core.permissions import user_has_permission

    if not request.user.is_authenticated or not user_has_permission(
        request.user, STUDENTS, getattr(request, "active_branch", None)
    ):
        return JsonResponse({"results": []}, status=403)

    results = search_students(
        request.user, request.GET.get("q"), getattr(request, "active_branch", None)
    )
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(s.pk),
                    "text": f"{s.full_name} ({s.admission_no})",
                    "class": s.current_class_display,
                }
                for s in results
            ]
        }
    )
