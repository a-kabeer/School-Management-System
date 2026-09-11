"""Dashboard, health check and shared error handlers."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from . import idcards
from .dashboard import build_dashboard
from .mixins import ActiveBranchMixin
from .permissions import PermissionRequiredMixin


def health(request):
    """Unauthenticated liveness probe for the platform."""
    return JsonResponse({"status": "ok"})


class DashboardView(PermissionRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"
    required_permission = "core.access_dashboard"

    def dispatch(self, request, *args, **kwargs):
        # Parents get their own portal; the staff dashboard would be empty for
        # them and its queries are not child-scoped.
        if (
            request.user.is_authenticated
            and getattr(request.user, "is_parent_account", False)
            and not request.user.is_superuser
        ):
            return redirect("parents:portal_home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = getattr(self.request, "active_branch", None)
        context["page_title"] = _("Dashboard")
        context["board"] = build_dashboard(self.request.user, branch)
        context["today"] = timezone.localdate()
        return context


@login_required
def home(request):
    return redirect("core:dashboard")


# --------------------------------------------------------------------------
# ID cards
# --------------------------------------------------------------------------
class IdCardMixin(PermissionRequiredMixin):
    """Shared plumbing for the card screens: language, branding, print mode."""

    template_name = "core/idcards.html"

    def get_language(self):
        requested = self.request.GET.get("lang", "")
        allowed = {code for code, _label in idcards.LANGUAGES}
        return requested if requested in allowed else "en"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = getattr(self.request, "active_branch", None)
        language = self.get_language()
        context.update(
            {
                "branding": idcards.branding_for(self.request.user.organization, branch),
                "card_language": language,
                "card_is_rtl": language in idcards.RTL_LANGUAGES,
                "languages": idcards.LANGUAGES,
                "print_mode": self.request.GET.get("print") == "1",
                "show_back": self.request.GET.get("back") == "1",
            }
        )
        return context


class StudentIdCardView(IdCardMixin, ActiveBranchMixin, TemplateView):
    required_permission = "core.access_students"

    def get_context_data(self, **kwargs):
        from apps.students.models import Student

        context = super().get_context_data(**kwargs)
        language = context["card_language"]
        student = get_object_or_404(
            Student.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        context["cards"] = [idcards.student_card(student, self.request, language)]
        context["page_title"] = _("ID Card")
        context["page_subtitle"] = student.full_name
        context["back_url"] = reverse("students:student_detail", args=[student.pk])
        return context


class StaffIdCardView(IdCardMixin, ActiveBranchMixin, TemplateView):
    required_permission = "core.access_staff"

    def get_context_data(self, **kwargs):
        from apps.staff.models import Staff

        context = super().get_context_data(**kwargs)
        language = context["card_language"]
        staff = get_object_or_404(
            Staff.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        context["cards"] = [idcards.staff_card(staff, self.request, language)]
        context["page_title"] = _("ID Card")
        context["page_subtitle"] = staff.full_name
        context["back_url"] = reverse("staff:staff_detail", args=[staff.pk])
        return context


class BulkStudentCardsView(IdCardMixin, ActiveBranchMixin, TemplateView):
    """A printable sheet of student cards for a class."""

    required_permission = "core.access_students"

    def get_context_data(self, **kwargs):
        from apps.academics.models import SchoolClass
        from apps.students.models import Student
        from apps.students.selectors import students_for

        context = super().get_context_data(**kwargs)
        language = context["card_language"]
        classes = SchoolClass.objects.for_user(
            self.request.user, self.active_branch
        ).filter(is_active=True)
        chosen = classes.filter(pk=self.request.GET.get("school_class")).first()

        students = students_for(self.request.user, self.active_branch).filter(
            status=Student.Status.ACTIVE
        )
        if chosen is not None:
            students = students.filter(
                enrollments__school_class=chosen, enrollments__is_current=True
            )
        # A print run is bounded: a sheet of thousands helps nobody and would
        # build thousands of QR codes in one request.
        students = students.order_by("full_name")[:120]

        context["cards"] = [
            idcards.student_card(student, self.request, language)
            for student in students
        ]
        context["classes"] = classes
        context["selected_class"] = chosen
        context["bulk"] = True
        context["bulk_kind"] = "student"
        context["page_title"] = _("Student ID Cards")
        context["page_subtitle"] = (
            chosen.name if chosen else _("All active students (first 120)")
        )
        context["back_url"] = reverse("students:student_list")
        return context


class BulkStaffCardsView(IdCardMixin, ActiveBranchMixin, TemplateView):
    """A printable sheet of staff cards."""

    required_permission = "core.access_staff"

    def get_context_data(self, **kwargs):
        from apps.staff.models import Staff

        context = super().get_context_data(**kwargs)
        language = context["card_language"]
        staff = (
            Staff.objects.for_user(self.request.user, self.active_branch)
            .filter(status=Staff.Status.ACTIVE)
            .select_related("designation", "department")
            .order_by("full_name")[:120]
        )
        context["cards"] = [idcards.staff_card(member, self.request, language) for member in staff]
        context["bulk"] = True
        context["bulk_kind"] = "staff"
        context["page_title"] = _("Staff ID Cards")
        context["page_subtitle"] = _("All active staff (first 120)")
        context["back_url"] = reverse("staff:staff_list")
        return context


def verify_card(request, kind, pk):
    """Public verification target for a card's QR code.

    It shows only what is already printed on the card face - photo, name, ID,
    class or designation, and whether the card is current. Nothing here is
    private: a person holding the card can read all of it without scanning.
    Anything sensitive (contact details, guardians, dates of birth) is
    deliberately absent.
    """
    from apps.staff.models import Staff
    from apps.students.models import Student

    record = None
    details = []
    if kind == "student":
        record = Student.objects.filter(pk=pk).select_related("branch__organization").first()
        if record is not None:
            enrollment = record.current_enrollment
            details = [
                (_("Student ID"), record.admission_no),
                (_("Class"), enrollment.school_class.name if enrollment else "—"),
                (_("Section"), enrollment.section.name if enrollment and enrollment.section else "—"),
                (_("Academic Session"), enrollment.academic_year.name if enrollment else "—"),
            ]
            valid = record.status == Student.Status.ACTIVE
    elif kind == "staff":
        record = Staff.objects.filter(pk=pk).select_related(
            "branch__organization", "designation", "department"
        ).first()
        if record is not None:
            details = [
                (_("Staff ID"), record.employee_no),
                (_("Designation"), record.designation.name if record.designation
                 else record.get_staff_type_display()),
                (_("Department"), record.department.name if record.department else "—"),
            ]
            valid = record.status == Staff.Status.ACTIVE
    else:
        raise Http404

    if record is None:
        return render(request, "core/verify.html", {"found": False}, status=404)

    from apps.core import idcards as card_module

    return render(
        request,
        "core/verify.html",
        {
            "found": True,
            "kind": kind,
            "record": record,
            "details": details,
            "valid": valid,
            "photo_url": record.photo.url if record.photo else "",
            "branding": card_module.branding_for(
                record.branch.organization, record.branch
            ),
        },
    )


def permission_denied_view(request, exception=None):
    return render(
        request,
        "errors/403.html",
        {"message": str(exception) if exception else _("Access denied.")},
        status=403,
    )


def not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error_view(request):
    return render(request, "errors/500.html", status=500)
