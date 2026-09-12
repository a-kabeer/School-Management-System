"""The timetable workbench.

A timetable is a week, not a list of rows. This screen shows one section's
week as the grid people already have on paper: days across, periods down,
every cell either a lesson or a gap you can fill. Adding and editing happen
in the shared dialog, so building a week never leaves the week.
"""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin
from apps.core.permissions import PermissionRequiredMixin, user_has_permission

from . import selectors
from .models import AcademicYear, SchoolClass, Section, Timetable
from .timetable_config import is_working_day, working_weekdays


MINIMUM_PERIODS = 8


class TimetableWorkbenchView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "academics/timetable_grid.html"
    required_permission = "core.access_academics"
    page_title = _("Timetable")

    def get_selection(self):
        """Year, class and section, each falling back to something sensible."""
        user, branch = self.request.user, self.active_branch
        years = AcademicYear.objects.for_user(user, branch).order_by("-start_date")
        year = years.filter(pk=self.request.GET.get("academic_year")).first() or selectors.current_year(user, branch)

        sections = (
            Section.objects.for_user(user, branch)
            .filter(is_active=True)
            .select_related("school_class")
            .order_by("school_class__level", "school_class__name", "name")
        )
        section = sections.filter(pk=self.request.GET.get("section")).first()
        school_class = SchoolClass.objects.for_user(user, branch).filter(pk=self.request.GET.get("school_class")).first()
        if section is not None:
            school_class = section.school_class
        elif school_class is not None:
            section = sections.filter(school_class=school_class).first()
        else:
            section = sections.first()
            school_class = section.school_class if section else None
        return {"years": years, "year": year, "sections": sections, "section": section, "school_class": school_class}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user, branch = self.request.user, self.active_branch
        selection = self.get_selection()
        year, section = selection["year"], selection["section"]
        context.update(selection)
        context["can_edit"] = user_has_permission(user, "academics.add_timetable", branch)
        context["working_weekdays"] = working_weekdays()
        context["working_day_schedule"] = _("Monday–Friday")
        context["page_subtitle"] = (
            _("%(section)s · %(year)s") % {"section": section, "year": year.name if year else "—"}
            if section else _("Choose a section to build its week.")
        )

        if section is None or year is None:
            context["grid"] = []
            context["weekend_slot_count"] = 0
            return context

        slots = list(selectors.slots_for(user, branch, section=section, academic_year=year))
        working_days = working_weekdays()
        visible_slots = [slot for slot in slots if is_working_day(slot.weekday)]
        context["slots"] = visible_slots
        context["slot_count"] = len(visible_slots)
        context["weekend_slot_count"] = len(slots) - len(visible_slots)
        context["conflicts"] = self.find_conflicts(user, branch, year, visible_slots)

        by_cell = {(slot.weekday, slot.period): slot for slot in visible_slots}
        weekdays = working_days
        highest = max((slot.period for slot in visible_slots), default=0)
        periods = range(1, max(highest, MINIMUM_PERIODS) + 1)
        create_url = reverse("academics:timetable_create")
        context["weekdays"] = [{"value": day, "label": Timetable.Weekday(day).label} for day in weekdays]
        context["grid"] = [
            {
                "period": period,
                "cells": [
                    self.build_cell(
                        by_cell.get((day, period)), day=day, period=period,
                        section=section, year=year, create_url=create_url,
                        conflicts=context["conflicts"],
                    )
                    for day in weekdays
                ],
            }
            for period in periods
        ]
        return context

    def build_cell(self, slot, *, day, period, section, year, create_url, conflicts):
        if slot is None:
            return {
                "slot": None,
                "add_url": f"{create_url}?academic_year={year.pk}&section={section.pk}&weekday={day}&period={period}",
                "label": _("Add lesson"),
            }
        return {
            "slot": slot,
            "edit_url": reverse("academics:timetable_update", args=[slot.pk]),
            "view_url": reverse("academics:timetable_detail", args=[slot.pk]),
            "conflict": conflicts.get(slot.pk),
        }

    def find_conflicts(self, user, branch, year, slots):
        """Which of these lessons need a teacher who is already elsewhere."""
        teachers = {slot.teacher_id for slot in slots if slot.teacher_id}
        if not teachers or not slots:
            return {}
        elsewhere = selectors.slots_for(
            user, branch, academic_year=year, teacher_id__in=teachers
        ).exclude(section_id=slots[0].section_id)
        booked = {}
        for other in elsewhere:
            if is_working_day(other.weekday):
                booked.setdefault((other.teacher_id, other.weekday, other.period), other)
        conflicts = {}
        for slot in slots:
            clash = booked.get((slot.teacher_id, slot.weekday, slot.period))
            if clash is not None:
                conflicts[slot.pk] = clash
        return conflicts
