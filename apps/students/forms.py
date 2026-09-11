from django import forms
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.core.forms import DateInput, TenantModelForm
from apps.core.validators import validate_upload

from .models import (
    Guardian,
    Student,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentProfile,
)


class StudentForm(TenantModelForm):
    """Admission form: student details plus the first class placement."""

    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.none(), label=_("Academic year")
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.objects.none(), label=_("Class")
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.none(), required=False, label=_("Section")
    )
    roll_number = forms.CharField(required=False, label=_("Roll number"))

    class Meta:
        model = Student
        fields = [
            "admission_no",
            "full_name",
            "father_name",
            "gender",
            "date_of_birth",
            "place_of_birth",
            "nationality",
            "national_id",
            "photo",
            "phone",
            "email",
            "address",
            "city",
            "previous_institution",
            "admission_date",
            "is_boarder",
            "status",
        ]
        widgets = {
            "date_of_birth": DateInput(),
            "admission_date": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["admission_no"].required = False
        self.fields["admission_no"].help_text = _(
            "Leave blank to generate the next number automatically."
        )

        if self.instance.pk:
            # Placement is changed through the enrollment screen, not here.
            for name in ("academic_year", "school_class", "section", "roll_number"):
                self.fields.pop(name, None)
            return

        if self.branch is not None:
            years = AcademicYear.objects.filter(branch=self.branch)
            self.fields["academic_year"].queryset = years
            current = years.filter(is_current=True).first()
            if current:
                self.fields["academic_year"].initial = current.pk
            self.fields["school_class"].queryset = SchoolClass.objects.filter(
                branch=self.branch, is_active=True
            )
            self.fields["section"].queryset = Section.objects.filter(
                branch=self.branch, is_active=True
            ).select_related("school_class")

    def clean_photo(self):
        return validate_upload(self.cleaned_data.get("photo"))

    def clean_admission_no(self):
        value = (self.cleaned_data.get("admission_no") or "").strip()
        if value and self.branch is not None:
            clash = Student.all_objects.filter(
                branch=self.branch, admission_no=value
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    _("That admission number is already in use in this branch.")
                )
        return value

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        school_class = cleaned.get("school_class")
        if section and school_class and section.school_class_id != school_class.pk:
            self.add_error("section", _("That section belongs to a different class."))
        return cleaned


class StudentProfileForm(TenantModelForm):
    class Meta:
        model = StudentProfile
        fields = [
            "blood_group",
            "medical_conditions",
            "allergies",
            "emergency_contact_name",
            "emergency_contact_phone",
            "transport_required",
            "hostel_room",
            "remarks",
        ]
        widgets = {
            "medical_conditions": forms.Textarea(attrs={"rows": 2}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }


class GuardianForm(TenantModelForm):
    class Meta:
        model = Guardian
        fields = [
            "full_name",
            "relation",
            "national_id",
            "phone",
            "alternate_phone",
            "email",
            "occupation",
            "address",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


class StudentGuardianForm(TenantModelForm):
    class Meta:
        model = StudentGuardian
        fields = [
            "student",
            "guardian",
            "relation",
            "is_primary",
            "can_view_portal",
            "can_collect_student",
        ]


class StudentDocumentForm(TenantModelForm):
    class Meta:
        model = StudentDocument
        fields = ["student", "document_type", "title", "file", "issued_on", "notes"]
        widgets = {"issued_on": DateInput()}

    def clean_file(self):
        return validate_upload(self.cleaned_data.get("file"))


class EnrollmentForm(TenantModelForm):
    class Meta:
        model = StudentEnrollment
        fields = [
            "student",
            "academic_year",
            "school_class",
            "section",
            "roll_number",
            "start_date",
            "end_date",
            "is_current",
        ]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        school_class = cleaned.get("school_class")
        if section and school_class and section.school_class_id != school_class.pk:
            self.add_error("section", _("That section belongs to a different class."))
        return cleaned


class StudentStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Student.Status.choices, label=_("New status"))
    effective_date = forms.DateField(widget=DateInput(), label=_("Effective date"))
    reason = forms.CharField(required=False, max_length=255, label=_("Reason"))

    def __init__(self, *args, **kwargs):
        kwargs.pop("user", None)
        kwargs.pop("branch", None)
        kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )


class StudentTransferForm(forms.Form):
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.objects.none(), label=_("New class")
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.none(), required=False, label=_("New section")
    )
    moved_on = forms.DateField(widget=DateInput(), label=_("Effective date"))
    reason = forms.CharField(required=False, max_length=255, label=_("Reason"))

    def __init__(self, *args, branch=None, **kwargs):
        kwargs.pop("user", None)
        kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(
                branch=branch, is_active=True
            )
            self.fields["section"].queryset = Section.objects.filter(
                branch=branch, is_active=True
            ).select_related("school_class")
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def clean(self):
        cleaned = super().clean()
        section = cleaned.get("section")
        school_class = cleaned.get("school_class")
        if section and school_class and section.school_class_id != school_class.pk:
            self.add_error("section", _("That section belongs to a different class."))
        return cleaned
