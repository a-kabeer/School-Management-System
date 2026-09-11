"""Staff check-in/out, working hours, corrections and the monthly report.

The staff register is deliberately a separate mechanism from the student one:
staff clock themselves against a clock, students are marked in bulk against a
class. These tests hold that separation in place.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.attendance.models import StaffAttendance
from apps.attendance.services import (
    correct_staff_attendance,
    staff_check_in,
    staff_check_out,
    staff_month_summary,
)
from apps.core.constants import AttendanceStatus
from apps.core.tests.factories import build_branch, build_staff, build_user


class StaffClockTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.staff = build_staff(self.fixture, "Clock Tester", "EMP-CLK")
        self.user = build_user(self.fixture.branch, username="clocker")

    def test_checking_in_records_the_time_and_marks_present(self):
        record = staff_check_in(
            staff=self.staff, at=dt.time(7, 55), actor=self.user
        )
        self.assertEqual(record.check_in, dt.time(7, 55))
        self.assertEqual(record.status, AttendanceStatus.PRESENT)
        self.assertTrue(record.is_open)

    def test_arriving_after_the_cut_off_is_late(self):
        # The default cut-off is 08:15; arriving past it is late, not absent.
        record = staff_check_in(staff=self.staff, at=dt.time(9, 30))
        self.assertEqual(record.status, AttendanceStatus.LATE)

    def test_checking_in_twice_is_refused(self):
        staff_check_in(staff=self.staff, at=dt.time(8, 0))
        with self.assertRaises(ValidationError):
            staff_check_in(staff=self.staff, at=dt.time(8, 30))
        self.assertEqual(StaffAttendance.objects.count(), 1)

    def test_checking_out_computes_the_hours_worked(self):
        staff_check_in(staff=self.staff, at=dt.time(8, 0))
        record = staff_check_out(staff=self.staff, at=dt.time(14, 30))

        self.assertEqual(record.worked_minutes, 390)
        self.assertEqual(record.worked_hours_display, "6h 30m")
        self.assertFalse(record.is_open)

    def test_checking_out_without_checking_in_is_refused(self):
        with self.assertRaises(ValidationError):
            staff_check_out(staff=self.staff, at=dt.time(14, 0))

    def test_checking_out_twice_is_refused(self):
        staff_check_in(staff=self.staff, at=dt.time(8, 0))
        staff_check_out(staff=self.staff, at=dt.time(14, 0))
        with self.assertRaises(ValidationError):
            staff_check_out(staff=self.staff, at=dt.time(15, 0))

    def test_checking_out_before_checking_in_is_refused(self):
        staff_check_in(staff=self.staff, at=dt.time(9, 0))
        with self.assertRaises(ValidationError):
            staff_check_out(staff=self.staff, at=dt.time(8, 0))

    def test_an_open_record_reports_no_hours(self):
        record = staff_check_in(staff=self.staff, at=dt.time(8, 0))
        self.assertIsNone(record.worked_minutes)
        self.assertEqual(record.worked_hours_display, "—")

    def test_one_row_per_person_per_day(self):
        from django.db.utils import IntegrityError

        staff_check_in(staff=self.staff, at=dt.time(8, 0))
        with self.assertRaises(IntegrityError):
            StaffAttendance.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                staff=self.staff,
                date=timezone.localdate(),
                status=AttendanceStatus.PRESENT,
            )


class StaffCorrectionTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.staff = build_staff(self.fixture, "Correction Tester", "EMP-COR")
        self.officer = build_user(self.fixture.branch, username="officer")

    def test_a_correction_rewrites_the_times_and_is_audited(self):
        from apps.audit.models import ActivityLog

        record = staff_check_in(staff=self.staff, at=dt.time(9, 45))
        self.assertEqual(record.status, AttendanceStatus.LATE)

        corrected = correct_staff_attendance(
            record=record,
            status=AttendanceStatus.PRESENT,
            check_in=dt.time(8, 0),
            check_out=dt.time(16, 0),
            remarks="Gate register confirms 08:00",
            actor=self.officer,
        )

        self.assertEqual(corrected.status, AttendanceStatus.PRESENT)
        self.assertEqual(corrected.worked_hours_display, "8h 00m")
        self.assertTrue(
            ActivityLog.objects.filter(
                metadata__event="staff_attendance_correction"
            ).exists()
        )

    def test_a_correction_cannot_invert_the_day(self):
        record = staff_check_in(staff=self.staff, at=dt.time(8, 0))
        with self.assertRaises(ValidationError):
            correct_staff_attendance(
                record=record, check_out=dt.time(7, 0), actor=self.officer
            )


class StaffMonthlyReportTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.staff = build_staff(self.fixture, "Monthly Tester", "EMP-MON")
        self.user = build_user(self.fixture.branch, username="reader")
        self.month = dt.date(2026, 6, 1)

    def _day(self, day, status, check_in=None, check_out=None):
        return StaffAttendance.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            staff=self.staff,
            date=self.month.replace(day=day),
            status=status,
            check_in=check_in,
            check_out=check_out,
        )

    def test_the_month_totals_days_hours_and_a_percentage(self):
        self._day(1, AttendanceStatus.PRESENT, dt.time(8, 0), dt.time(14, 0))
        self._day(2, AttendanceStatus.LATE, dt.time(9, 0), dt.time(14, 0))
        self._day(3, AttendanceStatus.ABSENT)
        self._day(4, AttendanceStatus.PRESENT, dt.time(8, 0), dt.time(12, 30))

        report = staff_month_summary(self.user, self.fixture.branch, month=self.month)
        row = report["rows"][0]

        self.assertEqual(row["days"], 4)
        self.assertEqual(row["present"], 2)
        self.assertEqual(row["late"], 1)
        self.assertEqual(row["absent"], 1)
        # 6h + 5h + 4h30 = 15h30, and late still counts as attending.
        self.assertEqual(row["worked_display"], "15h 30m")
        self.assertEqual(row["percentage"], 75.0)

    def test_another_month_is_not_counted(self):
        self._day(1, AttendanceStatus.PRESENT, dt.time(8, 0), dt.time(14, 0))
        report = staff_month_summary(
            self.user, self.fixture.branch, month=dt.date(2026, 7, 1)
        )
        self.assertEqual(report["rows"], [])
