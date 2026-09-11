"""Attendance service layer."""

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity
from apps.core.constants import AttendanceStatus
from apps.notifications.services import notify_absence

from .models import AttendanceSession, StaffAttendance, StudentAttendance


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
):
    """Record a whole register in one transaction.

    ``entries`` maps a ``Student`` to ``{"status": ..., "remarks": ...}``.
    Re-submitting the same register updates it rather than creating duplicates;
    the unique constraint on (session, student) backs that up at the database.
    """
    session, created = AttendanceSession.objects.get_or_create(
        branch=branch,
        school_class=school_class,
        section=section,
        date=date,
        period=period,
        defaults={
            "organization": branch.organization,
            "academic_year": academic_year,
            "session_type": session_type,
            "taken_by": actor,
        },
    )

    if session.is_locked:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(_("This attendance session is locked."))

    saved = 0
    newly_absent = []
    for student, values in entries.items():
        status = values.get("status") or AttendanceStatus.PRESENT
        record, created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "branch": branch,
                "organization": branch.organization,
                "date": date,
                "status": status,
                "minutes_late": values.get("minutes_late") or 0,
                "remarks": values.get("remarks", ""),
                "marked_by": actor,
            },
        )
        saved += 1
        if created and status == AttendanceStatus.ABSENT:
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
        new_values={"records": saved, "date": str(date)},
        metadata={"event": "attendance_marked"},
    )
    return session, saved


@transaction.atomic
def mark_staff_attendance(*, branch, date, entries, actor=None, request=None):
    """``entries`` maps a ``Staff`` to its attendance values."""
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
                "remarks": values.get("remarks", ""),
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


def attendance_summary(user, branch=None, *, date_from=None, date_to=None, student=None):
    """Counts per status, used by dashboards, report cards and reports."""
    from django.db.models import Count, Q

    queryset = StudentAttendance.objects.for_user(user, branch)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    if student is not None:
        queryset = queryset.filter(student=student)

    return queryset.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
        absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        late=Count("id", filter=Q(status=AttendanceStatus.LATE)),
        leave=Count("id", filter=Q(status=AttendanceStatus.LEAVE)),
        excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
    )
