from django.views.generic import TemplateView

from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin
from apps.core.permissions import PermissionRequiredMixin, user_has_permission

from .models import Timetable
from .timetable_config import working_weekdays


class AffectedTimetableSlotsView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "academics/timetable_affected.html"
    required_permission = "core.access_academics"
    page_title = "Affected Timetable Slots"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slots = (
            Timetable.objects.for_user(self.request.user, self.active_branch)
            .exclude(weekday__in=working_weekdays(self.active_branch))
            .select_related(
                "teacher", "section__school_class", "class_subject__subject", "academic_year"
            )
            .order_by("weekday", "academic_year__start_date", "section__school_class__level", "section__name", "period")
        )
        context["slots"] = slots
        context["can_edit"] = user_has_permission(
            self.request.user, "academics.change_timetable", self.active_branch
        )
        return context
