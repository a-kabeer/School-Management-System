from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm

from .models import Account, AccountType, FiscalPeriod, Journal, JournalEntry, PaymentMethod


class AccountTypeForm(forms.ModelForm):
    class Meta:
        model = AccountType
        fields = ["code", "name", "nature", "normal_balance"]

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization or getattr(user, "organization", None)
        for field in self.fields.values():
            widget = field.widget
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


class AccountForm(TenantModelForm):
    class Meta:
        model = Account
        fields = [
            "code",
            "name",
            "account_type",
            "parent",
            "description",
            "opening_balance",
            "is_bank_account",
            "is_active",
        ]


class FiscalPeriodForm(TenantModelForm):
    class Meta:
        model = FiscalPeriod
        fields = ["name", "start_date", "end_date"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("End date cannot be before start date."))
        if start and end and self.branch is not None:
            overlapping = FiscalPeriod.objects.filter(
                branch=self.branch, start_date__lte=end, end_date__gte=start
            ).exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise forms.ValidationError(
                    _("This period overlaps an existing fiscal period.")
                )
        return cleaned


class JournalForm(TenantModelForm):
    class Meta:
        model = Journal
        fields = ["code", "name", "journal_type", "is_active"]


class PaymentMethodForm(TenantModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["name", "method_type", "account", "requires_reference", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = self.fields["account"].queryset.filter(
            is_active=True
        )


class JournalEntryForm(forms.Form):
    """Header of a manual journal entry; lines come from the formset."""

    date = forms.DateField(widget=DateInput(), label=_("Date"))
    journal_type = forms.ChoiceField(
        choices=Journal.JournalType.choices,
        initial=Journal.JournalType.GENERAL,
        label=_("Journal"),
    )
    reference = forms.CharField(max_length=150, required=False, label=_("Reference"))
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), required=False, label=_("Description")
    )

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )


class JournalEntryLineForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(), required=False, label=_("Account")
    )
    debit = forms.DecimalField(
        max_digits=14, decimal_places=2, required=False, initial=Decimal("0.00")
    )
    credit = forms.DecimalField(
        max_digits=14, decimal_places=2, required=False, initial=Decimal("0.00")
    )
    description = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["account"].queryset = Account.objects.filter(
                branch=branch, is_active=True
            ).order_by("code")
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("debit") or Decimal("0.00")
        credit = cleaned.get("credit") or Decimal("0.00")
        account = cleaned.get("account")
        if account and debit and credit:
            raise forms.ValidationError(
                _("A line cannot be both a debit and a credit.")
            )
        if account and not debit and not credit:
            raise forms.ValidationError(_("Enter a debit or a credit amount."))
        if (debit or credit) and not account:
            raise forms.ValidationError(_("Select an account for this line."))
        if debit < 0 or credit < 0:
            raise forms.ValidationError(_("Amounts cannot be negative."))
        return cleaned


JournalEntryLineFormSet = forms.formset_factory(
    JournalEntryLineForm, extra=4, min_num=2, validate_min=True
)
