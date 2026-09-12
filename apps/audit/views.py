from django.utils.translation import gettext_lazy as _

from apps.core.filters import FilterSpec
from apps.core.mixins import TenantDetailView, TenantListView

from .models import ActivityLog


class ActivityLogListView(TenantListView):
    """Searchable, filterable trail for administrators."""

    model = ActivityLog
    required_permission = "core.access_audit"
    requires_branch = False
    across_branches = True
    page_title = _("Audit Log")
    page_subtitle = _("Every recorded action, newest first.")
    select_related = ("user", "branch", "organization")
    ordering = ["-created_at"]
    paginate_by = 50
    detail_url_name = "audit:detail"
    empty_message = _("No activity recorded yet")
    table_columns = (
        {"label": _("When"), "field": "created_at", "type": "datetime"},
        {"label": _("User"), "field": "username"},
        {"label": _("Role"), "field": "role_name"},
        {"label": _("Action"), "field": "action", "type": "choice"},
        {"label": _("Module"), "field": "app_label"},
        {"label": _("Resource"), "field": "model_name"},
        {"label": _("Object"), "field": "object_repr"},
        {"label": _("Branch"), "field": "branch.name"},
        {"label": _("IP"), "field": "ip_address"},
    )
    filter_spec = FilterSpec(
        search_fields=("object_repr", "username", "model_name", "request_path"),
        choices={"action": "action", "module": "app_label", "user": "user_id"},
        date_field="created_at__date",
        selects={
            "action": {
                "label": _("Action"),
                "options": ActivityLog.Action.choices,
            }
        },
    )

    def get_base_queryset(self):
        return ActivityLog.objects.all()

    def get_list_queryset(self):
        queryset = ActivityLog.objects.for_user(
            self.request.user, None if self.across_branches else self.active_branch
        ).select_related(*self.select_related)
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        return queryset


class ActivityLogDetailView(TenantDetailView):
    model = ActivityLog
    required_permission = "core.access_audit"
    requires_branch = False
    across_branches = True
    template_name = "audit/activity_detail.html"
    page_title = _("Audit Entry")

    def get_queryset(self):
        return ActivityLog.objects.for_user(self.request.user).select_related(
            "user", "branch", "organization"
        )
