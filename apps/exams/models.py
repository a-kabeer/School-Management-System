"""Examinations, marks, grades and results."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, ClassSubject, SchoolClass, Section, Term
from apps.core.models import BranchOwnedModel
from apps.students.models import Student


class Grade(BranchOwnedModel):
    """One band of the grading scale, e.g. A+ from 90 to 100."""

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="grades",
        verbose_name=_("academic year"),
    )
    name = models.CharField(_("grade"), max_length=20)
    min_percentage = models.DecimalField(
        _("minimum %"), max_digits=5, decimal_places=2
    )
    max_percentage = models.DecimalField(
        _("maximum %"), max_digits=5, decimal_places=2
    )
    grade_point = models.DecimalField(
        _("grade point"), max_digits=4, decimal_places=2, default=Decimal("0.00")
    )
    remark = models.CharField(_("remark"), max_length=100, blank=True)
    is_pass = models.BooleanField(_("counts as pass"), default=True)

    class Meta:
        verbose_name = _("grade")
        verbose_name_plural = _("grading scale")
        ordering = ["-min_percentage"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "name"], name="uq_grade_name"
            ),
            models.CheckConstraint(
                condition=models.Q(max_percentage__gte=models.F("min_percentage")),
                name="ck_grade_range",
            ),
        ]
        indexes = [models.Index(fields=["branch", "academic_year"])]

    def __str__(self):
        return self.name


class ExamTerm(BranchOwnedModel):
    """A group of exams, e.g. "Mid Term" or "Final"."""

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="exam_terms",
        verbose_name=_("academic year"),
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_terms",
        verbose_name=_("term"),
    )
    name = models.CharField(_("name"), max_length=150)
    sequence = models.PositiveSmallIntegerField(_("sequence"), default=1)
    weight_percentage = models.DecimalField(
        _("weight %"), max_digits=5, decimal_places=2, default=Decimal("100.00")
    )

    class Meta:
        verbose_name = _("exam term")
        verbose_name_plural = _("exam terms")
        ordering = ["academic_year", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "name"], name="uq_exam_term_name"
            )
        ]

    def __str__(self):
        return self.name


class Exam(BranchOwnedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        ONGOING = "ongoing", _("Ongoing")
        MARKING = "marking", _("Marking")
        PUBLISHED = "published", _("Published")
        CANCELLED = "cancelled", _("Cancelled")

    exam_term = models.ForeignKey(
        ExamTerm,
        on_delete=models.PROTECT,
        related_name="exams",
        verbose_name=_("exam term"),
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="exams",
        verbose_name=_("academic year"),
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.PROTECT,
        related_name="exams",
        verbose_name=_("class"),
    )
    name = models.CharField(_("name"), max_length=200)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_exams",
        verbose_name=_("published by"),
    )
    instructions = models.TextField(_("instructions"), blank=True)

    class Meta:
        verbose_name = _("exam")
        verbose_name_plural = _("exams")
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "exam_term", "school_class", "name"],
                name="uq_exam_name",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "academic_year", "status"]),
            models.Index(fields=["branch", "start_date"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.school_class}"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED


class ExamSubject(BranchOwnedModel):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_subjects",
        verbose_name=_("exam"),
    )
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.PROTECT,
        related_name="exam_subjects",
        verbose_name=_("subject"),
    )
    total_marks = models.DecimalField(
        _("total marks"), max_digits=7, decimal_places=2, default=Decimal("100.00")
    )
    passing_marks = models.DecimalField(
        _("passing marks"), max_digits=7, decimal_places=2, default=Decimal("40.00")
    )
    weight_percentage = models.DecimalField(
        _("weight %"), max_digits=5, decimal_places=2, default=Decimal("100.00")
    )

    class Meta:
        verbose_name = _("exam subject")
        verbose_name_plural = _("exam subjects")
        ordering = ["class_subject__subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "class_subject"], name="uq_exam_subject"
            ),
            models.CheckConstraint(
                condition=models.Q(passing_marks__lte=models.F("total_marks")),
                name="ck_exam_subject_marks",
            ),
        ]
        indexes = [models.Index(fields=["branch", "exam"])]

    def __str__(self):
        return f"{self.exam.name} — {self.class_subject.subject.name}"


class ExamSchedule(BranchOwnedModel):
    """When and where a subject paper is sat."""

    exam_subject = models.ForeignKey(
        ExamSubject,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("exam subject"),
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exam_schedules",
        verbose_name=_("section"),
    )
    date = models.DateField(_("date"))
    start_time = models.TimeField(_("start time"))
    end_time = models.TimeField(_("end time"))
    room = models.CharField(_("room"), max_length=100, blank=True)
    invigilator = models.ForeignKey(
        "staff.Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invigilations",
        verbose_name=_("invigilator"),
    )

    class Meta:
        verbose_name = _("exam schedule")
        verbose_name_plural = _("exam schedules")
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam_subject", "section"], name="uq_exam_schedule"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="ck_exam_schedule_times",
            ),
        ]
        indexes = [models.Index(fields=["branch", "date"])]

    def __str__(self):
        return f"{self.exam_subject} — {self.date}"


class StudentExam(BranchOwnedModel):
    """A student's registration for an exam."""

    class Status(models.TextChoices):
        REGISTERED = "registered", _("Registered")
        APPEARED = "appeared", _("Appeared")
        ABSENT = "absent", _("Absent")
        EXEMPTED = "exempted", _("Exempted")
        DISQUALIFIED = "disqualified", _("Disqualified")

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="student_exams",
        verbose_name=_("exam"),
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="student_exams",
        verbose_name=_("student"),
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_exams",
        verbose_name=_("section"),
    )
    roll_number = models.CharField(_("roll number"), max_length=50, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.REGISTERED
    )

    class Meta:
        verbose_name = _("student exam")
        verbose_name_plural = _("student exams")
        ordering = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"], name="uq_student_exam"
            )
        ]
        indexes = [
            models.Index(fields=["branch", "exam", "status"]),
            models.Index(fields=["student", "exam"]),
        ]

    def __str__(self):
        return f"{self.student} — {self.exam}"


