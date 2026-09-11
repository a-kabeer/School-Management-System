from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm

from .models import (
    DailyProgress,
    HifzAssessment,
    HifzStudentProfile,
    HifzTeacherAssignment,
    Revision,
)


class HifzStudentProfileForm(TenantModelForm):
    class Meta:
        model = HifzStudentProfile
        fields = [
            "student",
            "stage",
            "started_on",
            "completed_on",
            "current_para",
            "current_surah",
            "paras_memorized",
            "daily_target_lines",
            "is_active",
            "notes",
        ]
        widgets = {
            "started_on": DateInput(),
            "completed_on": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class HifzTeacherAssignmentForm(TenantModelForm):
    class Meta:
        model = HifzTeacherAssignment
        fields = [
            "hifz_profile",
            "teacher",
            "start_date",
            "end_date",
            "is_active",
            "notes",
        ]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = self.fields["teacher"].queryset.filter(
            status="active"
        )


class DailyProgressForm(TenantModelForm):
    class Meta:
        model = DailyProgress
        fields = [
            "hifz_profile",
            "teacher",
            "date",
            "lesson_type",
            "from_para",
            "to_para",
            "surah",
            "from_ayah",
            "to_ayah",
            "lines",
            "pages",
            "mistakes",
            "hesitations",
            "quality",
            "is_repeated",
            "remarks",
        ]
        widgets = {"date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        from_para, to_para = cleaned.get("from_para"), cleaned.get("to_para")
        if from_para and to_para and to_para < from_para:
            self.add_error("to_para", _("The end para cannot be before the start."))
        from_ayah, to_ayah = cleaned.get("from_ayah"), cleaned.get("to_ayah")
        if from_ayah and to_ayah and to_ayah < from_ayah:
            self.add_error("to_ayah", _("The end ayah cannot be before the start."))
        return cleaned


class RevisionForm(TenantModelForm):
    class Meta:
        model = Revision
        fields = [
            "hifz_profile",
            "teacher",
            "from_para",
            "to_para",
            "scheduled_date",
            "completed_date",
            "status",
            "mistakes",
            "quality",
            "remarks",
        ]
        widgets = {"scheduled_date": DateInput(), "completed_date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        from_para, to_para = cleaned.get("from_para"), cleaned.get("to_para")
        if from_para and to_para and to_para < from_para:
            self.add_error("to_para", _("The end para cannot be before the start."))
        return cleaned


class HifzAssessmentForm(TenantModelForm):
    class Meta:
        model = HifzAssessment
        fields = [
            "hifz_profile",
            "examiner",
            "title",
            "date",
            "from_para",
            "to_para",
            "total_marks",
            "obtained_marks",
            "mistakes",
            "result",
            "remarks",
        ]
        widgets = {"date": DateInput(), "remarks": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        cleaned = super().clean()
        total, obtained = cleaned.get("total_marks"), cleaned.get("obtained_marks")
        if total is not None and obtained is not None and obtained > total:
            self.add_error("obtained_marks", _("Marks cannot exceed the total."))
        from_para, to_para = cleaned.get("from_para"), cleaned.get("to_para")
        if from_para and to_para and to_para < from_para:
            self.add_error("to_para", _("The end para cannot be before the start."))
        return cleaned
