"""Attendance marking, duplicate prevention and the absence alert."""

import datetime as dt

from django.db.utils import IntegrityError
from django.test import TestCase

from apps.attendance.models import AttendanceSession, StudentAttendance
from apps.attendance.services import attendance_summary, mark_student_attendance
from apps.core.constants import AttendanceStatus
from apps.core.tests.factories import (
    build_branch,
    build_guardian_with_portal,
    build_student,
    build_user,
    two_branches,
)

DATE = dt.date(2026, 6, 1)


class AttendanceMarkingTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.teacher = build_user(self.fixture.branch, username="teacher")
        self.student = build_student(self.fixture, "Register Student", "R-001")

    def _mark(self, status):
        return mark_student_attendance(
            branch=self.fixture.branch,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            section=self.fixture.section,
            date=DATE,
            entries={self.student: {"status": status}},
            actor=self.teacher,
        )

    def test_marking_creates_a_session_and_a_record(self):
        session, saved = self._mark(AttendanceStatus.PRESENT)
        self.assertEqual(saved, 1)
        self.assertEqual(session.records.count(), 1)
        self.assertEqual(
            session.records.first().status, AttendanceStatus.PRESENT
        )

    def test_re_marking_updates_rather_than_duplicating(self):
        self._mark(AttendanceStatus.PRESENT)
        self._mark(AttendanceStatus.ABSENT)

        self.assertEqual(AttendanceSession.objects.count(), 1)
        self.assertEqual(StudentAttendance.objects.count(), 1)
        self.assertEqual(
            StudentAttendance.objects.first().status, AttendanceStatus.ABSENT
        )

    def test_the_database_refuses_a_duplicate_record(self):
        session, _saved = self._mark(AttendanceStatus.PRESENT)
        with self.assertRaises(IntegrityError):
            StudentAttendance.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                session=session,
                student=self.student,
                date=DATE,
                status=AttendanceStatus.PRESENT,
            )

    def test_a_locked_session_refuses_changes(self):
        from django.core.exceptions import PermissionDenied

        session, _saved = self._mark(AttendanceStatus.PRESENT)
        session.is_locked = True
        session.save(update_fields=["is_locked"])
        with self.assertRaises(PermissionDenied):
            self._mark(AttendanceStatus.ABSENT)

    def test_the_summary_counts_each_status(self):
        self._mark(AttendanceStatus.LATE)
        summary = attendance_summary(self.teacher, self.fixture.branch)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["late"], 1)
        self.assertEqual(summary["present"], 0)

    def test_a_new_absence_notifies_the_guardian(self):
        from apps.notifications.models import Notification

        build_guardian_with_portal(self.fixture, self.student, username="absent_parent")
        self._mark(AttendanceStatus.ABSENT)

        self.assertTrue(
            Notification.objects.filter(event="attendance.absent").exists()
        )

    def test_re_saving_an_absence_does_not_notify_twice(self):
        from apps.notifications.models import Notification

        build_guardian_with_portal(self.fixture, self.student, username="absent_parent")
        self._mark(AttendanceStatus.ABSENT)
        self._mark(AttendanceStatus.ABSENT)

        self.assertEqual(
            Notification.objects.filter(event="attendance.absent").count(), 1
        )


class AttendanceIsolationTests(TestCase):
    def test_a_register_is_scoped_to_its_branch(self):
        branch_a, branch_b = two_branches()
        student_b = build_student(branch_b, "Branch B Student", "B-900")
        mark_student_attendance(
            branch=branch_b.branch,
            academic_year=branch_b.academic_year,
            school_class=branch_b.school_class,
            section=branch_b.section,
            date=DATE,
            entries={student_b: {"status": AttendanceStatus.PRESENT}},
        )
        user_a = build_user(branch_a.branch, username="teacher_a")
        self.assertEqual(
            StudentAttendance.objects.for_user(user_a, branch_a.branch).count(), 0
        )
