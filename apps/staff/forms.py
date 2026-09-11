from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm
from apps.core.validators import validate_upload

from .models import (
    Staff,
    StaffAssignment,
    StaffDepartment,
    StaffDesignation,
    StaffDocument,
    StaffProfile,
)


class StaffDepartmentForm(TenantModelForm):
    class Meta:
        model = StaffDepartment
        fields = ["name", "description", "is_active"]


class StaffDesignationForm(TenantModelForm):
    class Meta:
        model = StaffDesignation
        fields = ["name", "department", "is_teaching", "is_active"]


class StaffForm(TenantModelForm):
    class Meta:
        model = Staff
        fields = [
            "employee_no",
            "full_name",
            "father_name",
            "staff_type",
            "department",
            "designation",
            "gender",
            "date_of_birth",
            "national_id",
            "phone",
            "email",
            "address",
            "qualification",
            "photo",
            "joining_date",
            "leaving_date",
            "basic_salary",
            "status",
        ]
        widgets = {
            "date_of_birth": DateInput(),
            "joining_date": DateInput(),
            "leaving_date": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_photo(self):
        return validate_upload(self.cleaned_data.get("photo"))

    def clean_employee_no(self):
        value = (self.cleaned_data.get("employee_no") or "").strip()
        if value and self.branch is not None:
            clash = Staff.all_objects.filter(
                branch=self.branch, employee_no=value
            ).exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError(
                    _("That employee number is already in use in this branch.")
                )
        return value

    def clean(self):
        cleaned = super().clean()
        joining, leaving = cleaned.get("joining_date"), cleaned.get("leaving_date")
        if joining and leaving and leaving < joining:
            self.add_error("leaving_date", _("Leaving date cannot be before joining."))
        return cleaned


class StaffProfileForm(TenantModelForm):
    class Meta:
        model = StaffProfile
        fields = [
            "staff",
            "blood_group",
            "marital_status",
            "emergency_contact_name",
            "emergency_contact_phone",
            "bank_name",
            "bank_account_number",
            "experience_years",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class StaffDocumentForm(TenantModelForm):
    class Meta:
        model = StaffDocument
        fields = [
            "staff",
            "document_type",
            "title",
            "file",
            "issued_on",
            "expires_on",
            "notes",
        ]
        widgets = {"issued_on": DateInput(), "expires_on": DateInput()}

    def clean_file(self):
        return validate_upload(self.cleaned_data.get("file"))


class StaffAssignmentForm(TenantModelForm):
    class Meta:
        model = StaffAssignment
        fields = [
            "staff",
            "title",
            "department",
            "start_date",
            "end_date",
            "is_active",
            "notes",
        ]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}


class StaffStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Staff.Status.choices, label=_("New status"))
    effective_date = forms.DateField(widget=DateInput(), label=_("Effective date"))
    reason = forms.CharField(required=False, max_length=255, label=_("Reason"))

    def __init__(self, *args, **kwargs):
        for key in ("user", "branch", "organization"):
            kwargs.pop(key, None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )
