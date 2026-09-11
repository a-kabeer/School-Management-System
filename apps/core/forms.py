"""Form base classes that keep tenancy out of individual apps."""

from django import forms
from django.db.models import ForeignKey, ManyToManyField
from django.utils.translation import gettext_lazy as _

from .models import BranchOwnedModel, OrganizationOwnedModel


class TenantModelForm(forms.ModelForm):
    """ModelForm that scopes every relation to the caller's branch.

    Choice narrowing here is a security control, not a convenience: a POST
    carrying another branch's primary key fails validation because that id was
    never in the field's queryset.
    """

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.branch = branch
        self.organization = organization or getattr(branch, "organization", None)
        if self.organization is None and user is not None:
            self.organization = getattr(user, "organization", None)

        self._scope_related_fields()
        self._style_widgets()

    def _scope_related_fields(self):
        from apps.accounts.rbac import accessible_branch_ids

        for name, field in self.fields.items():
            queryset = getattr(field, "queryset", None)
            if queryset is None:
                continue

            model = queryset.model
            try:
                model_field = self._meta.model._meta.get_field(name)
            except Exception:
                model_field = None
            if model_field is not None and not isinstance(
                model_field, (ForeignKey, ManyToManyField)
            ):
                continue

            if issubclass(model, BranchOwnedModel):
                if self.branch is not None:
                    field.queryset = queryset.filter(branch=self.branch)
                elif self.user is not None:
                    field.queryset = queryset.filter(
                        branch_id__in=accessible_branch_ids(self.user)
                    )
                else:
                    field.queryset = queryset.none()
            elif issubclass(model, OrganizationOwnedModel):
                if self.organization is not None:
                    field.queryset = queryset.filter(organization=self.organization)
                else:
                    field.queryset = queryset.none()

    def _style_widgets(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                continue
            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, (forms.DateInput, forms.DateTimeInput)):
                widget.attrs.setdefault("class", "form-control")
                widget.input_type = "date"
            else:
                widget.attrs.setdefault("class", "form-control")
            if field.required:
                widget.attrs.setdefault("required", "required")

    def save(self, commit=True):
        instance = super().save(commit=False)
        if isinstance(instance, BranchOwnedModel):
            # Branch is never taken from the payload; it comes from the
            # session-authorized branch the view resolved.
            if self.branch is not None:
                instance.branch = self.branch
            if instance.branch_id:
                instance.organization_id = instance.branch.organization_id
        elif isinstance(instance, OrganizationOwnedModel):
            if self.organization is not None:
                instance.organization = self.organization
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DateInput(forms.DateInput):
    input_type = "date"


class TimeInput(forms.TimeInput):
    input_type = "time"


class SearchForm(forms.Form):
    q = forms.CharField(
        label=_("Search"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
