from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantListView,
)
from apps.core.pagination import paginate, querystring_without_page
from apps.core.permissions import (
    PermissionRequiredMixin,
    require_permission,
    user_has_permission,
)
from apps.core.utils import export_to_excel, parse_date

from .models import ReportExport, SavedReport
from .registry import available_reports, get_report

REPORTS = "core.access_reports"


class ReportIndexView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "reports/index.html"
    required_permission = REPORTS
    requires_branch = False
    page_title = _("Reports")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.db.models import Q

        context["reports"] = available_reports(self.request.user, self.active_branch)
        context["saved"] = SavedReport.objects.for_user(self.request.user).filter(
            Q(is_shared=True) | Q(created_by=self.request.user)
        )[:20]
        return context


class ReportDetailView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Runs one registered report, with optional Excel export."""

    template_name = "reports/detail.html"
    required_permission = REPORTS
    requires_branch = False

    def get_definition(self):
        definition = get_report(self.kwargs["key"])
        if definition is None:
            raise Http404(_("Unknown report."))
        # The report's own permission is checked on top of "can see reports".
        require_permission(self.request.user, definition.permission, self.active_branch)
        return definition

    def get_params(self):
        return {
            "date_from": parse_date(self.request.GET.get("date_from")),
            "date_to": parse_date(self.request.GET.get("date_to")),
            "status": self.request.GET.get("status") or "",
        }

    def get(self, request, *args, **kwargs):
        definition = self.get_definition()
        params = self.get_params()
        # Organization-wide reports span every accessible branch; the rest
        # stay inside the branch the user is working in.
        branch = None if definition.organization_wide else self.active_branch
        data = definition.builder(request.user, branch, params)

        if request.GET.get("export") == "xlsx":
            if not user_has_permission(
                request.user, "core.export_report", self.active_branch
            ):
                messages.error(request, _("You are not allowed to export reports."))
                return redirect("reports:detail", key=definition.key)

            from apps.audit.services import log_activity

            ReportExport.objects.create(
                organization=self.organization,
                branch=self.active_branch,
                report_key=definition.key,
                filters={k: str(v) for k, v in params.items() if v},
                row_count=len(data["rows"]),
                exported_by=request.user,
            )
            log_activity(
                action="export",
                request=request,
                metadata={
                    "report": definition.key,
                    "rows": len(data["rows"]),
                    "filters": {k: str(v) for k, v in params.items() if v},
                },
            )
            return export_to_excel(
                str(definition.label),
                [str(h) for h in data["headers"]],
                data["rows"],
                sheet_title=str(definition.label),
            )

        # Totals arrive keyed by column index; flatten them to a row the
        # template can walk alongside the headers.
        totals = data.get("totals") or {}
        total_row = (
            [totals.get(index) for index in range(len(data["headers"]))]
            if totals
            else None
        )

        page, paginator = paginate(request, data["rows"], per_page=100)
        context = self.get_context_data(**kwargs)
        context.update(
            {
                "definition": definition,
                "headers": data["headers"],
                "rows": page.object_list,
                "total_row": total_row,
                "meta": data.get("meta", {}),
                "row_count": len(data["rows"]),
                "page_obj": page,
                "paginator": paginator,
                "is_paginated": page.has_other_pages(),
                "querystring": querystring_without_page(request),
                "page_title": definition.label,
                "params": params,
                "can_export": user_has_permission(
                    request.user, "core.export_report", self.active_branch
                ),
            }
        )
        return self.render_to_response(context)


class SavedReportListView(TenantListView):
    model = SavedReport
    required_permission = REPORTS
    requires_branch = False
    across_branches = True
    page_title = _("Saved Reports")
    ordering = ["name"]
    filter_spec = FilterSpec(search_fields=("name", "report_key"))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Report"), "field": "report_key"},
        {"label": _("Shared"), "field": "is_shared", "type": "bool"},
    )

    def get_list_queryset(self):
        from django.db.models import Q

        return SavedReport.objects.for_user(self.request.user).filter(
            Q(is_shared=True) | Q(created_by=self.request.user)
        )
