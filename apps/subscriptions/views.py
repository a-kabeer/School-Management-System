from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.filters import FilterSpec
from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin, TenantListView
from apps.core.permissions import PermissionRequiredMixin

from .models import Plan, SubscriptionInvoice
from .services import plan_limits


class SubscriptionDetailView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "subscriptions/detail.html"
    required_permission = "core.access_subscriptions"
    requires_branch = False
    page_title = _("Subscription")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["usage"] = plan_limits(self.organization)
        context["plans"] = Plan.objects.filter(is_active=True)
        context["invoices"] = SubscriptionInvoice.objects.for_user(
            self.request.user
        ).select_related("subscription__plan")[:12]
        return context


class SubscriptionInvoiceListView(TenantListView):
    model = SubscriptionInvoice
    required_permission = "core.access_subscriptions"
    requires_branch = False
    across_branches = True
    page_title = _("Subscription Invoices")
    select_related = ("subscription__plan",)
    ordering = ["-issue_date"]
    filter_spec = FilterSpec(
        search_fields=("invoice_number",),
        choices={"status": "status"},
        selects={
            "status": {
                "label": _("Status"),
                "options": SubscriptionInvoice.Status.choices,
            }
        },
    )
    table_columns = (
        {"label": _("Invoice #"), "field": "invoice_number"},
        {"label": _("Plan"), "field": "subscription.plan.name"},
        {"label": _("Period"), "field": "period_start", "type": "date"},
        {"label": _("Total"), "field": "total_amount", "type": "money"},
        {"label": _("Due"), "field": "due_date", "type": "date"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )
