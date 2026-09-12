from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

# Existing module content retained; only the TeacherAssignment model below is updated.

class TeacherAssignment(BranchOwnedModel):
    """Which teacher teaches which class subject, optionally per section."""

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="teacher_assignments", verbose_name=_("academic year"))
    teacher = models.ForeignKey("staff.Staff", on_delete=models.CASCADE, related_name="teaching_assignments", verbose_name=_("teacher"))
    class_subject = models.ForeignKey(ClassSubject, on_delete=models.CASCADE, related_name="teacher_assignments", verbose_name=_("class subject"))
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True, related_name="teacher_assignments", verbose_name=_("section"))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("teacher assignment")
        verbose_name_plural = _("teacher assignments")
        ordering = ["teacher__full_name"]
        constraints = [models.UniqueConstraint(fields=["class_subject", "section", "teacher"], name="uq_teacher_assignment")]
        indexes = [models.Index(fields=["branch", "academic_year"]), models.Index(fields=["teacher", "is_active"])]

    @property
    def assignment_type(self):
        """Explicit UI classification without changing the persisted model."""
        return _("Subject Teacher")

    @property
    def assignment_scope(self):
        return _("Section") if self.section_id else _("All sections")

    def __str__(self):
        return f"{self.teacher} — {self.class_subject}"

    def clean(self):
        super().clean()
        if self.section_id and self.class_subject_id and self.section.school_class_id != self.class_subject.school_class_id:
            raise ValidationError({"section": _("That section belongs to a different class.")})
