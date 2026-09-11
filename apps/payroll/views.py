from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, View

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
    EmployeeSalaryForm,
    PayrollPeriodForm,
    ProcessPayrollForm,
    SalaryComponentForm,
    SalaryPaymentForm,
    SalaryStructureForm,
    SalaryStructureLineForm,
)
from .models import (
    EmployeeSalary,
    PayrollItem,
    PayrollPeriod,
    PayrollRun,
    SalaryComponent,
    SalaryPayment,
    SalaryStructure,
    SalaryStructureLine,
)
from .services import approve_payroll_run, pay_salary, payroll_summary, process_payroll

PAYROLL = "core.access_payroll"


class SalaryComponentListView(TenantListView):
    model = SalaryComponent
    required_permission = PAYROLL
    create_permission = "payroll.add_salarycomponent"
    page_title = _("Salary Components")
    ordering = ["component_type", "name"]
    create_url_name = "payroll:component_create"
    update_url_name = "payroll:component_update"
    filter_spec = FilterSpec(search_fields=("name", "code"))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Code"), "field": "code"},
        {"label": _("Type"), "field": "component_type", "type": "choice"},
        {"label": _("Calculation"), "field": "calculation_type", "type": "choice"},
        {"label": _("Default"), "field": "default_value", "type": "money"},
    )


class SalaryComponentCreateView(TenantCreateView):
    model = SalaryComponent
    form_class = SalaryComponentForm
    required_permission = "payroll.add_salarycomponent"
    success_url = reverse_lazy("payroll:component_list")
    page_title = _("New Salary Component")


class SalaryComponentUpdateView(TenantUpdateView):
    model = SalaryComponent
    form_class = SalaryComponentForm
    required_permission = "payroll.change_salarycomponent"
    success_url = reverse_lazy("payroll:component_list")
    page_title = _("Edit Salary Component")


class SalaryStructureListView(TenantListView):
    model = SalaryStructure
    required_permission = PAYROLL
    create_permission = "payroll.add_salarystructure"
    page_title = _("Salary Structures")
    ordering = ["name"]
    create_url_name = "payroll:structure_create"
    detail_url_name = "payroll:structure_detail"
    update_url_name = "payroll:structure_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Basic Salary"), "field": "basic_salary", "type": "money"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class SalaryStructureDetailView(TenantDetailView):
    model = SalaryStructure
    required_permission = PAYROLL
    template_name = "payroll/structure_detail.html"
    page_title = _("Salary Structure")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("component").order_by(
            "sequence"
        )
        return context


class SalaryStructureCreateView(TenantCreateView):
    model = SalaryStructure
    form_class = SalaryStructureForm
    required_permission = "payroll.add_salarystructure"
    success_url = reverse_lazy("payroll:structure_list")
    page_title = _("New Salary Structure")


class SalaryStructureUpdateView(TenantUpdateView):
    model = SalaryStructure
    form_class = SalaryStructureForm
    required_permission = "payroll.change_salarystructure"
    success_url = reverse_lazy("payroll:structure_list")
    page_title = _("Edit Salary Structure")


class StructureLineCreateView(TenantCreateView):
    model = SalaryStructureLine
    form_class = SalaryStructureLineForm
    required_permission = "payroll.add_salarystructure"
    success_url = reverse_lazy("payroll:structure_list")
    page_title = _("Add Structure Line")