class Mark(BranchOwnedModel):
    """Raw marks entered by a teacher for one paper."""

    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="marks",
        verbose_name=_("student exam"),
    )
    exam_subject = models.ForeignKey(
        ExamSubject,
        on_delete=models.CASCADE,
        related_name="marks",
        verbose_name=_("exam subject"),
    )
    obtained_marks = models.DecimalField(
        _("obtained marks"), max_digits=7, decimal_places=2, default=Decimal("0.00")
    )
    is_absent = models.BooleanField(_("absent"), default=False)
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)
    entered_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entered_marks",
        verbose_name=_("entered by"),
    )

    class Meta:
        verbose_name = _("mark")
        verbose_name_plural = _("marks")
        ordering = ["exam_subject__class_subject__subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student_exam", "exam_subject"], name="uq_student_subject_mark"
            ),
            models.CheckConstraint(
                condition=models.Q(obtained_marks__gte=0), name="ck_mark_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["branch", "exam_subject"])]

    def __str__(self):
        return f"{self.student_exam.student} — {self.obtained_marks}"

    def clean(self):
        super().clean()
        if (
            self.exam_subject_id
            and self.obtained_marks > self.exam_subject.total_marks
        ):
            raise ValidationError(
                {"obtained_marks": _("Marks cannot exceed the paper total.")}
            )


class Result(BranchOwnedModel):
    """Per-subject outcome computed from a :class:`Mark`."""

    student_exam = models.ForeignKey(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("student exam"),
    )
    exam_subject = models.ForeignKey(
        ExamSubject,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("exam subject"),
    )
    obtained_marks = models.DecimalField(
        _("obtained marks"), max_digits=7, decimal_places=2, default=Decimal("0.00")
    )
    total_marks = models.DecimalField(
        _("total marks"), max_digits=7, decimal_places=2, default=Decimal("0.00")
    )
    percentage = models.DecimalField(
        _("percentage"), max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
        verbose_name=_("grade"),
    )
    is_pass = models.BooleanField(_("passed"), default=False)

    class Meta:
        verbose_name = _("result")
        verbose_name_plural = _("results")
        ordering = ["exam_subject__class_subject__subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student_exam", "exam_subject"], name="uq_subject_result"
            )
        ]
        indexes = [
            models.Index(fields=["branch", "student_exam"]),
            models.Index(fields=["branch", "exam_subject", "is_pass"]),
        ]

    def __str__(self):
        return f"{self.student_exam.student} — {self.percentage}%"


class ResultSummary(BranchOwnedModel):
    """A student's overall standing in one exam - the report card header."""

    class Outcome(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")
        PENDING = "pending", _("Pending")

    student_exam = models.OneToOneField(
        StudentExam,
        on_delete=models.CASCADE,
        related_name="summary",
        verbose_name=_("student exam"),
    )
    total_marks = models.DecimalField(
        _("total marks"), max_digits=9, decimal_places=2, default=Decimal("0.00")
    )
    obtained_marks = models.DecimalField(
        _("obtained marks"), max_digits=9, decimal_places=2, default=Decimal("0.00")
    )
    percentage = models.DecimalField(
        _("percentage"), max_digits=6, decimal_places=2, default=Decimal("0.00")
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="summaries",
        verbose_name=_("grade"),
    )
    subjects_passed = models.PositiveSmallIntegerField(_("subjects passed"), default=0)
    subjects_failed = models.PositiveSmallIntegerField(_("subjects failed"), default=0)
    position = models.PositiveIntegerField(_("position"), null=True, blank=True)
    outcome = models.CharField(
        _("outcome"), max_length=20, choices=Outcome.choices, default=Outcome.PENDING
    )
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)
    generated_at = models.DateTimeField(_("generated at"), null=True, blank=True)

    class Meta:
        verbose_name = _("result summary")
        verbose_name_plural = _("result summaries")
        ordering = ["position"]
        indexes = [
            models.Index(fields=["branch", "outcome"]),
            models.Index(fields=["branch", "percentage"]),
        ]

    def __str__(self):
        return f"{self.student_exam.student} — {self.percentage}%"
