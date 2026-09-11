"""Exam service layer: registration, marks, result generation, publication."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity, snapshot

from .models import Exam, Grade, Mark, Result, ResultSummary, StudentExam

ZERO = Decimal("0.00")


def grade_for(academic_year, percentage):
    """The grading band a percentage falls into, or ``None`` if unset."""
    return (
        Grade.objects.filter(
            academic_year=academic_year,
            min_percentage__lte=percentage,
            max_percentage__gte=percentage,
        )
        .order_by("-min_percentage")
        .first()
    )


@transaction.atomic
def register_students(*, exam, students=None, actor=None, request=None):
    """Enrol a class into an exam. Re-running it adds only the newcomers."""
    from apps.students.models import Student

    if students is None:
        students = Student.objects.filter(
            branch=exam.branch,
            status=Student.Status.ACTIVE,
            enrollments__school_class=exam.school_class,
            enrollments__is_current=True,
        ).distinct()

    existing = set(
        StudentExam.objects.filter(exam=exam).values_list("student_id", flat=True)
    )
    created = []
    for student in students:
        if student.pk in existing:
            continue
        enrollment = student.enrollments.filter(is_current=True).first()
        created.append(
            StudentExam(
                branch=exam.branch,
                organization=exam.organization,
                exam=exam,
                student=student,
                section=enrollment.section if enrollment else None,
                roll_number=enrollment.roll_number if enrollment else "",
            )
        )
    StudentExam.objects.bulk_create(created)

    log_activity(
        action="create",
        request=request,
        user=actor,
        instance=exam,
        new_values={"registered": len(created)},
        metadata={"event": "exam_registration"},
    )
    return created


@transaction.atomic
def save_marks(*, exam_subject, entries, actor=None, request=None):
    """Enter or correct marks for one paper.

    ``entries`` maps a ``StudentExam`` to ``{"obtained_marks": .., "is_absent": ..}``.
    """
    if exam_subject.exam.is_published:
        raise ValidationError(
            _("Results are published; unpublish the exam before editing marks.")
        )

    saved = 0
    for student_exam, values in entries.items():
        if student_exam.exam_id != exam_subject.exam_id:
            raise ValidationError(_("That student is not registered for this exam."))

        obtained = Decimal(str(values.get("obtained_marks") or 0))
        if obtained < ZERO or obtained > exam_subject.total_marks:
            raise ValidationError(
                {
                    "obtained_marks": _("Marks for %(student)s must be between 0 and %(total)s.")
                    % {"student": student_exam.student, "total": exam_subject.total_marks}
                }
            )

        Mark.objects.update_or_create(
            student_exam=student_exam,
            exam_subject=exam_subject,
            defaults={
                "branch": exam_subject.branch,
                "organization": exam_subject.organization,
                "obtained_marks": obtained,
                "is_absent": bool(values.get("is_absent")),
                "remarks": (values.get("remarks") or "")[:255],
                "entered_by": actor,
            },
        )
        saved += 1

    if exam_subject.exam.status == Exam.Status.PLANNED:
        exam_subject.exam.status = Exam.Status.MARKING
        exam_subject.exam.save(update_fields=["status", "updated_at"])

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=exam_subject,
        new_values={"marks_saved": saved},
        metadata={"event": "marks_entered"},
    )
    return saved


@transaction.atomic
def generate_results(*, exam, actor=None, request=None):
    """Turn raw marks into per-subject results and per-student summaries.

    Results are derived, never typed in, so re-running this after a mark
    correction always produces a consistent report card.
    """
    subjects = list(exam.exam_subjects.select_related("class_subject__subject"))
    if not subjects:
        raise ValidationError(_("Add subjects to this exam first."))

    student_exams = list(
        exam.student_exams.select_related("student").prefetch_related("marks")
    )
    if not student_exams:
        raise ValidationError(_("No students are registered for this exam."))

    subject_totals = {s.pk: s for s in subjects}
    summaries = []

    for student_exam in student_exams:
        marks = {m.exam_subject_id: m for m in student_exam.marks.all()}
        total_marks = ZERO
        obtained_total = ZERO
        passed = 0
        failed = 0

        for subject in subjects:
            mark = marks.get(subject.pk)
            obtained = ZERO if mark is None or mark.is_absent else mark.obtained_marks
            percentage = (
                (obtained / subject.total_marks * 100) if subject.total_marks else ZERO
            ).quantize(Decimal("0.01"))
            is_pass = obtained >= subject.passing_marks and not (
                mark is not None and mark.is_absent
            )

            Result.objects.update_or_create(
                student_exam=student_exam,
                exam_subject=subject,
                defaults={
                    "branch": exam.branch,
                    "organization": exam.organization,
                    "obtained_marks": obtained,
                    "total_marks": subject.total_marks,
                    "percentage": percentage,
                    "grade": grade_for(exam.academic_year, percentage),
                    "is_pass": is_pass,
                },
            )

            total_marks += subject.total_marks
            obtained_total += obtained
            passed += 1 if is_pass else 0
            failed += 0 if is_pass else 1

        overall_percentage = (
            (obtained_total / total_marks * 100) if total_marks else ZERO
        ).quantize(Decimal("0.01"))

        summary, _created = ResultSummary.objects.update_or_create(
            student_exam=student_exam,
            defaults={
                "branch": exam.branch,
                "organization": exam.organization,
                "total_marks": total_marks,
                "obtained_marks": obtained_total,
                "percentage": overall_percentage,
                "grade": grade_for(exam.academic_year, overall_percentage),
                "subjects_passed": passed,
                "subjects_failed": failed,
                "outcome": (
                    ResultSummary.Outcome.PASS
                    if failed == 0
                    else ResultSummary.Outcome.FAIL
                ),
                "generated_at": timezone.now(),
            },
        )
        summaries.append(summary)

    # Positions are assigned after every summary exists, so a tie in
    # percentage produces the same position for both students.
    summaries.sort(key=lambda s: s.percentage, reverse=True)
    previous_percentage = None
    position = 0
    for index, summary in enumerate(summaries, start=1):
        if summary.percentage != previous_percentage:
            position = index
            previous_percentage = summary.percentage
        summary.position = position
    ResultSummary.objects.bulk_update(summaries, ["position"])

    exam.status = Exam.Status.MARKING
    exam.save(update_fields=["status", "updated_at"])

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=exam,
        new_values={"summaries": len(summaries), "subjects": len(subject_totals)},
        metadata={"event": "results_generated"},
    )
    return summaries


@transaction.atomic
def publish_results(*, exam, actor=None, request=None):
    """Make results visible to students and parents."""
    if not ResultSummary.objects.filter(student_exam__exam=exam).exists():
        raise ValidationError(_("Generate the results before publishing."))

    previous = snapshot(exam)
    exam.status = Exam.Status.PUBLISHED
    exam.published_at = timezone.now()
    exam.published_by = actor
    exam.save(update_fields=["status", "published_at", "published_by", "updated_at"])

    log_activity(
        action="publish",
        request=request,
        user=actor,
        instance=exam,
        previous_values=previous,
        new_values=snapshot(exam),
        metadata={"event": "results_published"},
    )

    from apps.notifications.services import notify_result_published

    notify_result_published(exam=exam, actor=actor)
    return exam


@transaction.atomic
def unpublish_results(*, exam, actor=None, request=None):
    exam.status = Exam.Status.MARKING
    exam.published_at = None
    exam.save(update_fields=["status", "published_at", "updated_at"])
    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=exam,
        new_values={"status": exam.status},
        metadata={"event": "results_unpublished"},
    )
    return exam


def report_card(student_exam):
    """Everything one report card needs, in one place."""
    return {
        "student_exam": student_exam,
        "results": student_exam.results.select_related(
            "exam_subject__class_subject__subject", "grade"
        ).order_by("exam_subject__class_subject__subject__name"),
        "summary": getattr(student_exam, "summary", None),
    }
