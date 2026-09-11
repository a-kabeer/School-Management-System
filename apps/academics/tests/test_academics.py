"""Academic structure constraints."""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.academics.forms import TeacherAssignmentForm, TimetableForm
from apps.academics.models import AcademicYear, SchoolClass, Section, Timetable
from apps.core.tests.factories import build_branch, build_staff, build_subject, two_branches


class AcademicYearTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()

    def test_only_one_year_can_be_current(self):
        with self.assertRaises(IntegrityError):
            AcademicYear.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                name="Another 2026",
                start_date=dt.date(2027, 1, 1),
                end_date=dt.date(2027, 12, 31),
                is_current=True,
            )

    def test_the_end_date_must_follow_the_start(self):
        year = AcademicYear(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Backwards",
            start_date=dt.date(2026, 12, 31),
            end_date=dt.date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            year.clean()

    def test_two_branches_can_each_have_a_current_year(self):
        branch_a, branch_b = two_branches()
        self.assertTrue(
            AcademicYear.objects.filter(
                branch=branch_a.branch, is_current=True
            ).exists()
        )
        self.assertTrue(
            AcademicYear.objects.filter(
                branch=branch_b.branch, is_current=True
            ).exists()
        )


class TimetableTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.class_subject = build_subject(self.fixture)
        self.teacher = build_staff(self.fixture)

    def _slot(self, period, weekday=Timetable.Weekday.MONDAY):
        return Timetable.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.fixture.academic_year,
            section=self.fixture.section,
            class_subject=self.class_subject,
            teacher=self.teacher,
            weekday=weekday,
            period=period,
            start_time=dt.time(8, 0),
            end_time=dt.time(8, 40),
        )

    def test_a_section_cannot_have_two_slots_in_one_period(self):
        self._slot(1)
        with self.assertRaises(IntegrityError):
            self._slot(1)

    def test_the_end_time_must_follow_the_start(self):
        form = TimetableForm(
            data={
                "academic_year": str(self.fixture.academic_year.pk),
                "section": str(self.fixture.section.pk),
                "class_subject": str(self.class_subject.pk),
                "weekday": Timetable.Weekday.MONDAY,
                "period": 1,
                "start_time": "09:00",
                "end_time": "08:00",
            },
            branch=self.fixture.branch,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("end_time", form.errors)

    def test_a_teacher_cannot_be_in_two_places_at_once(self):
        self._slot(1)
        second_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Grade 2",
            code="G2",
            level=2,
        )
        second_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=second_class,
            name="A",
        )
        form = TimetableForm(
            data={
                "academic_year": str(self.fixture.academic_year.pk),
                "section": str(second_section.pk),
                "class_subject": str(self.class_subject.pk),
                "teacher": str(self.teacher.pk),
                "weekday": Timetable.Weekday.MONDAY,
                "period": 1,
                "start_time": "08:00",
                "end_time": "08:40",
            },
            branch=self.fixture.branch,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("teacher", form.errors)


class TenantScopedFormTests(TestCase):
    def test_a_form_only_offers_this_branch_relations(self):
        branch_a, branch_b = two_branches()
        subject_b = build_subject(branch_b)
        teacher_a = build_staff(branch_a)

        form = TeacherAssignmentForm(branch=branch_a.branch)
        self.assertIn(teacher_a, form.fields["teacher"].queryset)
        self.assertNotIn(subject_b, form.fields["class_subject"].queryset)

    def test_posting_another_branch_relation_fails_validation(self):
        branch_a, branch_b = two_branches()
        subject_b = build_subject(branch_b)
        teacher_a = build_staff(branch_a)

        form = TeacherAssignmentForm(
            data={
                "academic_year": str(branch_a.academic_year.pk),
                "teacher": str(teacher_a.pk),
                "class_subject": str(subject_b.pk),
                "is_active": True,
            },
            branch=branch_a.branch,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("class_subject", form.errors)
