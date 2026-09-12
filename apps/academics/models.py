"""Academic structure: years, terms, classes, sections, subjects, timetable."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BranchOwnedModel

from .timetable_config import is_working_day


class AcademicYear(BranchOwnedModel):
    """A school year within one branch."""
    name = models.CharField(_("name"), max_length=100)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))
    is_current = models.BooleanField(_("current"), default=False)
    is_closed = models.BooleanField(_("closed"), default=False)
    class Meta:
        verbose_name = _("academic year"); verbose_name_plural = _("academic years"); ordering = ["-start_date"]
        constraints = [models.UniqueConstraint(fields=["branch", "name"], name="uq_academic_year_name"), models.UniqueConstraint(fields=["branch"], condition=models.Q(is_current=True), name="uq_single_current_academic_year"), models.CheckConstraint(condition=models.Q(end_date__gt=models.F("start_date")), name="ck_academic_year_dates")]
        indexes = [models.Index(fields=["branch", "is_current"])]
    def __str__(self): return self.name
    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date <= self.start_date: raise ValidationError({"end_date": _("End date must be after the start date.")})


class Term(BranchOwnedModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms", verbose_name=_("academic year"))
    name = models.CharField(_("name"), max_length=100); sequence = models.PositiveSmallIntegerField(_("sequence"), default=1)
    start_date = models.DateField(_("start date")); end_date = models.DateField(_("end date")); is_current = models.BooleanField(_("current"), default=False)
    class Meta:
        verbose_name = _("term"); verbose_name_plural = _("terms"); ordering = ["academic_year__start_date", "sequence"]
        constraints = [models.UniqueConstraint(fields=["academic_year", "name"], name="uq_term_name"), models.UniqueConstraint(fields=["academic_year", "sequence"], name="uq_term_sequence"), models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="ck_term_dates")]
        indexes = [models.Index(fields=["branch", "is_current"])]
    def __str__(self): return f"{self.academic_year.name} — {self.name}"


class SchoolClass(BranchOwnedModel):
    name = models.CharField(_("name"), max_length=150); code = models.CharField(_("code"), max_length=50); level = models.PositiveSmallIntegerField(_("level"), default=0); description = models.CharField(_("description"), max_length=255, blank=True); is_active = models.BooleanField(_("active"), default=True)
    class Meta:
        verbose_name = _("class"); verbose_name_plural = _("classes"); ordering = ["level", "name"]
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="uq_class_code"), models.UniqueConstraint(fields=["branch", "name"], name="uq_class_name")]
        indexes = [models.Index(fields=["branch", "is_active"])]
    def __str__(self): return self.name
    @property
    def section_count(self):
        sections = getattr(self, "_prefetched_objects_cache", {}).get("sections"); return len(sections) if sections is not None else self.sections.count()
    @property
    def subject_count(self):
        subjects = getattr(self, "_prefetched_objects_cache", {}).get("class_subjects"); return len(subjects) if subjects is not None else self.class_subjects.count()
    @property
    def teacher_count(self):
        subjects = getattr(self, "_prefetched_objects_cache", {}).get("class_subjects")
        if subjects is not None:
            return len({a.teacher_id for cs in subjects for a in getattr(cs, "_prefetched_objects_cache", {}).get("teacher_assignments", []) if a.is_active})
        return TeacherAssignment.objects.filter(class_subject__school_class=self, is_active=True).values("teacher_id").distinct().count()
    @property
    def student_count(self):
        enrollments = getattr(self, "_prefetched_objects_cache", {}).get("enrollments")
        if enrollments is not None: return sum(1 for e in enrollments if e.is_current)
        return self.enrollments.filter(is_current=True).values("student_id").distinct().count()


class Section(BranchOwnedModel):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="sections", verbose_name=_("class")); name = models.CharField(_("name"), max_length=100); capacity = models.PositiveIntegerField(_("capacity"), null=True, blank=True)
    class_teacher = models.ForeignKey("staff.Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="class_teacher_of", verbose_name=_("class teacher")); is_active = models.BooleanField(_("active"), default=True)
    class Meta:
        verbose_name = _("section"); verbose_name_plural = _("sections"); ordering = ["school_class__level", "name"]; constraints = [models.UniqueConstraint(fields=["school_class", "name"], name="uq_section_name")]; indexes = [models.Index(fields=["branch", "school_class"])]
    def __str__(self): return f"{self.school_class.name} — {self.name}"


class Subject(BranchOwnedModel):
    class Kind(models.TextChoices):
        ACADEMIC = "academic", _("Academic"); RELIGIOUS = "religious", _("Religious"); HIFZ = "hifz", _("Hifz"); ACTIVITY = "activity", _("Activity")
    name = models.CharField(_("name"), max_length=150); code = models.CharField(_("code"), max_length=50, blank=True); kind = models.CharField(_("kind"), max_length=20, choices=Kind.choices, default=Kind.ACADEMIC); is_elective = models.BooleanField(_("elective"), default=False); is_active = models.BooleanField(_("active"), default=True)
    class Meta:
        verbose_name = _("subject"); verbose_name_plural = _("subjects"); ordering = ["name"]; constraints = [models.UniqueConstraint(fields=["branch", "name"], name="uq_subject_name")]; indexes = [models.Index(fields=["branch", "is_active"])]
    def __str__(self): return self.name


class ClassSubject(BranchOwnedModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="class_subjects", verbose_name=_("academic year")); school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="class_subjects", verbose_name=_("class")); subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="class_subjects", verbose_name=_("subject")); weekly_periods = models.PositiveSmallIntegerField(_("weekly periods"), default=0); is_active = models.BooleanField(_("active"), default=True)
    class Meta:
        verbose_name = _("class subject"); verbose_name_plural = _("class subjects"); ordering = ["school_class__level", "subject__name"]; constraints = [models.UniqueConstraint(fields=["academic_year", "school_class", "subject"], name="uq_class_subject")]; indexes = [models.Index(fields=["branch", "academic_year", "school_class"])]
    def __str__(self): return f"{self.school_class.name} — {self.subject.name}"
    def clean(self):
        super().clean()
        if self.academic_year_id and self.school_class_id and self.subject_id:
            if ClassSubject.objects.filter(academic_year_id=self.academic_year_id, school_class_id=self.school_class_id, subject_id=self.subject_id).exclude(pk=self.pk).exists():
                raise ValidationError({"subject": _("This class already has this subject for the selected academic year. Choose a different subject or academic year.")})
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TeacherAssignment(BranchOwnedModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="teacher_assignments", verbose_name=_("academic year")); teacher = models.ForeignKey("staff.Staff", on_delete=models.CASCADE, related_name="teaching_assignments", verbose_name=_("teacher")); class_subject = models.ForeignKey(ClassSubject, on_delete=models.CASCADE, related_name="teacher_assignments", verbose_name=_("class subject")); section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True, related_name="teacher_assignments", verbose_name=_("section")); is_active = models.BooleanField(_("active"), default=True)
    class Meta:
        verbose_name = _("teacher assignment"); verbose_name_plural = _("teacher assignments"); ordering = ["teacher__full_name"]; constraints = [models.UniqueConstraint(fields=["class_subject", "section", "teacher"], name="uq_teacher_assignment")]; indexes = [models.Index(fields=["branch", "academic_year"]), models.Index(fields=["teacher", "is_active"])]
    @property
    def assignment_type(self): return _("Subject Teacher")
    @property
    def assignment_scope(self): return _("Section") if self.section_id else _("All sections")
    def __str__(self): return f"{self.teacher} — {self.class_subject}"
    def clean(self):
        super().clean()
        if self.class_subject_id and self.academic_year_id and self.class_subject.academic_year_id != self.academic_year_id:
            raise ValidationError({"class_subject": _("This Class Subject belongs to a different academic year. Select a Class Subject from the selected academic year.")})
        if self.section_id and self.class_subject_id and self.section.school_class_id != self.class_subject.school_class_id:
            raise ValidationError({"section": _("This section belongs to a different class. Select a section from the Class Subject's class.")})
        if self.teacher_id:
            teacher = self.teacher
            if teacher.staff_type != "teacher":
                raise ValidationError({"teacher": _("Select a staff member whose type is Teacher.")})
            if self._state.adding and teacher.status != "active":
                raise ValidationError({"teacher": _("Only an active teacher can receive a new assignment. Activate this teacher first, then try again.")})
        if self.class_subject_id and self.teacher_id and self.is_active:
            duplicate = TeacherAssignment.objects.filter(class_subject_id=self.class_subject_id, teacher_id=self.teacher_id, section_id=self.section_id, is_active=True).exclude(pk=self.pk).exists()
            if duplicate:
                raise ValidationError({"teacher": _("This teacher is already assigned to this subject for the selected scope. Edit the existing assignment instead of creating another one.")})
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Timetable(BranchOwnedModel):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, _("Monday"); TUESDAY = 1, _("Tuesday"); WEDNESDAY = 2, _("Wednesday"); THURSDAY = 3, _("Thursday"); FRIDAY = 4, _("Friday"); SATURDAY = 5, _("Saturday"); SUNDAY = 6, _("Sunday")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="timetable_slots", verbose_name=_("academic year")); section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="timetable_slots", verbose_name=_("section")); class_subject = models.ForeignKey(ClassSubject, on_delete=models.CASCADE, related_name="timetable_slots", verbose_name=_("class subject")); teacher = models.ForeignKey("staff.Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="timetable_slots", verbose_name=_("teacher")); weekday = models.IntegerField(_("weekday"), choices=Weekday.choices); period = models.PositiveSmallIntegerField(_("period"), default=1); start_time = models.TimeField(_("start time")); end_time = models.TimeField(_("end time")); room = models.CharField(_("room"), max_length=100, blank=True)
    class Meta:
        verbose_name = _("timetable slot"); verbose_name_plural = _("timetable"); ordering = ["weekday", "period"]; constraints = [models.UniqueConstraint(fields=["section", "weekday", "period", "academic_year"], name="uq_timetable_slot"), models.UniqueConstraint(fields=["academic_year", "teacher", "weekday", "period"], condition=models.Q(teacher__isnull=False), name="uq_timetable_teacher_slot"), models.UniqueConstraint(fields=["branch", "academic_year", "room", "weekday", "period"], condition=~models.Q(room=""), name="uq_timetable_room_slot"), models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="ck_timetable_times")]; indexes = [models.Index(fields=["branch", "academic_year", "weekday"]), models.Index(fields=["teacher", "weekday"])]
    def __str__(self): return f"{self.section} — {self.get_weekday_display()} P{self.period}"
    def clean(self):
        super().clean()
        errors = {}
        if self.weekday is not None and not is_working_day(self.weekday, self.branch): errors["weekday"] = _("This day is not configured as a working day for the branch. Choose one of the configured working days.")
        if self.academic_year_id and self.class_subject_id and self.class_subject.academic_year_id != self.academic_year_id: errors["class_subject"] = _("This Class Subject belongs to a different academic year. Select a Class Subject from the selected academic year.")
        if self.section_id and self.class_subject_id and self.section.school_class_id != self.class_subject.school_class_id: errors["section"] = _("This section belongs to a different class. Select a section from the Class Subject's class.")
        if self.teacher_id and self.class_subject_id and self.academic_year_id:
            assignment = TeacherAssignment.objects.filter(academic_year_id=self.academic_year_id, teacher_id=self.teacher_id, class_subject_id=self.class_subject_id, is_active=True).filter(models.Q(section_id=self.section_id) | models.Q(section__isnull=True)).first()
            if assignment is None: errors["teacher"] = _("This teacher is not assigned to the selected Class Subject and section. Assign the teacher first, or choose a teacher who is already assigned.")
        if self.academic_year_id and self.section_id and self.weekday is not None and self.period:
            clash = Timetable.objects.filter(academic_year_id=self.academic_year_id, section_id=self.section_id, weekday=self.weekday, period=self.period).exclude(pk=self.pk).first()
            if clash: errors["period"] = _("This section already has a lesson in this period. Move the new lesson to another period, or edit the existing lesson.")
        if self.academic_year_id and self.teacher_id and self.weekday is not None and self.period:
            clash = Timetable.objects.filter(academic_year_id=self.academic_year_id, teacher_id=self.teacher_id, weekday=self.weekday, period=self.period).exclude(pk=self.pk).select_related("section").first()
            if clash: errors["teacher"] = _("This teacher is already scheduled for %(section)s at this time. Choose another period/teacher, or edit the existing lesson.") % {"section": clash.section}
        if self.branch_id and self.academic_year_id and self.room and self.weekday is not None and self.period:
            clash = Timetable.objects.filter(branch_id=self.branch_id, academic_year_id=self.academic_year_id, room__iexact=self.room.strip(), weekday=self.weekday, period=self.period).exclude(pk=self.pk).select_related("section").first()
            if clash: errors["room"] = _("Room %(room)s is already booked by %(section)s at this time. Choose another room or period.") % {"room": self.room, "section": clash.section}
        if errors: raise ValidationError(errors)
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
