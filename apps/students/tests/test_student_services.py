"""Admission, enrollment, transfer, status changes and soft delete."""

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import SchoolClass, Section
from apps.core.tests.factories import build_branch, build_student, build_user
from apps.students.models import (
    Student,
    StudentClassHistory,
    StudentEnrollment,
    StudentStatusHistory,
)
from apps.students.services import (
    admit_student,
    change_student_status,
    next_admission_number,
    transfer_student,
)

PASSWORD = "Str0ngPassphrase!42"
DATE = dt.date(2026, 6, 1)


class AdmissionTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="registrar")

    def test_admission_creates_a_student_and_an_enrollment(self):
        student, enrollment = admit_student(
            branch=self.fixture.branch,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            section=self.fixture.section,
            full_name="New Student",
            admission_date=DATE,
            actor=self.actor,
        )
        self.assertTrue(enrollment.is_current)
        self.assertEqual(student.current_enrollment, enrollment)
        self.assertEqual(StudentClassHistory.objects.filter(student=student).count(), 1)

    def test_admission_numbers_are_generated_and_sequential(self):
        first = build_student(self.fixture, "One")
        second = build_student(self.fixture, "Two")
        self.assertNotEqual(first.admission_no, second.admission_no)
        self.assertTrue(first.admission_no.startswith(self.fixture.branch.code.upper()))

    def test_the_next_admission_number_follows_the_last(self):
        build_student(self.fixture, "One")
        candidate = next_admission_number(self.fixture.branch)
        self.assertFalse(
            Student.all_objects.filter(
                branch=self.fixture.branch, admission_no=candidate
            ).exists()
        )

    def test_a_section_from_another_class_is_refused(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Grade 2",
            code="G2",
            level=2,
        )
        with self.assertRaises(ValidationError):
            admit_student(
                branch=self.fixture.branch,
                academic_year=self.fixture.academic_year,
                school_class=other_class,
                section=self.fixture.section,
                full_name="Mismatched",
                actor=self.actor,
            )

    def test_a_failed_admission_leaves_no_half_record(self):
        before = Student.all_objects.count()
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Grade 3",
            code="G3",
            level=3,
        )
        with self.assertRaises(ValidationError):
            admit_student(
                branch=self.fixture.branch,
                academic_year=self.fixture.academic_year,
                school_class=other_class,
                section=self.fixture.section,
                full_name="Rolled Back",
                actor=self.actor,
            )
        self.assertEqual(Student.all_objects.count(), before)


class TransferAndStatusTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="registrar")
        self.student = build_student(self.fixture)
        self.grade_two = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Grade 2",
            code="G2",
            level=2,
        )
        self.grade_two_a = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=self.grade_two,
            name="A",
        )

    def test_a_transfer_moves_the_current_enrollment(self):
        transfer_student(
            student=self.student,
            school_class=self.grade_two,
            section=self.grade_two_a,
            moved_on=DATE,
            reason="Promotion",
            actor=self.actor,
        )
        enrollment = self.student.enrollments.get(is_current=True)
        self.assertEqual(enrollment.school_class, self.grade_two)
        self.assertEqual(
            StudentClassHistory.objects.filter(student=self.student).count(), 2
        )

    def test_a_status_change_is_recorded_and_ends_the_enrollment(self):
        change_student_status(
            student=self.student,
            new_status=Student.Status.WITHDRAWN,
            effective_date=DATE,
            reason="Moved city",
            actor=self.actor,
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.Status.WITHDRAWN)
        self.assertFalse(
            StudentEnrollment.objects.filter(
                student=self.student, is_current=True
            ).exists()
        )
        self.assertEqual(
            StudentStatusHistory.objects.filter(student=self.student).count(), 1
        )

    def test_setting_the_same_status_changes_nothing(self):
        change_student_status(
            student=self.student,
            new_status=Student.Status.ACTIVE,
            effective_date=DATE,
            actor=self.actor,
        )
        self.assertEqual(
            StudentStatusHistory.objects.filter(student=self.student).count(), 0
        )

    def test_enrolling_in_a_new_year_closes_the_previous_enrollment(self):
        from apps.academics.models import AcademicYear
        from apps.students.services import enroll_student

        next_year = AcademicYear.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="2027",
            start_date=dt.date(2027, 1, 1),
            end_date=dt.date(2027, 12, 31),
        )
        enroll_student(
            student=self.student,
            academic_year=next_year,
            school_class=self.grade_two,
            section=self.grade_two_a,
            start_date=dt.date(2027, 1, 1),
            actor=self.actor,
        )

        self.assertEqual(
            StudentEnrollment.objects.filter(
                student=self.student, is_current=True
            ).count(),
            1,
        )
        self.assertEqual(
            StudentEnrollment.objects.filter(student=self.student).count(), 2
        )

    def test_a_student_cannot_be_enrolled_twice_in_one_year(self):
        from apps.students.services import enroll_student

        # One enrollment per academic year; moving class inside a year is a
        # transfer, not a second enrollment.
        with self.assertRaises(ValidationError):
            enroll_student(
                student=self.student,
                academic_year=self.fixture.academic_year,
                school_class=self.grade_two,
                section=self.grade_two_a,
                start_date=DATE,
                actor=self.actor,
            )


class SoftDeleteTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.student = build_student(self.fixture)

    def test_deleting_hides_the_row_without_erasing_it(self):
        self.student.delete()
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(Student.all_objects.filter(pk=self.student.pk).exists())

    def test_restoring_needs_the_restore_permission(self):
        self.student.delete()
        build_user(self.fixture.branch, username="ordinary")
        self.client.login(username="ordinary", password=PASSWORD)
        response = self.client.post(
            reverse("students:student_restore", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_deleted)

    def test_an_authorised_user_can_restore(self):
        self.student.delete()
        build_user(
            self.fixture.branch,
            username="restorer",
            permissions=["core.restore_record"],
            role_name="Restorer",
        )
        self.client.login(username="restorer", password=PASSWORD)
        response = self.client.post(
            reverse("students:student_restore", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_deleted)

    def test_a_restore_is_logged(self):
        from apps.audit.models import ActivityLog

        self.student.delete()
        build_user(
            self.fixture.branch,
            username="restorer2",
            permissions=["core.restore_record"],
            role_name="Restorer",
        )
        self.client.login(username="restorer2", password=PASSWORD)
        self.client.post(reverse("students:student_restore", args=[self.student.pk]))
        self.assertTrue(ActivityLog.objects.filter(action="restore").exists())
