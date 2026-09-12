import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import ClassSubject, SchoolClass, Section, Subject, TeacherAssignment, Timetable
from apps.academics.tests.test_workflow import AcademicsFixture
from apps.core.tests.factories import build_staff


class AcademicsValidationTests(AcademicsFixture):
    def test_class_subject_duplicate_is_rejected_by_model(self):
        duplicate = ClassSubject(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            school_class=self.school_class,
            subject=self.subject,
            weekly_periods=4,
        )
        with self.assertRaises(ValidationError) as raised:
            duplicate.full_clean()
        self.assertIn("subject", raised.exception.message_dict)

    def test_teacher_assignment_must_match_academic_year(self):
        other_year = self.year.__class__.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="2027/28",
            start_date=dt.date(2027, 4, 1),
            end_date=dt.date(2028, 3, 31),
        )
        assignment = TeacherAssignment(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=other_year,
            teacher=self.teacher,
            class_subject=self.class_subject,
            section=self.section,
        )
        with self.assertRaises(ValidationError) as raised:
            assignment.full_clean()
        self.assertIn("class_subject", raised.exception.message_dict)

    def test_teacher_assignment_requires_a_teacher_for_the_class_subject(self):
        other_teacher = build_staff(self.fixture, "Other Teacher", "EMP-T2")
        assignment = TeacherAssignment(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            teacher=other_teacher,
            class_subject=self.class_subject,
            section=self.section,
        )
        assignment.full_clean()
        self.assertEqual(assignment.section.school_class_id, self.class_subject.school_class_id)

    def test_timetable_rejects_unassigned_teacher(self):
        other_teacher = build_staff(self.fixture, "Unassigned Teacher", "EMP-T3")
        slot = Timetable(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=self.section,
            class_subject=self.class_subject,
            teacher=other_teacher,
            weekday=0,
            period=2,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 40),
        )
        with self.assertRaises(ValidationError) as raised:
            slot.full_clean()
        self.assertIn("teacher", raised.exception.message_dict)

    def test_timetable_rejects_room_conflict(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Room Conflict Class",
            code="ROOM",
            level=8,
        )
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=other_class,
            name="A",
        )
        other_subject = Subject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Room Conflict Subject",
        )
        other_cs = ClassSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            school_class=other_class,
            subject=other_subject,
        )
        slot = Timetable(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=other_section,
            class_subject=other_cs,
            weekday=0,
            period=3,
            start_time=dt.time(10, 0),
            end_time=dt.time(10, 40),
            room="R-101",
        )
        Timetable.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=self.section,
            class_subject=self.class_subject,
            weekday=0,
            period=3,
            start_time=dt.time(10, 0),
            end_time=dt.time(10, 40),
            room="R-101",
        )
        with self.assertRaises(ValidationError) as raised:
            slot.full_clean()
        self.assertIn("room", raised.exception.message_dict)

    def test_timetable_duplicate_slot_is_rejected_by_model(self):
        duplicate = Timetable(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=self.section,
            class_subject=self.class_subject,
            weekday=0,
            period=1,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 40),
        )
        with self.assertRaises(ValidationError) as raised:
            duplicate.full_clean()
        self.assertIn("__all__", raised.exception.message_dict)
