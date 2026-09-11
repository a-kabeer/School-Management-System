"""Attendance for students and staff."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.core.constants import AttendanceStatus
from apps.core.models import BranchOwnedModel
from apps.staff.models import Staff
from apps.students.models import Student


class AttendanceSession(BranchOwnedModel):
    """One marking event: a class/section on a date, optionally per period.

    Grouping attendance into sessions is what makes "who marked this, and
    when?" answerable, and it gives the uniqueness rule somewhere to live.
    """

    class SessionType(models.TextChoices):
        DAILY = "daily", _("Daily")
        PERIOD = "period", _("Period")
        EXAM = "exam", _("Exam")
        EVENT = "event", _("Event")

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="attendance_sessions",
        verbose_name=_("academic year"),
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name="attendance_sessions",
        verbose_name=_("class"),
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_sessions",
        verbose_name=_("section"),
    )
    date = models.DateField(_("date"), db_index=True)
    session_type = models.CharField(
        _("session type"),
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.DAILY,
    )
    period = models.PositiveSmallIntegerField(_("period"), default=0)
    taken_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_sessions",
        verbose_name=_("taken by"),
    )
    is_locked = models.BooleanField(_("locked"), default=False)
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("attendance session")
        verbose_name_plural = _("attendance sessions")
        ordering = ["-date", "school_class__level"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "school_class", "section", "date", "period"],
                name="uq_attendance_session",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["branch", "academic_year", "date"]),
            models.Index(fields=["school_class", "date"]),
        ]

    def __str__(self):
        label = self.section or self.school_class
        return f"{label} — {self.date}"

    @property
    def is_editable(self):
        return not self.is_locked


class StudentAttendance(BranchOwnedModel):
    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name=_("session"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        verbose_name=_("student"),
    )
    date = models.DateField(_("date"), db_index=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    minutes_late = models.PositiveSmallIntegerField(_("minutes late"), default=0)
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)
    marked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendance",
        verbose_name=_("marked by"),
    )

    class Meta:
        verbose_name = _("student attendance")
        verbose_name_plural = _("student attendance")
        ordering = ["-date", "student__full_name"]
        constraints = [
            # One record per student per session - the database refuses a
            # duplicate even if two devices submit the same register.
            models.UniqueConstraint(
                fields=["session", "student"], name="uq_attendance_session_student"
            ),
        ]
        indexes = [
            models.Index(fields=["student", "date"]),
            models.Index(fields=["branch", "date", "status"]),
            models.Index(fields=["branch", "status"]),
        ]

    def __str__(self):
        return f"{self.student} — {self.date} — {self.get_status_display()}"


class StaffAttendance(BranchOwnedModel):
    staff = models.ForeignKey(
        Staff,
        on_delete=models.PROTECT,
        related_name="attendance_records",
        verbose_name=_("staff"),
    )
    date = models.DateField(_("date"), db_index=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    check_in = models.TimeField(_("check in"), null=True, blank=True)
    check_out = models.TimeField(_("check out"), null=True, blank=True)
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)
    marked_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_staff_attendance",
        verbose_name=_("marked by"),
    )

    class Meta:
        verbose_name = _("staff attendance")
        verbose_name_plural = _("staff attendance")
        ordering = ["-date", "staff__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "date"], name="uq_staff_daily_attendance"
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "date", "status"]),
            models.Index(fields=["staff", "date"]),
        ]

    def __str__(self):
        return f"{self.staff} — {self.date}"
