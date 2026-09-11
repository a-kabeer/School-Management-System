"""Dashboard, health check and shared error handlers."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from .permissions import PermissionRequiredMixin
from .services import collection_trend, dashboard_summary, recent_activity


def health(request):
    """Unauthenticated liveness probe for the platform."""
    return JsonResponse({"status": "ok"})


class DashboardView(PermissionRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"
    required_permission = "core.access_dashboard"

    def dispatch(self, request, *args, **kwargs):
        # Parents get their own portal; the staff dashboard would be empty for
        # them and its queries are not child-scoped.
        if (
            request.user.is_authenticated
            and getattr(request.user, "is_parent_account", False)
            and not request.user.is_superuser
        ):
            return redirect("parents:portal_home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = getattr(self.request, "active_branch", None)
        context["page_title"] = _("Dashboard")
        context["summary"] = dashboard_summary(self.request.user, branch)
        context["activity"] = recent_activity(self.request.user, branch)
        context["trend"] = collection_trend(self.request.user, branch)
        context["trend_max"] = max(
            [row["total"] for row in context["trend"]] or [0]
        ) or 1
        return context


@login_required
def home(request):
    return redirect("core:dashboard")


def permission_denied_view(request, exception=None):
    return render(
        request,
        "errors/403.html",
        {"message": str(exception) if exception else _("Access denied.")},
        status=403,
    )


def not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error_view(request):
    return render(request, "errors/500.html", status=500)
