"""Quran memorization (Hifz).

This module stays independent of the general academic record: a Hifz student's
day is measured in Sabaq (new lesson), Sabqi (recent revision) and Manzil (old
revision), not in periods and marks.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BranchOwnedModel
from apps.staff.models import Staff
from apps.students.models import Student

TOTAL_PARAS = 30
TOTAL_SURAHS = 114


class LessonType(models.TextChoices):
    """The three daily Hifz duties, plus the pre-Hifz stages."""

    SABAQ = "sabaq", _("Sabaq (new lesson)")
    SABQI = "sabqi", _("Sabqi (recent revision)")
    MANZIL = "manzil", _("Manzil (old revision)")
    NAZRA = "nazra", _("Nazra (recitation)")
    QAIDA = "qaida", _("Qaida (foundation)")


class Quality(models.IntegerChoices):
    EXCELLENT = 5, _("Excellent")
    VERY_GOOD = 4, _("Very Good")
    GOOD = 3, _("Good")
    FAIR = 2, _("Fair")
    WEAK = 1, _("Weak")


class HifzStudentProfile(BranchOwnedModel):
    """Where a student stands in the memorization programme."""

    class Stage(models.TextChoices):
        QAIDA = "qaida", _("Qaida")
        NAZRA = "nazra", _("Nazra")
        HIFZ = "hifz", _("Hifz")
        REVISION = "revision", _("Full Revision")
        COMPLETED = "completed", _("Completed")

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="hifz_profile",
        verbose_name=_("student"),
    )
    stage = models.CharField(
        _("stage"), max_length=20, choices=Stage.choices, default=Stage.QAIDA
    )
    started_on = models.DateField(_("started on"), null=True, blank=True)
    completed_on = models.DateField(_("completed on"), null=True, blank=True)
    current_para = models.PositiveSmallIntegerField(
        _("current para"),
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)],
    )
    current_surah = models.PositiveSmallIntegerField(
        _("current surah"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(TOTAL_SURAHS)],
    )
    paras_memorized = models.DecimalField(
        _("paras memorized"), max_digits=5, decimal_places=2, default=0
    )
    daily_target_lines = models.PositiveSmallIntegerField(
        _("daily target (lines)"), default=0
    )
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("hifz student")
        verbose_name_plural = _("hifz students")
        ordering = ["student__full_name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(paras_memorized__gte=0)
                & models.Q(paras_memorized__lte=TOTAL_PARAS),
                name="ck_hifz_paras_range",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "stage", "is_active"]),
            models.Index(fields=["branch", "current_para"]),
        ]

    def __str__(self):
        return f"{self.student} — {self.get_stage_display()}"

    @property
    def completion_percent(self):
        return round(float(self.paras_memorized) / TOTAL_PARAS * 100, 1)


class HifzTeacherAssignment(BranchOwnedModel):
    """Which teacher (ustadh) listens to which student."""

    hifz_profile = models.ForeignKey(
        HifzStudentProfile,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        verbose_name=_("hifz student"),
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.PROTECT,
        related_name="hifz_assignments",
        verbose_name=_("teacher"),
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("hifz teacher assignment")
        verbose_name_plural = _("hifz teacher assignments")
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["hifz_profile"],
                condition=models.Q(is_active=True),
                name="uq_active_hifz_teacher",
            )
        ]
        indexes = [models.Index(fields=["teacher", "is_active"])]

    def __str__(self):
        return f"{self.hifz_profile.student} — {self.teacher}"


class DailyProgress(BranchOwnedModel):
    """One heard lesson: Sabaq, Sabqi or Manzil on a given day."""

    hifz_profile = models.ForeignKey(
        HifzStudentProfile,
        on_delete=models.CASCADE,
        related_name="daily_progress",
        verbose_name=_("hifz student"),
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="heard_progress",
        verbose_name=_("heard by"),
    )
    date = models.DateField(_("date"), db_index=True)
    lesson_type = models.CharField(
        _("lesson type"), max_length=20, choices=LessonType.choices
    )
    from_para = models.PositiveSmallIntegerField(
        _("from para"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)],
    )
    to_para = models.PositiveSmallIntegerField(
        _("to para"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)],
    )
    surah = models.PositiveSmallIntegerField(
        _("surah"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(TOTAL_SURAHS)],
    )
    from_ayah = models.PositiveIntegerField(_("from ayah"), null=True, blank=True)
    to_ayah = models.PositiveIntegerField(_("to ayah"), null=True, blank=True)
    lines = models.DecimalField(
        _("lines"), max_digits=6, decimal_places=2, default=0
    )
    pages = models.DecimalField(
        _("pages"), max_digits=6, decimal_places=2, default=0
    )
    mistakes = models.PositiveSmallIntegerField(_("mistakes"), default=0)
    hesitations = models.PositiveSmallIntegerField(_("hesitations"), default=0)
    quality = models.PositiveSmallIntegerField(
        _("quality"), choices=Quality.choices, null=True, blank=True
    )
    is_repeated = models.BooleanField(_("repeated"), default=False)
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("daily progress")
        verbose_name_plural = _("daily progress")
        ordering = ["-date", "lesson_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["hifz_profile", "date", "lesson_type"],
                name="uq_hifz_daily_lesson",
            ),
            models.CheckConstraint(
                condition=models.Q(mistakes__gte=0), name="ck_hifz_mistakes"
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "date", "lesson_type"]),
            models.Index(fields=["hifz_profile", "date"]),
            models.Index(fields=["teacher", "date"]),
        ]

    def __str__(self):
        return f"{self.hifz_profile.student} — {self.get_lesson_type_display()} — {self.date}"


class Revision(BranchOwnedModel):
    """A planned Manzil cycle and how it went."""

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")
        MISSED = "missed", _("Missed")

    hifz_profile = models.ForeignKey(
        HifzStudentProfile,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name=_("hifz student"),
    )
    teacher = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hifz_revisions",
        verbose_name=_("teacher"),
    )
    from_para = models.PositiveSmallIntegerField(
        _("from para"), validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)]
    )
    to_para = models.PositiveSmallIntegerField(
        _("to para"), validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)]
    )
    scheduled_date = models.DateField(_("scheduled date"))
    completed_date = models.DateField(_("completed date"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    mistakes = models.PositiveSmallIntegerField(_("mistakes"), default=0)
    quality = models.PositiveSmallIntegerField(
        _("quality"), choices=Quality.choices, null=True, blank=True
    )
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("revision")
        verbose_name_plural = _("revisions")
        ordering = ["-scheduled_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_para__gte=models.F("from_para")),
                name="ck_revision_para_range",
            )
        ]
        indexes = [
            models.Index(fields=["branch", "scheduled_date", "status"]),
            models.Index(fields=["hifz_profile", "status"]),
        ]

    def __str__(self):
        return f"{self.hifz_profile.student} — {self.from_para}-{self.to_para}"


class HifzAssessment(BranchOwnedModel):
    """A formal test of a memorized range."""

    class Result(models.TextChoices):
        PASSED = "passed", _("Passed")
        FAILED = "failed", _("Failed")
        REPEAT = "repeat", _("Repeat")

    hifz_profile = models.ForeignKey(
        HifzStudentProfile,
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name=_("hifz student"),
    )
    examiner = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hifz_assessments",
        verbose_name=_("examiner"),
    )
    title = models.CharField(_("title"), max_length=200)
    date = models.DateField(_("date"))
    from_para = models.PositiveSmallIntegerField(
        _("from para"), validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)]
    )
    to_para = models.PositiveSmallIntegerField(
        _("to para"), validators=[MinValueValidator(1), MaxValueValidator(TOTAL_PARAS)]
    )
    total_marks = models.DecimalField(
        _("total marks"), max_digits=6, decimal_places=2, default=100
    )
    obtained_marks = models.DecimalField(
        _("obtained marks"), max_digits=6, decimal_places=2, default=0
    )
    mistakes = models.PositiveSmallIntegerField(_("mistakes"), default=0)
    result = models.CharField(
        _("result"), max_length=20, choices=Result.choices, default=Result.PASSED
    )
    remarks = models.TextField(_("remarks"), blank=True)

    class Meta:
        verbose_name = _("hifz assessment")
        verbose_name_plural = _("hifz assessments")
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(obtained_marks__gte=0)
                & models.Q(obtained_marks__lte=models.F("total_marks")),
                name="ck_hifz_assessment_marks",
            ),
            models.CheckConstraint(
                condition=models.Q(to_para__gte=models.F("from_para")),
                name="ck_hifz_assessment_range",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["hifz_profile", "date"]),
        ]

    def __str__(self):
        return f"{self.hifz_profile.student} — {self.title}"

    @property
    def percentage(self):
        if not self.total_marks:
            return 0
        return round(float(self.obtained_marks) / float(self.total_marks) * 100, 1)
