from decimal import Decimal

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.academics.models import AcademicYear, SchoolClass, Term
from apps.core.forms import DateInput, TenantModelForm
from apps.finance.models import PaymentMethod
from apps.students.models import Student

from .models import (
    FeeDiscount,
    FeeInvoice,
    FeeStructure,
    FeeType,
    StudentFee,
)


class FeeTypeForm(TenantModelForm):
    class Meta:
        model = FeeType
        fields = [
            "name",
            "code",
            "frequency",
            "description",
            "income_account",
            "is_refundable",
            "is_active",
        ]


class FeeStructureForm(TenantModelForm):
    class Meta:
        model = FeeStructure
        fields = [
            "academic_year",
            "school_class",
            "fee_type",
            "amount",
            "is_mandatory",
            "is_active",
        ]


class StudentFeeForm(TenantModelForm):
    class Meta:
        model = StudentFee
        fields = [
            "student",
            "academic_year",
            "fee_type",
            "amount",
            "effective_from",
            "effective_to",
            "notes",
            "is_active",
        ]
        widgets = {"effective_from": DateInput(), "effective_to": DateInput()}


class FeeDiscountForm(TenantModelForm):
    class Meta:
        model = FeeDiscount
        fields = [
            "name",
            "student",
            "fee_type",
            "discount_type",
            "value",
            "valid_from",
            "valid_to",
            "reason",
            "is_active",
        ]
        widgets = {"valid_from": DateInput(), "valid_to": DateInput()}

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get("discount_type") == FeeDiscount.DiscountType.PERCENTAGE
            and (cleaned.get("value") or Decimal("0")) > Decimal("100")
        ):
            self.add_error("value", _("A percentage cannot exceed 100."))
        return cleaned


class InvoiceGenerateForm(forms.Form):
    """Bill one student or a whole class for a period."""

    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.none(), label=_("Academic year")
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.none(), required=False, label=_("Term")
    )
    student = forms.ModelChoiceField(
        queryset=Student.objects.none(), required=False, label=_("Student")
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.objects.none(), required=False, label=_("Whole class")
    )
    period_month = forms.DateField(
        widget=DateInput(), required=False, label=_("Billing month")
    )
    issue_date = forms.DateField(widget=DateInput(), label=_("Issue date"))
    due_date = forms.DateField(widget=DateInput(), label=_("Due date"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        if branch is not None:
            years = AcademicYear.objects.filter(branch=branch)
            self.fields["academic_year"].queryset = years
            current = years.filter(is_current=True).first()
            if current:
                self.fields["academic_year"].initial = current.pk
                self.fields["term"].queryset = Term.objects.filter(
                    academic_year=current
                )
            self.fields["student"].queryset = Student.objects.filter(
                branch=branch, status=Student.Status.ACTIVE
            )
            self.fields["school_class"].queryset = SchoolClass.objects.filter(
                branch=branch, is_active=True
            )
        self.fields["issue_date"].initial = timezone.localdate()
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get("student")
        school_class = cleaned.get("school_class")
        if not student and not school_class:
            raise forms.ValidationError(_("Choose a student or a class."))
        if student and school_class:
            raise forms.ValidationError(_("Choose either a student or a class, not both."))

        issue, due = cleaned.get("issue_date"), cleaned.get("due_date")
        if issue and due and due < issue:
            self.add_error("due_date", _("The due date cannot be before the issue date."))

        month = cleaned.get("period_month")
        if month:
            cleaned["period_month"] = month.replace(day=1)
        return cleaned


class PaymentForm(forms.Form):
    """Collect a payment against one invoice."""

    invoice = forms.ModelChoiceField(
        queryset=FeeInvoice.objects.none(), label=_("Invoice")
    )
    amount = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), label=_("Amount")
    )
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.none(), label=_("Payment method")
    )
    payment_date = forms.DateField(widget=DateInput(), label=_("Payment date"))
    reference = forms.CharField(max_length=150, required=False, label=_("Reference"))
    notes = forms.CharField(max_length=255, required=False, label=_("Notes"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            # Only this branch's unsettled invoices are selectable, so an
            # invoice id from elsewhere fails validation rather than posting.
            self.fields["invoice"].queryset = (
                FeeInvoice.objects.filter(branch=branch)
                .exclude(status__in=[FeeInvoice.Status.PAID, FeeInvoice.Status.CANCELLED])
                .select_related("student")
                .order_by("-issue_date")
            )
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


class RefundForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), label=_("Amount")
    )
    refund_date = forms.DateField(widget=DateInput(), label=_("Refund date"))
    reason = forms.CharField(max_length=255, label=_("Reason"))
    payment_method = forms.ModelChoiceField(
        queryset=PaymentMethod.objects.none(), required=False, label=_("Paid out via")
    )

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch is not None:
            self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
                branch=branch, is_active=True
            )
        self.fields["refund_date"].initial = timezone.localdate()
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class",
                "form-select" if isinstance(widget, forms.Select) else "form-control",
            )


class WaiverForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), label=_("Amount")
    )
    waived_on = forms.DateField(widget=DateInput(), label=_("Date"))
    reason = forms.CharField(max_length=255, label=_("Reason"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["waived_on"].initial = timezone.localdate()
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class VoidPaymentForm(forms.Form):
    reason = forms.CharField(max_length=255, label=_("Reason"))

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].widget.attrs.setdefault("class", "form-control")
