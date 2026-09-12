from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm

from .models import Branch, Organization


WEEKDAY_CHOICES = (
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday")),
)


class BranchForm(TenantModelForm):
    working_weekdays = forms.MultipleChoiceField(
        label=_("Working days"),
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Select the days this branch operates. The timetable will only offer these days."),
        required=True,
    )

    class Meta:
        model = Branch
        fields = [
            "name",
            "code",
            "phone",
            "email",
            "address",
            "city",
            "opened_on",
            "is_active",
            "is_central_administration",
            "working_weekdays",
        ]
        widgets = {"opened_on": DateInput(), "address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            configured = self.instance.working_weekdays or [0, 1, 2, 3, 4]
            self.initial["working_weekdays"] = [str(day) for day in configured]

    def clean_working_weekdays(self):
        return sorted({int(day) for day in self.cleaned_data["working_weekdays"]})

    def save(self, commit=True):
        instance = super(TenantModelForm, self).save(commit=False)
        if self.organization is not None:
            instance.organization = self.organization
        instance.working_weekdays = self.cleaned_data["working_weekdays"]
        if commit:
            instance.save()
        return instance


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "name",
            "legal_name",
            "logo",
            "email",
            "phone",
            "address",
            "city",
            "country",
            "timezone",
            "currency",
            "default_language",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_logo(self):
        from apps.core.validators import validate_upload

        return validate_upload(self.cleaned_data.get("logo"))


class BranchSwitchForm(forms.Form):
    branch = forms.UUIDField(label=_("Branch"))
