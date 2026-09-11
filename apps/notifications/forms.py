from django import forms
from django.utils.translation import gettext_lazy as _

from apps.academics.models import SchoolClass
from apps.core.forms import TenantModelForm

from .models import Channel, NotificationPreference, NotificationTemplate


class NotificationTemplateForm(forms.ModelForm):
    class Meta:
        model = NotificationTemplate
        fields = ["event", "channel", "language", "title", "body", "is_active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(user, "organization", None)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organization = self.organization
        if commit:
            instance.save()
        return instance


class NotificationPreferenceForm(TenantModelForm):
    class Meta:
        model = NotificationPreference
        fields = ["user", "event", "channel", "is_enabled"]


class AnnouncementForm(forms.Form):
    """Send a message to a chosen audience."""

    audience = forms.ChoiceField(
        choices=[
            ("all_staff", _("All staff")),
            ("all_parents", _("All parents")),
            ("class_parents", _("Parents of one class")),
        ],
        label=_("Send to"),
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.objects.none(), required=False, label=_("Class")
    )
    channels = forms.MultipleChoiceField(
        choices=Channel.choices,
        initial=[Channel.IN_APP],
        widget=forms.CheckboxSelectMultiple,
        label=_("Channels"),
    )
    title = forms.CharField(max_length=255, label=_("Title"))
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), label=_("Message"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["school_class"].queryset = SchoolClass.objects.filter(
                branch=branch, is_active=True
            )
        for name, field in self.fields.items():
            if name == "channels":
                continue
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience") == "class_parents" and not cleaned.get("school_class"):
            self.add_error("school_class", _("Choose a class."))
        return cleaned
