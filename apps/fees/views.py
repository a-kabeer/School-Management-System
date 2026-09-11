from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantDetailView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin

from .forms import (
    FeeDiscountForm,
    FeeStructureForm,
    FeeTypeForm,
    InvoiceGenerateForm,
    PaymentForm,
    RefundForm,
    StudentFeeForm,
    VoidPaymentForm,
    WaiverForm,
)
from .models import (
    FeeDiscount,
    FeeInvoice,
    FeePayment,
    FeeRefund,
    FeeStructure,
    FeeType,
    StudentFee,
)
from .services import (
    generate_invoice,
    generate_invoices_for_class,
    outstanding_summary,
    record_payment,
    refund_payment,
    void_payment,
    waive_invoice_amount,
)

FEES = "core.access_fees"


class FeeTypeListView(TenantListView):
    model = FeeType
    required_permission = FEES
    create_permission = "fees.add_feetype"
    page_title = _("Fee Types")
    ordering = ["name"]
    create_url_name = "fees:type_create"
    update_url_name = "fees:type_update"
    filter_spec = FilterSpec(search_fields=("name", "code"))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Code"), "field": "code"},
        {"label": _("Frequency"), "field": "frequency", "type": "choice"},
        {"label": _("Refundable"), "field": "is_refundable", "type": "bool"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class FeeTypeCreateView(TenantCreateView):
    model = FeeType
    form_class = FeeTypeForm
    required_permission = "fees.add_feetype"
    success_url = reverse_lazy("fees:type_list")
    page_title = _("New Fee Type")


class FeeTypeUpdateView(TenantUpdateView):
    model = FeeType
    form_class = FeeTypeForm
    required_permission = "fees.change_feetype"
    success_url = reverse_lazy("fees:type_list")
    page_title = _("Edit Fee Type")


class FeeStructureListView(TenantListView):
    model = FeeStructure
    required_permission = FEES
    create_permission = "fees.add_feestructure"
    page_title = _("Fee Structures")
    select_related = ("academic_year", "school_class", "fee_type")
    ordering = ["school_class__level", "fee_type__name"]
    create_url_name = "fees:structure_create"
    update_url_name = "fees:structure_update"
    filter_spec = FilterSpec(search_fields=("school_class__name", "fee_type__name"))
    table_columns = (
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Fee Type"), "field": "fee_type.name"},
        {"label": _("Amount"), "field": "amount", "type": "money"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class FeeStructureCreateView(TenantCreateView):
    model = FeeStructure
    form_class = FeeStructureForm
    required_permission = "fees.add_feestructure"
    success_url = reverse_lazy("fees:structure_list")
    page_title = _("New Fee Structure")


class FeeStructureUpdateView(TenantUpdateView):
    model = FeeStructure
    form_class = FeeStructureForm
    required_permission = "fees.change_feestructure"
    success_url = reverse_lazy("fees:structure_list")
    page_title = _("Edit Fee Structure")


class StudentFeeListView(TenantListView):
    model = StudentFee
    required_permission = FEES
    create_permission = "fees.add_studentfee"
    page_title = _("Student Fee Overrides")
    select_related = ("student", "fee_type", "academic_year")
    ordering = ["-effective_from"]
    create_url_name = "fees:studentfee_create"
    update_url_name = "fees:studentfee_update"
    filter_spec = FilterSpec(
        search_fields=("student__full_name", "student__admission_no")
    )
    table_columns = (
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Fee Type"), "field": "fee_type.name"},
        {"label": _("Amount"), "field": "amount", "type": "money"},
        {"label": _("From"), "field": "effective_from", "type": "date"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class StudentFeeCreateView(TenantCreateView):
    model = StudentFee
    form_class = StudentFeeForm
    required_permission = "fees.add_studentfee"
    success_url = reverse_lazy("fees:studentfee_list")
    page_title = _("New Fee Override")


class StudentFeeUpdateView(TenantUpdateView):
    model = StudentFee
    form_class = StudentFeeForm
    required_permission = "fees.change_studentfee"
    success_url = reverse_lazy("fees:studentfee_list")
    page_title = _("Edit Fee Override")


class DiscountListView(TenantListView):
    model = FeeDiscount
    required_permission = FEES
    create_permission = "core.waive_fee"
    page_title = _("Fee Discounts")
    select_related = ("student", "fee_type", "approved_by")
    ordering = ["-valid_from"]
    create_url_name = "fees:discount_create"
    update_url_name = "fees:discount_update"
    filter_spec = FilterSpec(search_fields=("name", "student__full_name"))
    table_columns = (
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Name"), "field": "name"},
        {"label": _("Type"), "field": "discount_type", "type": "choice"},
        {"label": _("Value"), "field": "value"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class DiscountCreateView(TenantCreateView):
    model = FeeDiscount
    form_class = FeeDiscountForm
    required_permission = "core.waive_fee"
    success_url = reverse_lazy("fees:discount_list")
    page_title = _("New Discount")

    def form_valid(self, form):
        form.instance.approved_by = self.request.user
        return super().form_valid(form)


class DiscountUpdateView(TenantUpdateView):
    model = FeeDiscount
    form_class = FeeDiscountForm
    required_permission = "core.waive_fee"
    success_url = reverse_lazy("fees:discount_list")
    page_title = _("Edit Discount")


class InvoiceListView(TenantListView):
    model = FeeInvoice
    required_permission = FEES
    create_permission = "fees.add_feeinvoice"
    template_name = "fees/invoice_list.html"
    page_title = _("Invoices")
    select_related = ("student", "academic_year", "term")
    ordering = ["-issue_date"]
    create_url_name = "fees:invoice_generate"
    detail_url_name = "fees:invoice_detail"
    filter_spec = FilterSpec(
        search_fields=("invoice_number", "student__full_name", "student__admission_no"),
        choices={"status": "status"},
        date_field="issue_date",
        selects={
            "status": {"label": _("Status"), "options": FeeInvoice.Status.choices}
        },
    )
    table_columns = (
        {"label": _("Invoice #"), "field": "invoice_number"},
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Issued"), "field": "issue_date", "type": "date"},
        {"label": _("Due"), "field": "due_date", "type": "date"},
        {"label": _("Total"), "field": "total_amount", "type": "money"},
        {"label": _("Paid"), "field": "paid_amount", "type": "money"},
        {"label": _("Balance"), "field": "balance", "type": "money"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = outstanding_summary(self.request.user, self.active_branch)
        return context


class InvoiceDetailView(TenantDetailView):
    model = FeeInvoice
    required_permission = FEES
    template_name = "fees/invoice_detail.html"
    select_related = ("student", "academic_year", "term", "created_by")
    page_title = _("Invoice")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.object.items.select_related("fee_type")
        context["payments"] = self.object.payments.select_related(
            "payment_method", "received_by"
        ).order_by("-payment_date")
        context["waivers"] = self.object.waivers.all()
        context["payment_form"] = PaymentForm(
            branch=self.active_branch, initial={"invoice": self.object}
        )
        context["waiver_form"] = WaiverForm()
        return context


class InvoiceGenerateView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = InvoiceGenerateForm
    template_name = "components/object_form.html"
    required_permission = "fees.add_feeinvoice"
    page_title = _("Generate Invoices")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            if data.get("student"):
                invoice = generate_invoice(
                    student=data["student"],
                    academic_year=data["academic_year"],
                    issue_date=data["issue_date"],
                    due_date=data["due_date"],
                    term=data.get("term"),
                    period_month=data.get("period_month"),
                    actor=self.request.user,
                    request=self.request,
                )
                messages.success(
                    self.request,
                    _("Invoice %(no)s created.") % {"no": invoice.invoice_number},
                )
                return redirect("fees:invoice_detail", pk=invoice.pk)

            created, skipped = generate_invoices_for_class(
                branch=self.active_branch,
                academic_year=data["academic_year"],
                school_class=data["school_class"],
                issue_date=data["issue_date"],
                due_date=data["due_date"],
                period_month=data.get("period_month"),
                term=data.get("term"),
                actor=self.request.user,
                request=self.request,
            )
        except ValidationError as error:
            messages.error(self.request, "; ".join(error.messages))
            return self.form_invalid(form)

        messages.success(
            self.request,
            _("%(created)s invoices created, %(skipped)s skipped.")
            % {"created": len(created), "skipped": len(skipped)},
        )
        return redirect("fees:invoice_list")


class PaymentListView(TenantListView):
    model = FeePayment
    required_permission = FEES
    create_permission = "core.collect_fee_payment"
    page_title = _("Payments")
    select_related = ("student", "invoice", "payment_method", "received_by")
    ordering = ["-payment_date", "-created_at"]
    create_url_name = "fees:payment_create"
    detail_url_name = "fees:payment_detail"
    filter_spec = FilterSpec(
        search_fields=("receipt_number", "student__full_name", "reference"),
        date_field="payment_date",
    )
    table_columns = (
        {"label": _("Receipt #"), "field": "receipt_number"},
        {"label": _("Date"), "field": "payment_date", "type": "date"},
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Method"), "field": "payment_method.name"},
        {"label": _("Amount"), "field": "amount", "type": "money"},
        {"label": _("Void"), "field": "is_void", "type": "bool"},
    )


class PaymentDetailView(TenantDetailView):
    model = FeePayment
    required_permission = FEES
    template_name = "fees/payment_detail.html"
    select_related = ("student", "invoice", "payment_method", "received_by", "journal_entry")
    page_title = _("Receipt")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["refunds"] = self.object.refunds.select_related("approved_by")
        context["refund_form"] = RefundForm(branch=self.active_branch)
        context["void_form"] = VoidPaymentForm()
        return context


class PaymentCreateView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = PaymentForm
    template_name = "fees/payment_form.html"
    required_permission = "core.collect_fee_payment"
    page_title = _("Collect Payment")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            payment = record_payment(
                invoice=data["invoice"],
                amount=data["amount"],
                payment_method=data["payment_method"],
                payment_date=data["payment_date"],
                reference=data.get("reference", ""),
                notes=data.get("notes", ""),
                actor=self.request.user,
                request=self.request,
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(self.request, "; ".join(getattr(error, "messages", [str(error)])))
            return self.form_invalid(form)

        messages.success(
            self.request,
            _("Receipt %(no)s recorded.") % {"no": payment.receipt_number},
        )
        return redirect("fees:payment_detail", pk=payment.pk)


class PaymentRefundView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = RefundForm
    template_name = "components/object_form.html"
    required_permission = "core.refund_fee_payment"
    page_title = _("Refund Payment")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        payment = get_object_or_404(
            FeePayment.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        try:
            refund = refund_payment(
                payment=payment,
                amount=form.cleaned_data["amount"],
                refund_date=form.cleaned_data["refund_date"],
                reason=form.cleaned_data["reason"],
                payment_method=form.cleaned_data.get("payment_method"),
                actor=self.request.user,
                request=self.request,
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(self.request, "; ".join(getattr(error, "messages", [str(error)])))
            return redirect("fees:payment_detail", pk=payment.pk)

        messages.success(
            self.request, _("Refund %(no)s issued.") % {"no": refund.refund_number}
        )
        return redirect("fees:payment_detail", pk=payment.pk)


class PaymentVoidView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = VoidPaymentForm
    template_name = "components/object_form.html"
    required_permission = "core.refund_fee_payment"
    page_title = _("Void Payment")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        payment = get_object_or_404(
            FeePayment.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        try:
            void_payment(
                payment=payment,
                reason=form.cleaned_data["reason"],
                actor=self.request.user,
                request=self.request,
            )
        except ValidationError as error:
            messages.error(self.request, "; ".join(error.messages))
        else:
            messages.success(self.request, _("Payment voided."))
        return redirect("fees:payment_detail", pk=payment.pk)


class InvoiceWaiveView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = WaiverForm
    template_name = "components/object_form.html"
    required_permission = "core.waive_fee"
    page_title = _("Waive Fee")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        invoice = get_object_or_404(
            FeeInvoice.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        try:
            waive_invoice_amount(
                invoice=invoice,
                amount=form.cleaned_data["amount"],
                reason=form.cleaned_data["reason"],
                waived_on=form.cleaned_data["waived_on"],
                actor=self.request.user,
                request=self.request,
            )
        except ValidationError as error:
            messages.error(self.request, "; ".join(error.messages))
        else:
            messages.success(self.request, _("Waiver applied."))
        return redirect("fees:invoice_detail", pk=invoice.pk)


class RefundListView(TenantListView):
    model = FeeRefund
    required_permission = FEES
    page_title = _("Refunds")
    select_related = ("payment__student", "payment_method", "approved_by")
    ordering = ["-refund_date"]
    filter_spec = FilterSpec(
        search_fields=("refund_number", "payment__receipt_number", "reason"),
        date_field="refund_date",
    )
    table_columns = (
        {"label": _("Refund #"), "field": "refund_number"},
        {"label": _("Date"), "field": "refund_date", "type": "date"},
        {"label": _("Student"), "field": "payment.student.full_name"},
        {"label": _("Amount"), "field": "amount", "type": "money"},
        {"label": _("Reason"), "field": "reason"},
    )
