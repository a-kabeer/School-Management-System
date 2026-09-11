from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantDetailView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin, require_permission
from apps.core.utils import parse_date

from .forms import (
    AccountForm,
    AccountTypeForm,
    FiscalPeriodForm,
    JournalEntryForm,
    JournalEntryLineFormSet,
    JournalForm,
    PaymentMethodForm,
)
from .models import Account, AccountType, FiscalPeriod, Journal, JournalEntry, PaymentMethod
from .services import (
    close_fiscal_period,
    income_statement,
    post_journal_entry,
    reverse_journal_entry,
    trial_balance,
)

FINANCE = "core.access_finance"


class AccountListView(TenantListView):
    model = Account
    required_permission = FINANCE
    create_permission = "finance.add_account"
    template_name = "finance/account_list.html"
    page_title = _("Chart of Accounts")
    select_related = ("account_type", "parent")
    ordering = ["code"]
    create_url_name = "finance:account_create"
    update_url_name = "finance:account_update"
    filter_spec = FilterSpec(search_fields=("code", "name"))
    table_columns = (
        {"label": _("Code"), "field": "code"},
        {"label": _("Name"), "field": "name"},
        {"label": _("Type"), "field": "account_type.name"},
        {"label": _("Nature"), "field": "account_type.nature", "type": "choice"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class AccountCreateView(TenantCreateView):
    model = Account
    form_class = AccountForm
    required_permission = "finance.add_account"
    success_url = reverse_lazy("finance:account_list")
    page_title = _("New Account")


class AccountUpdateView(TenantUpdateView):
    model = Account
    form_class = AccountForm
    required_permission = "finance.change_account"
    success_url = reverse_lazy("finance:account_list")
    page_title = _("Edit Account")


class AccountTypeListView(TenantListView):
    model = AccountType
    required_permission = FINANCE
    create_permission = "finance.add_accounttype"
    requires_branch = False
    across_branches = True
    page_title = _("Account Types")
    ordering = ["code"]
    create_url_name = "finance:accounttype_create"
    update_url_name = "finance:accounttype_update"
    filter_spec = FilterSpec(search_fields=("code", "name"))
    table_columns = (
        {"label": _("Code"), "field": "code"},
        {"label": _("Name"), "field": "name"},
        {"label": _("Nature"), "field": "nature", "type": "choice"},
        {"label": _("Normal Balance"), "field": "normal_balance", "type": "choice"},
    )


class AccountTypeCreateView(TenantCreateView):
    model = AccountType
    form_class = AccountTypeForm
    required_permission = "finance.add_accounttype"
    requires_branch = False
    success_url = reverse_lazy("finance:accounttype_list")
    page_title = _("New Account Type")


class AccountTypeUpdateView(TenantUpdateView):
    model = AccountType
    form_class = AccountTypeForm
    required_permission = "finance.change_accounttype"
    requires_branch = False
    success_url = reverse_lazy("finance:accounttype_list")
    page_title = _("Edit Account Type")


class JournalListView(TenantListView):
    model = Journal
    required_permission = FINANCE
    create_permission = "finance.add_journal"
    page_title = _("Journals")
    ordering = ["code"]
    create_url_name = "finance:journal_create"
    update_url_name = "finance:journal_update"
    filter_spec = FilterSpec(search_fields=("code", "name"))
    table_columns = (
        {"label": _("Code"), "field": "code"},
        {"label": _("Name"), "field": "name"},
        {"label": _("Type"), "field": "journal_type", "type": "choice"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class JournalCreateView(TenantCreateView):
    model = Journal
    form_class = JournalForm
    required_permission = "finance.add_journal"
    success_url = reverse_lazy("finance:journal_list")
    page_title = _("New Journal")


class JournalUpdateView(TenantUpdateView):
    model = Journal
    form_class = JournalForm
    required_permission = "finance.change_journal"
    success_url = reverse_lazy("finance:journal_list")
    page_title = _("Edit Journal")


class JournalEntryListView(TenantListView):
    model = JournalEntry
    required_permission = FINANCE
    create_permission = "core.post_journal_entry"
    page_title = _("Journal Entries")
    select_related = ("journal", "fiscal_period", "created_by")
    ordering = ["-date", "-entry_number"]
    create_url_name = "finance:entry_create"
    detail_url_name = "finance:entry_detail"
    filter_spec = FilterSpec(
        search_fields=("entry_number", "reference", "description"),
        choices={"status": "status"},
        date_field="date",
        selects={
            "status": {"label": _("Status"), "options": JournalEntry.Status.choices}
        },
    )
    table_columns = (
        {"label": _("Entry #"), "field": "entry_number"},
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Journal"), "field": "journal.name"},
        {"label": _("Description"), "field": "description"},
        {"label": _("Debit"), "field": "total_debit", "type": "money"},
        {"label": _("Credit"), "field": "total_credit", "type": "money"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class JournalEntryDetailView(TenantDetailView):
    model = JournalEntry
    required_permission = FINANCE
    template_name = "finance/entry_detail.html"
    select_related = ("journal", "fiscal_period", "created_by", "reversal_of")
    page_title = _("Journal Entry")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("account")
        return context


class JournalEntryCreateView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Manual journal entry: a header plus a formset of debit/credit lines."""

    template_name = "finance/entry_form.html"
    required_permission = "core.post_journal_entry"
    page_title = _("New Journal Entry")

    def get_forms(self, data=None):
        form = JournalEntryForm(data, user=self.request.user, branch=self.active_branch)
        formset = JournalEntryLineFormSet(
            data,
            form_kwargs={"branch": self.active_branch},
            prefix="lines",
        )
        return form, formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("form", kwargs.get("form"))
        context.setdefault("formset", kwargs.get("formset"))
        if context["form"] is None:
            context["form"], context["formset"] = self.get_forms()
        return context

    def get(self, request, *args, **kwargs):
        form, formset = self.get_forms()
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )

    def post(self, request, *args, **kwargs):
        form, formset = self.get_forms(request.POST)
        if form.is_valid() and formset.is_valid():
            lines = [
                {
                    "account": line["account"],
                    "debit": line.get("debit"),
                    "credit": line.get("credit"),
                    "description": line.get("description", ""),
                }
                for line in formset.cleaned_data
                if line.get("account")
            ]
            try:
                entry = post_journal_entry(
                    branch=self.active_branch,
                    date=form.cleaned_data["date"],
                    lines=lines,
                    journal_type=form.cleaned_data["journal_type"],
                    description=form.cleaned_data.get("description", ""),
                    reference=form.cleaned_data.get("reference", ""),
                    source_module="finance",
                    actor=request.user,
                    request=request,
                )
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
            else:
                messages.success(
                    request,
                    _("Entry %(no)s posted.") % {"no": entry.entry_number},
                )
                return redirect("finance:entry_detail", pk=entry.pk)
        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )


class JournalEntryReverseView(ActiveBranchMixin, View):
    def post(self, request, pk, *args, **kwargs):
        require_permission(request.user, "core.post_journal_entry", self.active_branch)
        entry = JournalEntry.objects.for_user(request.user, self.active_branch).filter(
            pk=pk
        ).first()
        if entry is None:
            messages.error(request, _("Record not found."))
            return redirect("finance:entry_list")
        try:
            reversal = reverse_journal_entry(
                entry=entry,
                reason=request.POST.get("reason", "")[:255],
                actor=request.user,
                request=request,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
            return redirect("finance:entry_detail", pk=entry.pk)
        messages.success(request, _("Entry reversed."))
        return redirect("finance:entry_detail", pk=reversal.pk)


class FiscalPeriodListView(TenantListView):
    model = FiscalPeriod
    required_permission = FINANCE
    create_permission = "finance.add_fiscalperiod"
    template_name = "finance/period_list.html"
    page_title = _("Fiscal Periods")
    ordering = ["-start_date"]
    create_url_name = "finance:period_create"
    update_url_name = "finance:period_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Start"), "field": "start_date", "type": "date"},
        {"label": _("End"), "field": "end_date", "type": "date"},
        {"label": _("Closed"), "field": "is_closed", "type": "bool"},
    )


class FiscalPeriodCreateView(TenantCreateView):
    model = FiscalPeriod
    form_class = FiscalPeriodForm
    required_permission = "finance.add_fiscalperiod"
    success_url = reverse_lazy("finance:period_list")
    page_title = _("New Fiscal Period")


class FiscalPeriodUpdateView(TenantUpdateView):
    model = FiscalPeriod
    form_class = FiscalPeriodForm
    required_permission = "finance.change_fiscalperiod"
    success_url = reverse_lazy("finance:period_list")
    page_title = _("Edit Fiscal Period")


class FiscalPeriodCloseView(ActiveBranchMixin, View):
    def post(self, request, pk, *args, **kwargs):
        require_permission(request.user, "finance.change_fiscalperiod", self.active_branch)
        period = FiscalPeriod.objects.for_user(request.user, self.active_branch).filter(
            pk=pk
        ).first()
        if period is None:
            messages.error(request, _("Record not found."))
        else:
            try:
                close_fiscal_period(period=period, actor=request.user, request=request)
                messages.success(request, _("Period closed."))
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
        return redirect("finance:period_list")


class PaymentMethodListView(TenantListView):
    model = PaymentMethod
    required_permission = FINANCE
    create_permission = "finance.add_paymentmethod"
    page_title = _("Payment Methods")
    select_related = ("account",)
    ordering = ["name"]
    create_url_name = "finance:method_create"
    update_url_name = "finance:method_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Type"), "field": "method_type", "type": "choice"},
        {"label": _("Account"), "field": "account.name"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class PaymentMethodCreateView(TenantCreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    required_permission = "finance.add_paymentmethod"
    success_url = reverse_lazy("finance:method_list")
    page_title = _("New Payment Method")


class PaymentMethodUpdateView(TenantUpdateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    required_permission = "finance.change_paymentmethod"
    success_url = reverse_lazy("finance:method_list")
    page_title = _("Edit Payment Method")


class TrialBalanceView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "finance/trial_balance.html"
    required_permission = FINANCE
    page_title = _("Trial Balance")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        date_from = parse_date(self.request.GET.get("date_from"))
        date_to = parse_date(self.request.GET.get("date_to"), timezone.localdate())
        context["report"] = trial_balance(
            self.request.user, self.active_branch, date_from=date_from, date_to=date_to
        )
        context["income_statement"] = income_statement(
            self.request.user, self.active_branch, date_from=date_from, date_to=date_to
        )
        context["date_from"] = date_from
        context["date_to"] = date_to
        return context
