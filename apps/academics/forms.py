from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm, TimeInput

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
            AcademicYear.objects.filter(branch=instance.branch, is_current=True).exclude(
                pk=instance.pk
            ).update(is_current=False)
        return instance


class TermForm(TenantModelForm):
    class Meta:
        model = Term
        fields = [
            "academic_year",
            "name",
            "sequence",
            "start_date",
            "end_date",
            "is_current",
        ]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit and instance.is_current:
            Term.objects.filter(
                academic_year=instance.academic_year, is_current=True
            ).exclude(pk=instance.pk).update(is_current=False)
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
        self.fields["class_teacher"].queryset = teachers.filter(
            staff_type="teacher", status="active"
        )


class SubjectForm(TenantModelForm):
    class Meta:
        model = Subject
        fields = ["name", "code", "kind", "is_elective", "is_active"]


class ClassSubjectForm(TenantModelForm):
    class Meta:
        model = ClassSubject
        fields = [
            "academic_year",
            "school_class",
            "subject",
            "weekly_periods",
            "is_active",
        ]


class TeacherAssignmentForm(TenantModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ["academic_year", "teacher", "class_subject", "section", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.filter(
            staff_type="teacher", status="active"
        )
        self.fields["class_subject"].queryset = self.fields[
            "class_subject"
        ].queryset.select_related("school_class", "subject")

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        class_subject = cleaned.get("class_subject")
        if section and class_subject and section.school_class_id != class_subject.school_class_id:
            self.add_error("section", _("That section belongs to a different class."))
        return cleaned


class TimetableForm(TenantModelForm):
    class Meta:
        model = Timetable
        fields = [
            "academic_year",
            "section",
            "class_subject",
            "teacher",
            "weekday",
            "period",
            "start_time",
            "end_time",
            "room",
        ]
        widgets = {"start_time": TimeInput(), "end_time": TimeInput()}

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", _("End time must be after the start time."))

        teacher = cleaned.get("teacher")
        weekday = cleaned.get("weekday")
        period = cleaned.get("period")
        year = cleaned.get("academic_year")
        if teacher and weekday is not None and period and year:
            clash = Timetable.objects.filter(
                academic_year=year, teacher=teacher, weekday=weekday, period=period
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error(
                    "teacher", _("This teacher already has a class in that period.")
                )
        return cleaned
