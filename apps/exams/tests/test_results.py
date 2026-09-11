"""Marks, result generation and publication."""

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.tests.factories import (
    build_branch,
    build_student,
    build_subject,
    build_user,
)
from apps.exams.models import Exam, ExamSubject, ExamTerm, Grade, ResultSummary
from apps.exams.services import (
    generate_results,
    publish_results,
    register_students,
    save_marks,
)

START = dt.date(2026, 6, 1)


class ResultGenerationTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="examiner")
        self.class_subject = build_subject(self.fixture, "Mathematics")
        self.second_subject = build_subject(self.fixture, "Arabic")

        for name, percentage in (("A", 80), ("B", 60), ("C", 40), ("F", 0)):
            Grade.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                academic_year=self.fixture.academic_year,
                name=name,
                min_percentage=Decimal(percentage),
                max_percentage=Decimal(percentage + 19 if percentage else 39),
                is_pass=percentage >= 40,
            )
        Grade.objects.filter(name="A").update(max_percentage=Decimal("100"))

        self.term = ExamTerm.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.fixture.academic_year,
            name="Mid Term",
        )
        self.exam = Exam.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            exam_term=self.term,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            name="Mid Term Exam",
            start_date=START,
        )
        self.maths = ExamSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            exam=self.exam,
            class_subject=self.class_subject,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("40.00"),
        )
        self.arabic = ExamSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            exam=self.exam,
            class_subject=self.second_subject,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("40.00"),
        )

        self.top = build_student(self.fixture, "Top Student", "E-001")
        self.weak = build_student(self.fixture, "Weak Student", "E-002")
        register_students(exam=self.exam, actor=self.actor)

    def _student_exam(self, student):
        return self.exam.student_exams.get(student=student)

    def _enter(self, student, maths, arabic):
        save_marks(
            exam_subject=self.maths,
            entries={self._student_exam(student): {"obtained_marks": maths}},
            actor=self.actor,
        )
        save_marks(
            exam_subject=self.arabic,
            entries={self._student_exam(student): {"obtained_marks": arabic}},
            actor=self.actor,
        )

    def test_registration_enrols_the_whole_class(self):
        self.assertEqual(self.exam.student_exams.count(), 2)

    def test_re_registering_adds_nobody_twice(self):
        register_students(exam=self.exam, actor=self.actor)
        self.assertEqual(self.exam.student_exams.count(), 2)

    def test_marks_above_the_paper_total_are_refused(self):
        with self.assertRaises(ValidationError):
            save_marks(
                exam_subject=self.maths,
                entries={self._student_exam(self.top): {"obtained_marks": 150}},
                actor=self.actor,
            )

    def test_results_are_computed_from_the_marks(self):
        self._enter(self.top, 90, 80)
        self._enter(self.weak, 30, 35)
        generate_results(exam=self.exam, actor=self.actor)

        top = ResultSummary.objects.get(student_exam__student=self.top)
        weak = ResultSummary.objects.get(student_exam__student=self.weak)

        self.assertEqual(top.obtained_marks, Decimal("170.00"))
        self.assertEqual(top.total_marks, Decimal("200.00"))
        self.assertEqual(top.percentage, Decimal("85.00"))
        self.assertEqual(top.outcome, ResultSummary.Outcome.PASS)
        self.assertEqual(top.grade.name, "A")

        self.assertEqual(weak.outcome, ResultSummary.Outcome.FAIL)
        self.assertEqual(weak.subjects_failed, 2)

    def test_positions_are_ordered_by_percentage(self):
        self._enter(self.top, 90, 80)
        self._enter(self.weak, 30, 35)
        generate_results(exam=self.exam, actor=self.actor)

        self.assertEqual(
            ResultSummary.objects.get(student_exam__student=self.top).position, 1
        )
        self.assertEqual(
            ResultSummary.objects.get(student_exam__student=self.weak).position, 2
        )

    def test_a_tie_shares_a_position(self):
        self._enter(self.top, 70, 70)
        self._enter(self.weak, 70, 70)
        generate_results(exam=self.exam, actor=self.actor)
        positions = set(
            ResultSummary.objects.values_list("position", flat=True)
        )
        self.assertEqual(positions, {1})

    def test_regenerating_after_a_correction_updates_the_summary(self):
        self._enter(self.top, 50, 50)
        generate_results(exam=self.exam, actor=self.actor)
        self.assertEqual(
            ResultSummary.objects.get(student_exam__student=self.top).percentage,
            Decimal("50.00"),
        )

        self._enter(self.top, 90, 90)
        generate_results(exam=self.exam, actor=self.actor)
        self.assertEqual(
            ResultSummary.objects.get(student_exam__student=self.top).percentage,
            Decimal("90.00"),
        )

    def test_publishing_requires_generated_results(self):
        with self.assertRaises(ValidationError):
            publish_results(exam=self.exam, actor=self.actor)

    def test_publishing_marks_the_exam_published(self):
        self._enter(self.top, 90, 80)
        self._enter(self.weak, 50, 50)
        generate_results(exam=self.exam, actor=self.actor)
        publish_results(exam=self.exam, actor=self.actor)

        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_published)
        self.assertIsNotNone(self.exam.published_at)

    def test_marks_cannot_be_edited_once_published(self):
        self._enter(self.top, 90, 80)
        self._enter(self.weak, 50, 50)
        generate_results(exam=self.exam, actor=self.actor)
        publish_results(exam=self.exam, actor=self.actor)

        self.maths.refresh_from_db()
        with self.assertRaises(ValidationError):
            save_marks(
                exam_subject=self.maths,
                entries={self._student_exam(self.top): {"obtained_marks": 100}},
                actor=self.actor,
            )

    def test_an_absent_student_scores_zero(self):
        save_marks(
            exam_subject=self.maths,
            entries={
                self._student_exam(self.top): {"obtained_marks": 0, "is_absent": True}
            },
            actor=self.actor,
        )
        save_marks(
            exam_subject=self.arabic,
            entries={self._student_exam(self.top): {"obtained_marks": 80}},
            actor=self.actor,
        )
        generate_results(exam=self.exam, actor=self.actor)

        summary = ResultSummary.objects.get(student_exam__student=self.top)
        self.assertEqual(summary.obtained_marks, Decimal("80.00"))
        self.assertEqual(summary.outcome, ResultSummary.Outcome.FAIL)
