"""Subject and period registers, and the timetable route into them.

A subject register is a different record from the day's general register for
the same class, and neither may be taken twice. Both rules are enforced at the
database, so these tests reach past the service layer to check them.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import Timetable
from apps.attendance.models import AttendanceSession
from apps.attendance.services import mark_student_attendance, todays_periods
from apps.core.constants import AttendanceStatus
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_staff,
    build_student,
    build_subject,
    build_user,
)

PASSWORD = "Str0ngPassphrase!42"
#: A Monday, so the weekday of the timetable slot is predictable.
DATE = dt.date(2026, 6, 1)


class SubjectRegisterTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.teacher = build_user(self.fixture.branch, username="subject_teacher")
        self.student = build_student(self.fixture, "Subject Student", "S-001")
        self.maths = build_subject(self.fixture, "Mathematics")
        self.science = build_subject(self.fixture, "Science")

    def _mark(self, class_subject=None, period=0, status=AttendanceStatus.PRESENT):
        return mark_student_attendance(
            branch=self.fixture.branch,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            section=self.fixture.section,
            date=DATE,
            entries={self.student: {"status": status}},
            actor=self.teacher,
            class_subject=class_subject,
            period=period,
            session_type=(
                AttendanceSession.SessionType.PERIOD
                if class_subject
                else AttendanceSession.SessionType.DAILY
            ),
        )

    def test_a_subject_register_is_separate_from_the_daily_one(self):
        self._mark()
        self._mark(class_subject=self.maths, period=1)

        self.assertEqual(AttendanceSession.objects.count(), 2)
        self.assertEqual(
            AttendanceSession.objects.filter(class_subject__isnull=True).count(), 1
        )

    def test_two_subjects_in_the_same_period_are_separate_registers(self):
        self._mark(class_subject=self.maths, period=1)
        self._mark(class_subject=self.science, period=2)
        self.assertEqual(AttendanceSession.objects.count(), 2)

    def test_re_taking_a_subject_register_updates_it(self):
        self._mark(class_subject=self.maths, period=1, status=AttendanceStatus.PRESENT)
        self._mark(class_subject=self.maths, period=1, status=AttendanceStatus.ABSENT)

        self.assertEqual(AttendanceSession.objects.count(), 1)
        session = AttendanceSession.objects.get()
        self.assertEqual(session.records.count(), 1)
        self.assertEqual(session.records.get().status, AttendanceStatus.ABSENT)

    def test_the_database_refuses_a_second_subject_session(self):
        self._mark(class_subject=self.maths, period=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceSession.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                academic_year=self.fixture.academic_year,
                school_class=self.fixture.school_class,
                section=self.fixture.section,
                class_subject=self.maths,
                period=1,
                date=DATE,
            )

    def test_the_database_refuses_a_second_daily_session(self):
        # PostgreSQL treats every NULL as distinct, so the daily register
        # needs its own constraint rather than relying on the subject one.
        self._mark()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceSession.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                academic_year=self.fixture.academic_year,
                school_class=self.fixture.school_class,
                section=self.fixture.section,
                class_subject=None,
                period=0,
                date=DATE,
            )

    def test_a_subject_from_another_class_is_refused(self):
        other = build_branch(self.fixture.organization, name="Other", code="OTH")
        foreign_subject = build_subject(other, "Foreign Subject")
        with self.assertRaises(ValidationError):
            self._mark(class_subject=foreign_subject, period=1)


class TimetableRouteTests(TestCase):
    """Opening today's period must not make a teacher re-pick anything."""

    def setUp(self):
        self.fixture = build_branch()
        self.admin = build_admin(self.fixture.branch, username="timetable_admin")
        self.staff = build_staff(self.fixture, "Timetable Teacher", "EMP-TT")
        self.maths = build_subject(self.fixture, "Mathematics")
        self.slot = Timetable.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.fixture.academic_year,
            section=self.fixture.section,
            class_subject=self.maths,
            teacher=self.staff,
            weekday=DATE.weekday(),
            period=3,
            start_time=dt.time(10, 0),
            end_time=dt.time(10, 45),
        )
        self.client.login(username="timetable_admin", password=PASSWORD)

    def test_todays_periods_flags_a_register_that_is_already_taken(self):
        slots = todays_periods(self.admin, self.fixture.branch, date=DATE)
        self.assertEqual(len(slots), 1)
        self.assertFalse(slots[0].register_taken)

        student = build_student(self.fixture, "Flagged Student", "F-001")
        mark_student_attendance(
            branch=self.fixture.branch,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            section=self.fixture.section,
            date=DATE,
            entries={student: {"status": AttendanceStatus.PRESENT}},
            class_subject=self.maths,
            period=3,
        )

        slots = todays_periods(self.admin, self.fixture.branch, date=DATE)
        self.assertTrue(slots[0].register_taken)

    def test_a_slot_carries_its_whole_selection_into_the_register(self):
        response = self.client.get(
            reverse("attendance:slot_register", args=[self.slot.pk]),
            {"date": DATE.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        for fragment in (
            f"school_class={self.fixture.school_class.pk}",
            f"section={self.fixture.section.pk}",
            f"class_subject={self.maths.pk}",
            "period=3",
            f"date={DATE.isoformat()}",
        ):
            self.assertIn(fragment, response.url)

    def test_a_slot_from_another_branch_is_not_reachable(self):
        other = build_branch(self.fixture.organization, name="Elsewhere", code="ELS")
        elsewhere = build_subject(other, "Elsewhere Subject")
        foreign_slot = Timetable.objects.create(
            branch=other.branch,
            organization=other.organization,
            academic_year=other.academic_year,
            section=other.section,
            class_subject=elsewhere,
            weekday=DATE.weekday(),
            period=1,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
        )
        response = self.client.get(
            reverse("attendance:slot_register", args=[foreign_slot.pk])
        )
        self.assertEqual(response.status_code, 404)
