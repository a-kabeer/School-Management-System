from decimal import Decimal

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput, TenantModelForm
from apps.finance.models import PaymentMethod

from .models import (
    EmployeeSalary,
    PayrollPeriod,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
)


class SalaryComponentForm(TenantModelForm):
    class Meta:
        model = SalaryComponent
        fields = [
            "name",
            "code",
            "component_type",
            "calculation_type",
            "default_value",
            "is_taxable",
            "expense_account",
            "is_active",
        ]


class SalaryStructureForm(TenantModelForm):
    class Meta:
        model = SalaryStructure
        fields = ["name", "description", "basic_salary", "is_active"]


class SalaryStructureLineForm(TenantModelForm):
    class Meta:
        model = SalaryStructureLine
        fields = ["structure", "component", "value", "sequence"]


class EmployeeSalaryForm(TenantModelForm):
    class Meta:
        model = EmployeeSalary
        fields = [
            "staff",
            "structure",
            "basic_salary",
            "effective_from",
            "effective_to",
            "bank_account_number",
            "is_active",
        ]
        widgets = {"effective_from": DateInput(), "effective_to": DateInput()}

    def clean(self):
        cleaned = super().clean()
        staff = cleaned.get("staff")
        if cleaned.get("is_active") and staff is not None:
            clash = EmployeeSalary.objects.filter(staff=staff, is_active=True).exclude(
                pk=self.instance.pk
            )
            if clash.exists():
                self.add_error(
                    "is_active",
                    _("This staff member already has an active salary. Close it first."),
                )
        return cleaned


class PayrollPeriodForm(TenantModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ["name", "month", "start_date", "end_date", "payment_date", "status"]
        widgets = {
            "month": DateInput(),
            "start_date": DateInput(),
            "end_date": DateInput(),
            "payment_date": DateInput(),
        }

    def clean_month(self):
        month = self.cleaned_data.get("month")
        return month.replace(day=1) if month else month


class ProcessPayrollForm(forms.Form):
    period = forms.ModelChoiceField(
        queryset=PayrollPeriod.objects.none(), label=_("Payroll period")
    )
    run_date = forms.DateField(widget=DateInput(), label=_("Run date"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["period"].queryset = PayrollPeriod.objects.filter(
                branch=branch
            ).exclude(status=PayrollPeriod.Status.CLOSED)
        self.fields["run_date"].initial = timezone.localdate()
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )


class SalaryPaymentForm(forms.Form):
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.none(), label=_("Payment method")
    )
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        label=_("Amount"),
        help_text=_("Leave blank to pay the full outstanding net salary."),
    )
    payment_date = forms.DateField(widget=DateInput(), label=_("Payment date"))
    reference = forms.CharField(max_length=150, required=False, label=_("Reference"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
                branch=branch, is_active=True
            )
        self.fields["payment_date"].initial = timezone.localdate()
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )
