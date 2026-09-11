from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.core.constants import AttendanceStatus
from apps.core.filters import FilterSpec
from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin, TenantDetailView, TenantListView
from apps.core.permissions import PermissionRequiredMixin
from apps.core.utils import parse_date
from apps.staff.models import Staff
from apps.students.selectors import students_in_class

from .models import AttendanceSession, StaffAttendance, StudentAttendance
from .services import mark_staff_attendance, mark_student_attendance

ATTENDANCE = "core.access_attendance"


class SessionListView(TenantListView):
    model = AttendanceSession
    required_permission = ATTENDANCE
    page_title = _("Attendance Sessions")
    select_related = ("school_class", "section", "taken_by", "academic_year")
    ordering = ["-date"]
    detail_url_name = "attendance:session_detail"
    filter_spec = FilterSpec(
        search_fields=("school_class__name", "section__name"),
        choices={"school_class": "school_class_id"},
        date_field="date",
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Type"), "field": "session_type", "type": "choice"},
        {"label": _("Taken by"), "field": "taken_by.display_name"},
        {"label": _("Locked"), "field": "is_locked", "type": "bool"},
    )


class SessionDetailView(TenantDetailView):
    model = AttendanceSession
    required_permission = ATTENDANCE
    template_name = "attendance/session_detail.html"
    select_related = ("school_class", "section", "academic_year", "taken_by")
    page_title = _("Attendance Session")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["records"] = self.object.records.select_related("student").order_by(
            "student__full_name"
        )
        return context


class MarkAttendanceView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Pick a class/section/date, then submit the whole register at once."""

    template_name = "attendance/mark.html"
    required_permission = "attendance.add_studentattendance"
    page_title = _("Mark Attendance")

    def get_selection(self):
        branch = self.active_branch
        classes = SchoolClass.objects.for_user(self.request.user, branch).filter(
            is_active=True
        )
        sections = Section.objects.for_user(self.request.user, branch).filter(
            is_active=True
        )

        school_class = classes.filter(pk=self.request.GET.get("school_class")).first()
        section = sections.filter(pk=self.request.GET.get("section")).first()
        if section is not None and school_class is not None and section.school_class_id != school_class.pk:
            section = None
        date = parse_date(self.request.GET.get("date"), timezone.localdate())
        return classes, sections, school_class, section, date

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        classes, sections, school_class, section, date = self.get_selection()
        context.update(
            {
                "classes": classes,
                "sections": sections,
                "selected_class": school_class,
                "selected_section": section,
                "selected_date": date,
                "statuses": AttendanceStatus.choices,
            }
        )

        if school_class is not None:
            students = students_in_class(
                self.request.user, school_class, section, self.active_branch
            )
            existing = {
                record.student_id: record
                for record in StudentAttendance.objects.for_user(
                    self.request.user, self.active_branch
                ).filter(date=date, student__in=students)
            }
            context["rows"] = [
                {"student": student, "record": existing.get(student.pk)}
                for student in students
            ]
        return context

    def post(self, request, *args, **kwargs):
        classes, _sections, school_class, section, date = self.get_selection()
        if school_class is None:
            messages.error(request, _("Select a class first."))
            return redirect(request.get_full_path())

        academic_year = (
            AcademicYear.objects.for_user(request.user, self.active_branch)
            .filter(is_current=True)
            .first()
        )
        if academic_year is None:
            messages.error(request, _("Set a current academic year first."))
            return redirect(request.get_full_path())

        students = {
            str(s.pk): s
            for s in students_in_class(
                request.user, school_class, section, self.active_branch
            )
        }
        entries = {}
        for key, value in request.POST.items():
            if not key.startswith("status-"):
                continue
            student = students.get(key.removeprefix("status-"))
            if student is None:
                # An id that is not on this register is ignored outright.
                continue
            entries[student] = {
                "status": value,
                "remarks": request.POST.get(f"remarks-{student.pk}", "")[:255],
            }

        if not entries:
            messages.error(request, _("No students to mark."))
            return redirect(request.get_full_path())

        _session, saved = mark_student_attendance(
            branch=self.active_branch,
            academic_year=academic_year,
            school_class=school_class,
            section=section,
            date=date,
            entries=entries,
            actor=request.user,
            request=request,
        )
        messages.success(
            request, _("Attendance saved for %(count)s students.") % {"count": saved}
        )
        return redirect(request.get_full_path())


class StudentAttendanceListView(TenantListView):
    model = StudentAttendance
    required_permission = ATTENDANCE
    page_title = _("Student Attendance")
    select_related = ("student", "session__school_class")
    ordering = ["-date"]
    filter_spec = FilterSpec(
        search_fields=("student__full_name", "student__admission_no"),
        choices={"status": "status"},
        date_field="date",
        selects={
            "status": {"label": _("Status"), "options": AttendanceStatus.choices}
        },
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Class"), "field": "session.school_class.name"},
        {"label": _("Status"), "field": "status", "type": "choice"},
        {"label": _("Remarks"), "field": "remarks"},
    )


class StaffAttendanceListView(TenantListView):
    model = StaffAttendance
    required_permission = ATTENDANCE
    template_name = "attendance/staff_list.html"
    page_title = _("Staff Attendance")
    select_related = ("staff",)
    ordering = ["-date"]
    filter_spec = FilterSpec(
        search_fields=("staff__full_name", "staff__employee_no"),
        choices={"status": "status"},
        date_field="date",
        selects={
            "status": {"label": _("Status"), "options": AttendanceStatus.choices}
        },
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Staff"), "field": "staff.full_name"},
        {"label": _("Status"), "field": "status", "type": "choice"},
        {"label": _("In"), "field": "check_in", "type": "time"},
        {"label": _("Out"), "field": "check_out", "type": "time"},
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        date = parse_date(self.request.GET.get("date"), timezone.localdate())
        context["mark_date"] = date
        context["statuses"] = AttendanceStatus.choices
        staff = Staff.objects.for_user(self.request.user, self.active_branch).filter(
            status=Staff.Status.ACTIVE
        )
        existing = {
            record.staff_id: record
            for record in StaffAttendance.objects.for_user(
                self.request.user, self.active_branch
            ).filter(date=date)
        }
        context["mark_rows"] = [
            {"staff": member, "record": existing.get(member.pk)} for member in staff
        ]
        return context

    def post(self, request, *args, **kwargs):
        from apps.core.permissions import require_permission

        require_permission(
            request.user, "attendance.add_staffattendance", self.active_branch
        )
        date = parse_date(request.POST.get("date"), timezone.localdate())
        staff = {
            str(s.pk): s
            for s in Staff.objects.for_user(request.user, self.active_branch)
        }
        entries = {}
        for key, value in request.POST.items():
            if not key.startswith("status-"):
                continue
            member = staff.get(key.removeprefix("status-"))
            if member is None:
                continue
            entries[member] = {"status": value}

        if entries:
            saved = mark_staff_attendance(
                branch=self.active_branch,
                date=date,
                entries=entries,
                actor=request.user,
                request=request,
            )
            messages.success(
                request, _("Attendance saved for %(count)s staff.") % {"count": saved}
            )
        return redirect(f"{reverse_lazy('attendance:staff_list')}?date={date}")
