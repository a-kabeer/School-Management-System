"""Attendance service layer.

Two registers live here and stay separate: students are marked in bulk against
a class (optionally a subject and period), staff clock themselves in and out.
Both write through the same audit trail.
"""

import datetime as dt

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity
from apps.core.constants import AttendanceStatus
from apps.core.services import get_setting
from apps.notifications.services import notify_absence

from .models import AttendanceSession, StaffAttendance, StudentAttendance


# --------------------------------------------------------------------------
# Students
# --------------------------------------------------------------------------
@transaction.atomic
def mark_student_attendance(
    *,
    branch,
    academic_year,
    school_class,
    section,
    date,
    entries,
    actor=None,
    request=None,
    session_type=AttendanceSession.SessionType.DAILY,
    period=0,
    class_subject=None,
):
    """Record a whole register in one transaction.

    ``entries`` maps a ``Student`` to ``{"status": ..., "remarks": ...}``.
    Re-submitting the same register updates it rather than creating duplicates;
    the unique constraints on the session and on (session, student) back that
    up at the database.

    Passing ``class_subject`` makes this a subject register for that period,
    kept separate from the day's general register for the same class.
    """
    if class_subject is not None and class_subject.school_class_id != school_class.pk:
        raise ValidationError(
            {"class_subject": _("That subject is not taught to this class.")}
        )

    session, created = AttendanceSession.objects.get_or_create(
        branch=branch,
        school_class=school_class,
        section=section,
        date=date,
        period=period,
        class_subject=class_subject,
        defaults={
            "organization": branch.organization,
            "academic_year": academic_year,
            "session_type": session_type,
            "taken_by": actor,
        },
    )

    if session.is_locked:
        raise PermissionDenied(_("This attendance session is locked."))

    saved = 0
    newly_absent = []
    for student, values in entries.items():
        status = values.get("status") or AttendanceStatus.PRESENT
        record, record_created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "branch": branch,
                "organization": branch.organization,
                "date": date,
                "status": status,
                "minutes_late": values.get("minutes_late") or 0,
                "remarks": (values.get("remarks") or "")[:255],
                "marked_by": actor,
            },
        )
        saved += 1
        if record_created and status == AttendanceStatus.ABSENT:
            # Only a newly recorded absence alerts the family; re-saving the
            # register must not send the same message twice.
            newly_absent.append(record)

    for record in newly_absent:
        notify_absence(attendance=record, actor=actor)

    log_activity(
        action="create" if created else "update",
        request=request,
        user=actor,
        instance=session,
        new_values={
            "records": saved,
            "date": str(date),
            "subject": str(class_subject) if class_subject else None,
            "period": period,
        },
        metadata={"event": "attendance_marked"},
    )
    return session, saved


def students_for_register(user, school_class, section=None, branch=None):
    """The students a register should list, in roll-number order."""
    from apps.students.selectors import students_in_class

    return students_in_class(user, school_class, section, branch)


def existing_marks(user, session=None, branch=None, date=None, students=None):
    """Existing marks keyed by student id, for pre-filling a register."""
    if session is not None:
        queryset = StudentAttendance.objects.filter(session=session)
    else:
        queryset = StudentAttendance.objects.for_user(user, branch).filter(date=date)
        if students is not None:
            queryset = queryset.filter(student__in=students)
    return {record.student_id: record for record in queryset}


def attendance_summary(user, branch=None, *, date_from=None, date_to=None, student=None,
                       class_subject=None, school_class=None):
    """Counts per status, used by dashboards, report cards and reports."""
    queryset = StudentAttendance.objects.for_user(user, branch)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    if student is not None:
        queryset = queryset.filter(student=student)
    if class_subject is not None:
        queryset = queryset.filter(session__class_subject=class_subject)
    if school_class is not None:
        queryset = queryset.filter(session__school_class=school_class)

    totals = queryset.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        late=Count("id", filter=Q(status=AttendanceStatus.LATE)),
        leave=Count("id", filter=Q(status=AttendanceStatus.LEAVE)),
        excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
    )
    marked = totals["total"] or 0
    # Late still counts as attending; only absence costs a student their rate.
    attended = (totals["present"] or 0) + (totals["late"] or 0)
    totals["percentage"] = round(attended / marked * 100, 1) if marked else None
    return totals


def todays_periods(user, branch, staff=None, date=None):
    """Timetable slots for today, so a teacher can open one and mark it.

    Each slot carries whether its register has already been taken, which is
    what turns the list into a to-do rather than a schedule.
    """
    from apps.academics.models import Timetable

    date = date or timezone.localdate()
    slots = (
        Timetable.objects.for_user(user, branch)
        .filter(weekday=date.weekday())
        .select_related(
            "section__school_class", "class_subject__subject", "teacher", "academic_year"
        )
        .order_by("period", "section__school_class__name", "section__name")
    )
    if staff is not None:
        slots = slots.filter(teacher=staff)

    slots = list(slots)
    taken = set(
        AttendanceSession.objects.for_user(user, branch)
        .filter(date=date, class_subject__isnull=False)
        .values_list("section_id", "class_subject_id", "period")
    )
    for slot in slots:
        slot.register_taken = (
            slot.section_id, slot.class_subject_id, slot.period
        ) in taken
    return slots


# --------------------------------------------------------------------------
# Staff
# --------------------------------------------------------------------------
def _late_after(organization):
    """Clock-in time after which arrival counts as late (HH:MM setting)."""
    raw = get_setting("staff_late_after", {"value": "08:15"}, organization)
    value = raw.get("value") if isinstance(raw, dict) else raw
    try:
        hour, minute = str(value).split(":")
        return dt.time(int(hour), int(minute))
    except (ValueError, TypeError):
        return dt.time(8, 15)