class EmployeeSalaryListView(TenantListView):
    model = EmployeeSalary
    required_permission = PAYROLL
    create_permission = "payroll.add_employeesalary"
    page_title = _("Employee Salaries")
    select_related = ("staff", "structure")
    ordering = ["-effective_from"]
    create_url_name = "payroll:salary_create"
    update_url_name = "payroll:salary_update"
    filter_spec = FilterSpec(
        search_fields=("staff__full_name", "staff__employee_no")
    )
    table_columns = (
        {"label": _("Staff"), "field": "staff.full_name"},
        {"label": _("Structure"), "field": "structure.name"},
        {"label": _("Basic"), "field": "basic_salary", "type": "money"},
        {"label": _("From"), "field": "effective_from", "type": "date"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class EmployeeSalaryCreateView(TenantCreateView):
    model = EmployeeSalary
    form_class = EmployeeSalaryForm
    required_permission = "payroll.add_employeesalary"
    success_url = reverse_lazy("payroll:salary_list")
    page_title = _("New Employee Salary")


class EmployeeSalaryUpdateView(TenantUpdateView):
    model = EmployeeSalary
    form_class = EmployeeSalaryForm
    required_permission = "payroll.change_employeesalary"
    success_url = reverse_lazy("payroll:salary_list")
    page_title = _("Edit Employee Salary")


class PayrollPeriodListView(TenantListView):
    model = PayrollPeriod
    required_permission = PAYROLL
    create_permission = "payroll.add_payrollperiod"
    page_title = _("Payroll Periods")
    ordering = ["-month"]
    create_url_name = "payroll:period_create"
    update_url_name = "payroll:period_update"
    filter_spec = FilterSpec(
        search_fields=("name",),
        choices={"status": "status"},
        selects={
            "status": {"label": _("Status"), "options": PayrollPeriod.Status.choices}
        },
    )
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Month"), "field": "month", "type": "date"},
        {"label": _("Payment Date"), "field": "payment_date", "type": "date"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class PayrollPeriodCreateView(TenantCreateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    required_permission = "payroll.add_payrollperiod"
    success_url = reverse_lazy("payroll:period_list")
    page_title = _("New Payroll Period")


class PayrollPeriodUpdateView(TenantUpdateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    required_permission = "payroll.change_payrollperiod"
    success_url = reverse_lazy("payroll:period_list")
    page_title = _("Edit Payroll Period")


class PayrollRunListView(TenantListView):
    model = PayrollRun
    required_permission = PAYROLL
    create_permission = "core.run_payroll"
    template_name = "payroll/run_list.html"
    page_title = _("Payroll Runs")
    select_related = ("period", "processed_by")
    ordering = ["-run_date"]
    create_url_name = "payroll:run_process"
    detail_url_name = "payroll:run_detail"
    filter_spec = FilterSpec(
        search_fields=("reference", "period__name"),
        choices={"status": "status"},
        selects={"status": {"label": _("Status"), "options": PayrollRun.Status.choices}},
    )
    table_columns = (
        {"label": _("Reference"), "field": "reference"},
        {"label": _("Period"), "field": "period.name"},
        {"label": _("Run Date"), "field": "run_date", "type": "date"},
        {"label": _("Employees"), "field": "employee_count"},
        {"label": _("Net"), "field": "total_net", "type": "money"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = payroll_summary(self.request.user, self.active_branch)
        return context


class PayrollRunDetailView(TenantDetailView):
    model = PayrollRun
    required_permission = PAYROLL
    template_name = "payroll/run_detail.html"
    select_related = ("period", "processed_by", "journal_entry")
    page_title = _("Payroll Run")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.object.items.select_related("staff").prefetch_related(
            "payments"
        )
        context["payment_form"] = SalaryPaymentForm(branch=self.active_branch)
        return context


class ProcessPayrollView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = ProcessPayrollForm
    template_name = "components/object_form.html"
    required_permission = "core.run_payroll"
    page_title = _("Process Payroll")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        try:
            run = process_payroll(
                period=form.cleaned_data["period"],
                run_date=form.cleaned_data["run_date"],
                actor=self.request.user,
                request=self.request,
            )
        except ValidationError as error:
            messages.error(self.request, "; ".join(error.messages))
            return self.form_invalid(form)

        messages.success(
            self.request,
            _("Run %(ref)s created for %(count)s employees.")
            % {"ref": run.reference, "count": run.employee_count},
        )
        return redirect("payroll:run_detail", pk=run.pk)


class ApprovePayrollRunView(PermissionRequiredMixin, ActiveBranchMixin, View):
    """Approve a draft run. POST-only, so it cannot be triggered by a link."""

    required_permission = "core.run_payroll"

    def post(self, request, pk, *args, **kwargs):
        run = get_object_or_404(
            PayrollRun.objects.for_user(request.user, self.active_branch), pk=pk
        )
        try:
            approve_payroll_run(run=run, actor=request.user, request=request)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(request, _("Payroll run approved and posted."))
        return redirect("payroll:run_detail", pk=run.pk)

    def get(self, request, *args, **kwargs):
        return redirect("payroll:run_list")


class PaySalaryView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = SalaryPaymentForm
    template_name = "components/object_form.html"
    required_permission = "core.run_payroll"
    page_title = _("Pay Salary")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def form_valid(self, form):
        item = get_object_or_404(
            PayrollItem.objects.for_user(self.request.user, self.active_branch),
            pk=self.kwargs["pk"],
        )
        try:
            payment = pay_salary(
                payroll_item=item,
                payment_method=form.cleaned_data["payment_method"],
                amount=form.cleaned_data.get("amount"),
                payment_date=form.cleaned_data["payment_date"],
                reference=form.cleaned_data.get("reference", ""),
                actor=self.request.user,
                request=self.request,
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(
                self.request, "; ".join(getattr(error, "messages", [str(error)]))
            )
            return redirect("payroll:run_detail", pk=item.run_id)

        messages.success(
            self.request,
            _("Voucher %(no)s paid.") % {"no": payment.voucher_number},
        )
        return redirect("payroll:run_detail", pk=item.run_id)


class SalaryPaymentListView(TenantListView):
    model = SalaryPayment
    required_permission = PAYROLL
    page_title = _("Salary Payments")
    select_related = ("payroll_item__staff", "payment_method", "paid_by")
    ordering = ["-payment_date"]
    filter_spec = FilterSpec(
        search_fields=("voucher_number", "payroll_item__staff__full_name"),
        date_field="payment_date",
    )
    table_columns = (
        {"label": _("Voucher #"), "field": "voucher_number"},
        {"label": _("Date"), "field": "payment_date", "type": "date"},
        {"label": _("Staff"), "field": "payroll_item.staff.full_name"},
        {"label": _("Amount"), "field": "amount", "type": "money"},
        {"label": _("Method"), "field": "payment_method.name"},
    )
