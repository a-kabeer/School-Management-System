from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin
from apps.core.permissions import PermissionRequiredMixin, user_has_permission

from .models import Timetable
from .timetable_config import working_weekdays


class AffectedTimetableSlotsView(PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView):
    template_name = "academics/timetable_affected.html"
    required_permission = "core.access_academics"
    page_title = _("Affected Timetable Slots")

    def get_slots(self):
        return (
            Timetable.objects.for_user(self.request.user, self.active_branch)
            .exclude(weekday__in=working_weekdays(self.active_branch))
            .select_related("teacher", "section__school_class", "class_subject__subject", "academic_year")
            .order_by("weekday", "academic_year__start_date", "section__school_class__level", "section__name", "period")
        )

    def post(self, request, *args, **kwargs):
        slot = get_object_or_404(self.get_slots(), pk=request.POST.get("slot"))
        try:
            weekday = int(request.POST.get("weekday"))
        except (TypeError, ValueError):
            messages.error(request, _("Choose a valid working day."))
            return redirect("academics:timetable_affected")
        if weekday not in working_weekdays(self.active_branch):
            messages.error(request, _("Choose a currently configured working day."))
            return redirect("academics:timetable_affected")
        slot.weekday = weekday
        slot.save(update_fields=["weekday"])
        messages.success(request, _("Timetable slot moved to %(day)s.") % {"day": slot.get_weekday_display()})
        return redirect("academics:timetable_affected")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["slots"] = self.get_slots()
        context["working_days"] = [(day, Timetable.Weekday(day).label) for day in working_weekdays(self.active_branch)]
        context["can_edit"] = user_has_permission(self.request.user, "academics.change_timetable", self.active_branch)
        return context