@transaction.atomic
def staff_check_in(*, staff, at=None, actor=None, request=None, remarks=""):
    """Record an arrival. Checking in twice on one day is refused."""
    now = timezone.localtime()
    date = now.date()
    at = at or now.time().replace(microsecond=0)

    record = StaffAttendance.objects.filter(staff=staff, date=date).first()
    if record is not None and record.check_in:
        raise ValidationError(
            _("%(staff)s already checked in at %(time)s.")
            % {"staff": staff.full_name, "time": record.check_in.strftime("%H:%M")}
        )

    status = (
        AttendanceStatus.LATE
        if at > _late_after(staff.organization)
        else AttendanceStatus.PRESENT
    )

    if record is None:
        record = StaffAttendance(
            branch=staff.branch, organization=staff.organization, staff=staff, date=date
        )
    record.check_in = at
    record.status = status
    record.remarks = remarks[:255] or record.remarks
    record.marked_by = actor
    record.save()

    log_activity(
        action="create",
        request=request,
        user=actor,
        instance=record,
        new_values={"check_in": str(at), "status": status},
        metadata={"event": "staff_check_in"},
    )
    return record


@transaction.atomic
def staff_check_out(*, staff, at=None, actor=None, request=None):
    """Record a departure against today's arrival."""
    now = timezone.localtime()
    date = now.date()
    at = at or now.time().replace(microsecond=0)

    record = StaffAttendance.objects.filter(staff=staff, date=date).first()
    if record is None or not record.check_in:
        raise ValidationError(_("There is no check-in recorded for today."))
    if record.check_out:
        raise ValidationError(
            _("%(staff)s already checked out at %(time)s.")
            % {"staff": staff.full_name, "time": record.check_out.strftime("%H:%M")}
        )
    if at < record.check_in:
        raise ValidationError(_("Check-out cannot be earlier than check-in."))

    record.check_out = at
    record.save(update_fields=["check_out", "updated_at"])

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=record,
        new_values={"check_out": str(at), "worked_minutes": record.worked_minutes},
        metadata={"event": "staff_check_out"},
    )
    return record


@transaction.atomic
def correct_staff_attendance(
    *, record, status=None, check_in=None, check_out=None, remarks="", actor=None, request=None
):
    """An authorised correction to a staff attendance row.

    Corrections are a separate entry point from check-in/out so they can carry
    their own permission and leave a distinct audit record.
    """
    from apps.audit.services import snapshot

    previous = snapshot(record)

    if status is not None:
        record.status = status
    if check_in is not None:
        record.check_in = check_in
    if check_out is not None:
        record.check_out = check_out
    if remarks:
        record.remarks = remarks[:255]

    if record.check_in and record.check_out and record.check_out < record.check_in:
        raise ValidationError({"check_out": _("Check-out cannot be earlier than check-in.")})

    record.marked_by = actor
    record.save()

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=record,
        previous_values=previous,
        new_values=snapshot(record),
        metadata={"event": "staff_attendance_correction"},
    )
    return record


@transaction.atomic
def mark_staff_attendance(*, branch, date, entries, actor=None, request=None):
    """Mark a whole staff register at once, for an office that does it by hand.

    ``entries`` maps a ``Staff`` to its attendance values.
    """
    saved = 0
    for staff, values in entries.items():
        StaffAttendance.objects.update_or_create(
            staff=staff,
            date=date,
            defaults={
                "branch": branch,
                "organization": branch.organization,
                "status": values.get("status") or AttendanceStatus.PRESENT,
                "check_in": values.get("check_in"),
                "check_out": values.get("check_out"),
                "remarks": (values.get("remarks") or "")[:255],
                "marked_by": actor,
            },
        )
        saved += 1

    log_activity(
        action="update",
        request=request,
        user=actor,
        organization=branch.organization,
        branch=branch,
        new_values={"records": saved, "date": str(date)},
        metadata={"event": "staff_attendance_marked"},
    )
    return saved


def staff_month_summary(user, branch=None, *, month=None, staff=None):
    """Per-staff totals for a month, for the monthly attendance report."""
    month = month or timezone.localdate().replace(day=1)
    next_month = (month.replace(day=28) + dt.timedelta(days=4)).replace(day=1)

    queryset = StaffAttendance.objects.for_user(user, branch).filter(
        date__gte=month, date__lt=next_month
    )
    if staff is not None:
        queryset = queryset.filter(staff=staff)

    rows = (
        queryset.values("staff_id", "staff__full_name", "staff__employee_no")
        .annotate(
            days=Count("id"),
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            late=Count("id", filter=Q(status=AttendanceStatus.LATE)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
            leave=Count("id", filter=Q(status=AttendanceStatus.LEAVE)),
        )
        .order_by("staff__full_name")
    )

    # Worked minutes are a Python property, so total them from the rows we
    # already have rather than adding a second aggregate query per person.
    minutes = {}
    for record in queryset.only("staff_id", "check_in", "check_out"):
        worked = record.worked_minutes
        if worked:
            minutes[record.staff_id] = minutes.get(record.staff_id, 0) + worked

    prepared = []
    for row in rows:
        total = minutes.get(row["staff_id"], 0)
        attended = row["present"] + row["late"]
        prepared.append(
            {
                **row,
                "worked_minutes": total,
                "worked_display": f"{total // 60}h {total % 60:02d}m",
                "percentage": round(attended / row["days"] * 100, 1) if row["days"] else None,
            }
        )
    return {"month": month, "rows": prepared}
