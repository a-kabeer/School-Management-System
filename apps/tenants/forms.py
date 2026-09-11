from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm

from .models import Branch, Organization


class BranchForm(TenantModelForm):
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
        ]
        widgets = {"opened_on": DateInput(), "address": forms.Textarea(attrs={"rows": 2})}

    def save(self, commit=True):
        instance = super(TenantModelForm, self).save(commit=False)
        if self.organization is not None:
            instance.organization = self.organization
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
