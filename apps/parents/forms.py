from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm

from .models import ParentPortalProfile, ParentRequest


class ParentRequestForm(forms.ModelForm):
    """A parent raising a request. The child list is restricted to their own."""

    class Meta:
        model = ParentRequest
        fields = [
            "student",
            "request_type",
            "subject",
            "message",
            "start_date",
            "end_date",
        ]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
            "start_date": DateInput(),
            "end_date": DateInput(),
        }

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        from .selectors import accessible_students

        # Narrowing the queryset is the control: a posted student id outside
        # this list fails validation rather than reaching the database write.
        self.fields["student"].queryset = accessible_students(user)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("The end date cannot be before the start."))
        return cleaned


class ParentRequestResponseForm(forms.ModelForm):
    class Meta:
        model = ParentRequest
        fields = ["status", "response"]
        widgets = {"response": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )


class PortalProfileForm(TenantModelForm):
    class Meta:
        model = ParentPortalProfile
        fields = [
            "default_student",
            "receives_attendance_alerts",
            "receives_fee_reminders",
            "receives_result_alerts",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .selectors import accessible_students

        self.fields["default_student"].queryset = accessible_students(self.user)
