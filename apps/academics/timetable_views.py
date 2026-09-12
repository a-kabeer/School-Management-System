"""The timetable workbench."""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin
from apps.core.permissions import PermissionRequiredMixin, user_has_permission

from . import selectors
from .models import AcademicYear, SchoolClass, Section, Timetable
from .timetable_config import is_working_day, working_weekdays

MINIMUM_PERIODS = 8


class TimetableWorkbenchView(PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView):
    template_name = "academics/timetable_grid.html"
    required_permission = "core.access_academics"
    page_title = _("Timetable")

    def get_selection(self):
        user, branch = self.request.user, self.active_branch
        years = AcademicYear.objects.for_user(user, branch).order_by("-start_date")
        year = years.filter(pk=self.request.GET.get("academic_year")).first() or selectors.current_year(user, branch)
        classes = SchoolClass.objects.for_user(user, branch).filter(is_active=True).order_by("level", "name")
        school_class = classes.filter(pk=self.request.GET.get("school_class")).first()
        sections = Section.objects.for_user(user, branch).filter(is_active=True).select_related("school_class").order_by("school_class__level", "school_class__name", "name")
        if school_class is not None:
            sections = sections.filter(school_class=school_class)
        requested_section = self.request.GET.get("section")
        section = None
        if requested_section and requested_section != "all":
            section = sections.filter(pk=requested_section).first()
            if section is not None:
                school_class = section.school_class
        return {"years": years, "classes": classes, "year": year, "sections": sections, "section": section, "school_class": school_class, "all_sections": school_class is not None and section is None}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user, branch = self.request.user, self.active_branch
        selection = self.get_selection(); year, section, school_class = selection["year"], selection["section"], selection["school_class"]
        context.update(selection)
        context["can_edit"] = user_has_permission(user, "academics.add_timetable", branch)
        context["working_weekdays"] = working_weekdays(branch)
        context["working_day_schedule"] = ", ".join(str(Timetable.Weekday(day).label) for day in working_weekdays(branch))
        context["page_subtitle"] = _("%(klass)s · All Sections · %(year)s") % {"klass": school_class.name, "year": year.name} if school_class is not None and year else _("%(section)s · %(year)s") % {"section": section, "year": year.name} if section and year else _("Choose a class to build its timetable.")
        context["weekend_slot_count"] = Timetable.objects.for_user(user, branch).exclude(weekday__in=working_weekdays(branch)).count()
        if school_class is None or year is None:
            context["grid"] = []; context["slot_count"] = 0; context["conflicts"] = {}; return context
        if section is not None:
            slots = list(selectors.slots_for(user, branch, section=section, academic_year=year))
        else:
            slots = list(selectors.slots_for(user, branch, section__school_class=school_class, academic_year=year))
        context["slots"] = slots; context["slot_count"] = len(slots); context["conflicts"] = self.find_conflicts(user, branch, year, slots)
        by_cell = {}
        for slot in slots: by_cell.setdefault((slot.weekday, slot.period), []).append(slot)
        weekdays = working_weekdays(branch); highest = max((slot.period for slot in slots), default=0); periods = range(1, max(highest, MINIMUM_PERIODS) + 1); create_url = reverse("academics:timetable_create")
        context["weekdays"] = [{"value": day, "label": Timetable.Weekday(day).label} for day in weekdays]
        context["grid"] = [{"period": period, "cells": [self.build_cell(by_cell.get((day, period), []), day=day, period=period, section=section, year=year, school_class=school_class, create_url=create_url, conflicts=context["conflicts"]) for day in weekdays]} for period in periods]
        return context

    def build_cell(self, slots, *, day, period, section, year, school_class, create_url, conflicts):
        if not slots:
            add_url = f"{create_url}?academic_year={year.pk}&school_class={school_class.pk}&weekday={day}&period={period}"
            if section is not None: add_url += f"&section={section.pk}"
            return {"slots": [], "add_url": add_url if section is not None else "", "label": _("Add lesson") if section is not None else _("Choose a section to add a lesson")}
        return {"slots": slots, "add_url": "", "label": _("Add lesson"), "conflicts": [conflicts.get(slot.pk) for slot in slots if conflicts.get(slot.pk)]}

    def find_conflicts(self, user, branch, year, slots):
        teachers = {slot.teacher_id for slot in slots if slot.teacher_id}
        if not teachers or not slots: return {}
        elsewhere = selectors.slots_for(user, branch, academic_year=year, teacher_id__in=teachers)
        selected_ids = {slot.pk for slot in slots}; booked = {}
        for other in elsewhere:
            if other.pk in selected_ids: continue
            booked.setdefault((other.teacher_id, other.weekday, other.period), other)
        conflicts = {}
        for slot in slots:
            clash = booked.get((slot.teacher_id, slot.weekday, slot.period))
            if clash is not None: conflicts[slot.pk] = clash
        return conflicts
