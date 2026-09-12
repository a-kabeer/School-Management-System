from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, RelatedCombo, TenantModelForm, TimeInput

from .models import (
    AcademicYear,
    ClassSubject,
    SchoolClass,
    Section,
    Subject,
    TeacherAssignment,
    Term,
    Timetable,
)
from .timetable_config import working_weekdays


class AcademicYearForm(TenantModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current", "is_closed"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end <= start:
            self.add_error("end_date", _("End date must be after the start date."))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit and instance.is_current:
            AcademicYear.objects.filter(branch=instance.branch, is_current=True).exclude(pk=instance.pk).update(is_current=False)
        return instance


class TermForm(TenantModelForm):
    class Meta:
        model = Term
        fields = ["academic_year", "name", "sequence", "start_date", "end_date", "is_current"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_quick_add("academic_year", "academics:year_create", _("Add academic year"), "academics.add_academicyear")

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("academic_year")
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("End date cannot be before the start date."))
        if year and start and start < year.start_date:
            self.add_error("start_date", _("This term starts before %(year)s does.") % {"year": year.name})
        if year and end and end > year.end_date:
            self.add_error("end_date", _("This term ends after %(year)s does.") % {"year": year.name})
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit and instance.is_current:
            Term.objects.filter(academic_year=instance.academic_year, is_current=True).exclude(pk=instance.pk).update(is_current=False)
        return instance


class SchoolClassForm(TenantModelForm):
    class Meta:
        model = SchoolClass
        fields = ["name", "code", "level", "description", "is_active"]


class SectionForm(TenantModelForm):
    class Meta:
        model = Section
        fields = ["school_class", "name", "capacity", "class_teacher", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        teachers = self.fields["class_teacher"].queryset
        self.fields["class_teacher"].queryset = teachers.filter(staff_type="teacher", status="active")
        self.allow_quick_add("school_class", "academics:class_create", _("Add class"), "academics.add_schoolclass")


class SubjectForm(TenantModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code", "kind", "is_elective", "is_active"]


class ClassSubjectForm(TenantModelForm):
    class Meta:
        model = ClassSubject
        fields = ["academic_year", "school_class", "subject", "weekly_periods", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_quick_add("subject", "academics:subject_create", _("Add subject"), "academics.add_subject")

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("academic_year")
        school_class = cleaned.get("school_class")
        subject = cleaned.get("subject")
        if year and school_class and subject:
            duplicate = ClassSubject.objects.filter(
                academic_year=year, school_class=school_class, subject=subject
            ).exclude(pk=self.instance.pk).exists()
            if duplicate:
                self.add_error("subject", _("That subject is already assigned to this class for this academic year."))
        return cleaned


class TeacherAssignmentForm(TenantModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ["academic_year", "teacher", "class_subject", "section", "is_active"]
        widgets = {
            "class_subject": RelatedCombo(parent_field="academic_year_id", key_field="school_class_id", parent_selector="#id_academic_year"),
            "section": RelatedCombo(parent_field="school_class_id", parent_selector="#id_class_subject"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.filter(staff_type="teacher", status="active")
        self.fields["class_subject"].queryset = self.fields["class_subject"].queryset.select_related("school_class", "subject")
        self.fields["section"].queryset = self.fields["section"].queryset.select_related("school_class")
        self.allow_quick_add("class_subject", "academics:classsubject_create", _("Add class subject"), "academics.add_classsubject")

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        class_subject = cleaned.get("class_subject")
        year = cleaned.get("academic_year")
        if section and class_subject and section.school_class_id != class_subject.school_class_id:
            self.add_error("section", _("That section belongs to a different class."))
        if year and class_subject and class_subject.academic_year_id != year.pk:
            self.add_error("class_subject", _("That subject is taught in a different academic year."))
        return cleaned


class TimetableForm(TenantModelForm):
    class Meta:
        model = Timetable
        fields = ["academic_year", "section", "class_subject", "teacher", "weekday", "period", "start_time", "end_time", "room"]
        widgets = {
            "start_time": TimeInput(),
            "end_time": TimeInput(),
            "class_subject": RelatedCombo(parent_field="academic_year_id", key_field="school_class_id", parent_selector="#id_academic_year"),
            "section": RelatedCombo(parent_field="school_class_id", parent_selector="#id_class_subject"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weekday"].choices = [
            (day, Timetable.Weekday(day).label) for day in working_weekdays(self.branch)
        ]
        self.fields["class_subject"].queryset = self.fields["class_subject"].queryset.select_related("school_class", "subject")
        self.fields["section"].queryset = self.fields["section"].queryset.select_related("school_class")
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.filter(staff_type="teacher", status="active")

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", _("End time must be after the start time."))

        year = cleaned.get("academic_year")
        section = cleaned.get("section")
        class_subject = cleaned.get("class_subject")
        weekday = cleaned.get("weekday")
        period = cleaned.get("period")
        teacher = cleaned.get("teacher")

        if weekday is not None and weekday not in working_weekdays(self.branch):
            self.add_error("weekday", _("This day is not configured as a working day for the branch."))
        if section and class_subject and section.school_class_id != class_subject.school_class_id:
            self.add_error("section", _("That section belongs to a different class."))
        if year and class_subject and class_subject.academic_year_id != year.pk:
            self.add_error("class_subject", _("That subject is taught in a different academic year."))

        if year and section and weekday is not None and period:
            taken = Timetable.objects.filter(
                academic_year=year, section=section, weekday=weekday, period=period
            ).exclude(pk=self.instance.pk).select_related("class_subject__subject").first()
            if taken is not None:
                self.add_error("period", _("%(section)s already has %(subject)s in that period.") % {"section": section, "subject": taken.class_subject.subject.name})

        if teacher and weekday is not None and period and year:
            clash = Timetable.objects.filter(
                academic_year=year, teacher=teacher, weekday=weekday, period=period
            ).exclude(pk=self.instance.pk).select_related("section__school_class").first()
            if clash is not None:
                self.add_error("teacher", _("%(teacher)s already teaches %(section)s in that period.") % {"teacher": teacher.full_name, "section": clash.section})
        return cleaned
