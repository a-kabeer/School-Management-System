from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm, TimeInput

from .models import Exam, ExamSchedule, ExamSubject, ExamTerm, Grade


class GradeForm(TenantModelForm):
    class Meta:
        model = Grade
        fields = [
            "academic_year",
            "name",
            "min_percentage",
            "max_percentage",
            "grade_point",
            "remark",
            "is_pass",
        ]

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("min_percentage"), cleaned.get("max_percentage")
        if low is not None and high is not None and high < low:
            self.add_error("max_percentage", _("The maximum cannot be below the minimum."))
        return cleaned


class ExamTermForm(TenantModelForm):
    class Meta:
        model = ExamTerm
        fields = ["academic_year", "term", "name", "sequence", "weight_percentage"]


class ExamForm(TenantModelForm):
    class Meta:
        model = Exam
        fields = [
            "exam_term",
            "academic_year",
            "school_class",
            "name",
            "start_date",
            "end_date",
            "status",
            "instructions",
        ]
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("End date cannot be before start date."))
        return cleaned


class ExamSubjectForm(TenantModelForm):
    class Meta:
        model = ExamSubject
        fields = [
            "exam",
            "class_subject",
            "total_marks",
            "passing_marks",
            "weight_percentage",
        ]

    def clean(self):
        cleaned = super().clean()
        total, passing = cleaned.get("total_marks"), cleaned.get("passing_marks")
        if total is not None and passing is not None and passing > total:
            self.add_error("passing_marks", _("Passing marks cannot exceed the total."))
        return cleaned


class ExamScheduleForm(TenantModelForm):
    class Meta:
        model = ExamSchedule
        fields = [
            "exam_subject",
            "section",
            "date",
            "start_time",
            "end_time",
            "room",
            "invigilator",
        ]
        widgets = {
            "date": DateInput(),
            "start_time": TimeInput(),
            "end_time": TimeInput(),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", _("End time must be after the start time."))
        return cleaned
