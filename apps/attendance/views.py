import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View

from apps.academics.models import AcademicYear, ClassSubject, SchoolClass, Section, Timetable
from apps.core.constants import AttendanceStatus
from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantDetailView,
    TenantListView,
)
from apps.core.permissions import PermissionRequiredMixin, require_permission
from apps.core.utils import parse_date
from apps.staff.models import Staff

from .models import AttendanceSession, StaffAttendance, StudentAttendance
from .services import (
    attendance_summary,
    correct_staff_attendance,
    existing_marks,
    mark_staff_attendance,
    mark_student_attendance,
    staff_check_in,
    staff_check_out,
    staff_month_summary,
    students_for_register,
    todays_periods,
)

ATTENDANCE = "core.access_attendance"


# --------------------------------------------------------------------------
# Sessions and history
# --------------------------------------------------------------------------
class SessionListView(TenantListView):
    model = AttendanceSession
    required_permission = ATTENDANCE
    page_title = _("Attendance Sessions")
    page_subtitle = _("Every register taken, daily and subject-wise.")
    select_related = ("school_class", "section", "taken_by", "academic_year",
                      "class_subject__subject")
    ordering = ["-date", "-created_at"]
    detail_url_name = "attendance:session_detail"
    filter_spec = FilterSpec(
        search_fields=("school_class__name", "section__name",
                       "class_subject__subject__name"),
        choices={"school_class": "school_class_id", "session_type": "session_type"},
        date_field="date",
        selects={
            "session_type": {
                "label": _("Type"),
                "options": AttendanceSession.SessionType.choices,
            }
        },
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Subject"), "field": "class_subject.subject.name"},
        {"label": _("Period"), "field": "period"},
        {"label": _("Taken by"), "field": "taken_by.display_name"},
        {"label": _("Locked"), "field": "is_locked", "type": "bool"},
    )


class SessionDetailView(TenantDetailView):
    model = AttendanceSession
    required_permission = ATTENDANCE
    template_name = "attendance/session_detail.html"
    select_related = ("school_class", "section", "academic_year", "taken_by",
                      "class_subject__subject")
    page_title = _("Attendance Session")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = self.object.records.select_related("student").order_by(
            "student__full_name"
        )
        context["records"] = records
        # Counted in Python over rows already fetched for the table, rather
        # than a second aggregate query per status.
        context["counts"] = [
            {"label": label, "count": sum(1 for r in records if r.status == status)}
            for status, label in AttendanceStatus.choices
        ]
        return context


# --------------------------------------------------------------------------
# Student registers
# --------------------------------------------------------------------------
class MarkAttendanceView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Pick a class/section/date — and optionally a subject and period — then
    submit the whole register at once."""

    template_name = "attendance/mark.html"
    required_permission = "attendance.add_studentattendance"
    page_title = _("Mark Attendance")
    page_subtitle = _("Choose a class, then mark everyone at once.")

    def get_selection(self):
        branch = self.active_branch
        user = self.request.user

        classes = SchoolClass.objects.for_user(user, branch).filter(is_active=True)
        sections = (
            Section.objects.for_user(user, branch)
            .filter(is_active=True)
            .select_related("school_class")
        )
        subjects = (
            ClassSubject.objects.for_user(user, branch)
            .filter(is_active=True)
            .select_related("subject", "school_class")
        )

        school_class = classes.filter(pk=self.request.GET.get("school_class")).first()
        section = sections.filter(pk=self.request.GET.get("section")).first()
        if section and school_class and section.school_class_id != school_class.pk:
            section = None

        class_subject = subjects.filter(pk=self.request.GET.get("class_subject")).first()
        if class_subject and school_class and class_subject.school_class_id != school_class.pk:
            class_subject = None

        try:
            period = int(self.request.GET.get("period") or 0)
        except (TypeError, ValueError):
            period = 0

        date = parse_date(self.request.GET.get("date"), timezone.localdate())
        return {
            "classes": classes,
            "sections": sections,
            "subjects": subjects,
            "school_class": school_class,
            "section": section,
            "class_subject": class_subject,
            "period": max(period, 0),
            "date": date,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selection = self.get_selection()
        context.update(
            {
                "classes": selection["classes"],
                "sections": selection["sections"],
                "subjects": selection["subjects"],
                "selected_class": selection["school_class"],
                "selected_section": selection["section"],
                "selected_subject": selection["class_subject"],
                "selected_period": selection["period"],
                "selected_date": selection["date"],
                "statuses": AttendanceStatus.choices,
            }
        )

        school_class = selection["school_class"]
        if school_class is None:
            return context

        students = list(
            students_for_register(
                self.request.user, school_class, selection["section"], self.active_branch
            )
        )
        session = (
            AttendanceSession.objects.for_user(self.request.user, self.active_branch)
            .filter(
                school_class=school_class,
                section=selection["section"],
                date=selection["date"],
                period=selection["period"],
                class_subject=selection["class_subject"],
            )
            .first()
        )
        marks = existing_marks(
            self.request.user,
            session=session,
            branch=self.active_branch,
            date=selection["date"],
            students=students,
        ) if session else {}

        context["session"] = session
        context["rows"] = [
            {"student": student, "record": marks.get(student.pk)} for student in students
        ]
        return context

    def post(self, request, *args, **kwargs):
        selection = self.get_selection()
        school_class = selection["school_class"]
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
            for s in students_for_register(
                request.user, school_class, selection["section"], self.active_branch
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
                "remarks": request.POST.get(f"remarks-{student.pk}", ""),
            }

        if not entries:
            messages.error(request, _("No students to mark."))
            return redirect(request.get_full_path())

        try:
            _session, saved = mark_student_attendance(
                branch=self.active_branch,
                academic_year=academic_year,
                school_class=school_class,
                section=selection["section"],
                date=selection["date"],
                entries=entries,
                actor=request.user,
                request=request,
                class_subject=selection["class_subject"],
                period=selection["period"],
                session_type=(
                    AttendanceSession.SessionType.PERIOD
                    if selection["class_subject"]
                    else AttendanceSession.SessionType.DAILY
                ),
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, "; ".join(getattr(error, "messages", [str(error)])))
            return redirect(request.get_full_path())

        messages.success(
            request, _("Attendance saved for %(count)s students.") % {"count": saved}
        )
        return redirect(request.get_full_path())


class TodayPeriodsView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Today's timetable as a to-do list: open a period, mark it, move on.

    This is the route that spares a teacher from picking class, subject and
    period by hand for every register.
    """

    template_name = "attendance/today.html"
    required_permission = ATTENDANCE
    page_title = _("Today's Classes")
    page_subtitle = _("Open a period to take its register.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        date = parse_date(self.request.GET.get("date"), timezone.localdate())
        staff = getattr(self.request.user, "staff_profile", None)

        slots = todays_periods(
            self.request.user, self.active_branch, staff=staff, date=date
        )
        if staff is not None and not slots:
            # A teacher with nothing of their own still gets the branch's day
            # rather than an empty page.
            slots = todays_periods(self.request.user, self.active_branch, date=date)
            context["showing_all"] = True

        context["slots"] = slots
        context["selected_date"] = date
        context["is_teacher"] = staff is not None
        return context


class SubjectRegisterView(ActiveBranchMixin, View):
    """Jump from a timetable slot straight into its register."""

    def get(self, request, pk, *args, **kwargs):
        require_permission(request.user, ATTENDANCE, self.active_branch)
        slot = get_object_or_404(
            Timetable.objects.for_user(request.user, self.active_branch)
            .select_related("section", "class_subject"),
            pk=pk,
        )
        date = parse_date(request.GET.get("date"), timezone.localdate())
        query = (
            f"?school_class={slot.section.school_class_id}"
            f"&section={slot.section_id}"
            f"&class_subject={slot.class_subject_id}"
            f"&period={slot.period}"
            f"&date={date:%Y-%m-%d}"
        )
        return redirect(reverse("attendance:mark") + query)


class StudentAttendanceListView(TenantListView):
    model = StudentAttendance
    required_permission = ATTENDANCE
    template_name = "attendance/record_list.html"
    page_title = _("Student Attendance")
    page_subtitle = _("Every marked record, searchable by student.")
    select_related = ("student", "session__school_class", "session__class_subject__subject")
    ordering = ["-date", "student__full_name"]
    filter_spec = FilterSpec(
        search_fields=("student__full_name", "student__admission_no"),
        choices={"status": "status", "school_class": "session__school_class_id"},
        date_field="date",
        selects={"status": {"label": _("Status"), "options": AttendanceStatus.choices}},
    )
    table_columns = (
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Class"), "field": "session.school_class.name"},
        {"label": _("Subject"), "field": "session.class_subject.subject.name"},
        {"label": _("Status"), "field": "status", "type": "choice"},
        {"label": _("Remarks"), "field": "remarks"},
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = attendance_summary(
            self.request.user,
            self.active_branch,
            date_from=parse_date(self.request.GET.get("date_from")),
            date_to=parse_date(self.request.GET.get("date_to")),
        )
        return context


# --------------------------------------------------------------------------
# Staff register
# --------------------------------------------------------------------------
class StaffAttendanceListView(TenantListView):
    model = StaffAttendance
    required_permission = ATTENDANCE
    template_name = "attendance/staff_list.html"
    page_title = _("Staff Attendance")
    page_subtitle = _("Check-in and check-out times, with hours worked.")
    select_related = ("staff",)
    ordering = ["-date", "staff__full_name"]
    filter_spec = FilterSpec(
        search_fields=("staff__full_name", "staff__employee_no"),
        choices={"status": "status"},
        date_field="date",
        selects={"status": {"label": _("Status"), "options": AttendanceStatus.choices}},
    )
    table_columns = (
        {"label": _("Staff"), "field": "staff.full_name"},
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Status"), "field": "status", "type": "choice"},
        {"label": _("In"), "field": "check_in", "type": "time"},
        {"label": _("Out"), "field": "check_out", "type": "time"},
        {"label": _("Hours"), "field": "worked_hours_display"},
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
        return redirect(f"{reverse('attendance:staff_list')}?date={date:%Y-%m-%d}")


class StaffClockView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Check in and out. A staff member clocks themselves; an office with the
    staff-attendance permission can clock anyone in their branch."""

    template_name = "attendance/clock.html"
    required_permission = ATTENDANCE
    page_title = _("Check In / Check Out")
    page_subtitle = _("Today's arrival and departure times.")

    def get_staff_queryset(self):
        return Staff.objects.for_user(self.request.user, self.active_branch).filter(
            status=Staff.Status.ACTIVE
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        me = getattr(self.request.user, "staff_profile", None)

        context["me"] = me
        context["today"] = today
        context["now"] = timezone.localtime().time()
        context["my_record"] = (
            StaffAttendance.objects.filter(staff=me, date=today).first() if me else None
        )
        context["can_clock_others"] = self.request.user.has_perm(
            "attendance.add_staffattendance"
        )
        if context["can_clock_others"]:
            records = {
                r.staff_id: r
                for r in StaffAttendance.objects.for_user(
                    self.request.user, self.active_branch
                ).filter(date=today)
            }
            context["rows"] = [
                {"staff": member, "record": records.get(member.pk)}
                for member in self.get_staff_queryset()
            ]
        context["history"] = (
            StaffAttendance.objects.filter(staff=me).order_by("-date")[:14] if me else []
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        staff_id = request.POST.get("staff")
        me = getattr(request.user, "staff_profile", None)

        if staff_id:
            # Clocking somebody else is a supervisory action and needs the
            # staff-attendance permission, whoever the target is.
            require_permission(
                request.user, "attendance.add_staffattendance", self.active_branch
            )
            staff = get_object_or_404(self.get_staff_queryset(), pk=staff_id)
        elif me is not None:
            staff = me
        else:
            messages.error(request, _("Your account is not linked to a staff record."))
            return redirect("attendance:clock")

        try:
            if action == "check_out":
                record = staff_check_out(staff=staff, actor=request.user, request=request)
                messages.success(
                    request,
                    _("Checked out at %(time)s — %(hours)s worked.")
                    % {
                        "time": record.check_out.strftime("%H:%M"),
                        "hours": record.worked_hours_display,
                    },
                )
            else:
                record = staff_check_in(staff=staff, actor=request.user, request=request)
                messages.success(
                    request,
                    _("Checked in at %(time)s (%(status)s).")
                    % {
                        "time": record.check_in.strftime("%H:%M"),
                        "status": record.get_status_display(),
                    },
                )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))

        return redirect("attendance:clock")


class StaffCorrectionView(ActiveBranchMixin, View):
    """Authorised correction of a staff attendance row."""

    def post(self, request, pk, *args, **kwargs):
        require_permission(
            request.user, "attendance.change_staffattendance", self.active_branch
        )
        record = get_object_or_404(
            StaffAttendance.objects.for_user(request.user, self.active_branch), pk=pk
        )

        def _time(name):
            raw = request.POST.get(name)
            if not raw:
                return None
            try:
                return dt.datetime.strptime(raw, "%H:%M").time()
            except ValueError:
                return None

        try:
            correct_staff_attendance(
                record=record,
                status=request.POST.get("status") or None,
                check_in=_time("check_in"),
                check_out=_time("check_out"),
                remarks=request.POST.get("remarks", ""),
                actor=request.user,
                request=request,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(getattr(error, "messages", [str(error)])))
        else:
            messages.success(request, _("Attendance corrected."))
        return redirect(f"{reverse('attendance:staff_list')}?date={record.date:%Y-%m-%d}")


class StaffMonthlyReportView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "attendance/staff_month.html"
    required_permission = ATTENDANCE
    page_title = _("Staff Monthly Attendance")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month = parse_date(
            self.request.GET.get("month"), timezone.localdate()
        ).replace(day=1)
        context["report"] = staff_month_summary(
            self.request.user, self.active_branch, month=month
        )
        context["month"] = month
        context["page_subtitle"] = month.strftime("%B %Y")
        return context
