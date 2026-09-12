"""Data-driven academic document definitions and renderers.

This module intentionally keeps document presentation in one place. Each
report supplies structured sections/columns while the shared template owns
branding, metadata, typography, print CSS and page chrome.
"""

from dataclasses import dataclass

from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import AcademicYear, ClassSubject, SchoolClass, Section, Subject, TeacherAssignment, Timetable
from . import selectors
from .timetable_config import working_weekdays


@dataclass(frozen=True)
class DocumentDefinition:
    key: str
    title: object
    description: object
    builder: str


DOCUMENTS = {
    "class-timetable": DocumentDefinition("class-timetable", _("Class Timetable"), _("Weekly timetable for a class."), "class_timetable"),
    "section-timetable": DocumentDefinition("section-timetable", _("Section Timetable"), _("Weekly timetable for a section."), "section_timetable"),
    "teacher-timetable": DocumentDefinition("teacher-timetable", _("Teacher Timetable"), _("Weekly teaching schedule for a teacher."), "teacher_timetable"),
    "class-summary": DocumentDefinition("class-summary", _("Class Academic Summary"), _("Academic structure and teaching assignments for a class."), "class_summary"),
    "section-summary": DocumentDefinition("section-summary", _("Section Academic Summary"), _("Academic and teaching summary for a section."), "section_summary"),
    "teacher-assignments": DocumentDefinition("teacher-assignments", _("Teacher Assignment Report"), _("Teaching assignments for the selected academic year."), "teacher_assignments"),
    "academic-year-summary": DocumentDefinition("academic-year-summary", _("Academic Year Summary"), _("Academic structure for the selected year."), "academic_year_summary"),
}


def _year(request):
    qs = AcademicYear.objects.for_user(request.user, request.active_branch).order_by("-start_date")
    return qs.filter(pk=request.GET.get("academic_year")).first() or qs.filter(is_current=True).first()


def _row(label, value):
    return {"cells": [str(label), value if value not in (None, "") else "—"]}


def _table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": [{"cells": row} for row in rows]}


def _timetable_rows(slots):
    return [[slot.get_weekday_display(), f"P{slot.period}", slot.start_time.strftime("%H:%M"), slot.end_time.strftime("%H:%M"), slot.class_subject.subject.name, slot.teacher.full_name if slot.teacher else "—", slot.section.name, slot.room or "—"] for slot in slots]


def _slots(request, *, section=None, teacher=None, year=None):
    return list(selectors.slots_for(request.user, request.active_branch, academic_year=year, section=section, teacher=teacher).select_related("section__school_class", "class_subject__subject", "teacher"))


def class_timetable(request):
    year = _year(request)
    school_class = SchoolClass.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("school_class")).first()
    if not year or not school_class:
        raise Http404(_("Choose an academic year and class first."))
    slots = _slots(request, year=year).copy()
    slots = [slot for slot in slots if slot.section.school_class_id == school_class.pk]
    return _timetable_document(request, year, _("Class: %(name)s") % {"name": school_class.name}, slots, school_class=school_class)


def section_timetable(request):
    year = _year(request)
    section = Section.objects.for_user(request.user, request.active_branch).select_related("school_class", "class_teacher").filter(pk=request.GET.get("section")).first()
    if not year or not section:
        raise Http404(_("Choose an academic year and section first."))
    return _timetable_document(request, year, _("Section: %(name)s") % {"name": section}, _slots(request, year=year, section=section), section=section)


def teacher_timetable(request):
    year = _year(request)
    from apps.staff.models import Staff
    teacher = Staff.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("teacher"), staff_type="teacher").first()
    if not year or not teacher:
        raise Http404(_("Choose an academic year and teacher first."))
    return _timetable_document(request, year, _("Teacher: %(name)s") % {"name": teacher.full_name}, _slots(request, year=year, teacher=teacher), teacher=teacher)


def _timetable_document(request, year, scope, slots, **objects):
    rows = _timetable_rows(slots)
    return {
        "metadata": [_row(_("Academic year"), year.name), _row(_("Scope"), scope), _row(_("Working days"), ", ".join(str(Timetable.Weekday(d).label) for d in working_weekdays(request.active_branch)))],
        "sections": [_table(_("Weekly Schedule"), [_('Day'), _('Period'), _('Start'), _('End'), _('Subject'), _('Teacher'), _('Section'), _('Room')], rows)],
        "objects": objects,
    }


def class_summary(request):
    year = _year(request)
    klass = SchoolClass.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("school_class")).first()
    if not year or not klass:
        raise Http404(_("Choose an academic year and class first."))
    sections = list(klass.sections.filter(is_active=True).order_by("name"))
    subjects = list(klass.class_subjects.filter(academic_year=year, is_active=True).select_related("subject"))
    assignments = list(TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, class_subject__school_class=klass, is_active=True).select_related("teacher", "class_subject__subject", "section"))
    return {"metadata": [_row(_("Academic year"), year.name), _row(_("Class"), klass.name), _row(_("Sections"), len(sections))], "sections": [_table(_("Sections"), [_('Section'), _('Capacity'), _('Class Teacher')], [[s.name, s.capacity or "—", s.class_teacher.full_name if s.class_teacher else "—"] for s in sections]), _table(_("Class Subjects"), [_('Subject'), _('Weekly Periods')], [[cs.subject.name, cs.weekly_periods] for cs in subjects]), _table(_("Subject Teachers"), [_('Teacher'), _('Subject'), _('Section')], [[a.teacher.full_name, a.class_subject.subject.name, a.section.name if a.section else _('All sections')] for a in assignments])]}


def section_summary(request):
    year = _year(request)
    section = Section.objects.for_user(request.user, request.active_branch).select_related("school_class", "class_teacher").filter(pk=request.GET.get("section")).first()
    if not year or not section:
        raise Http404(_("Choose an academic year and section first."))
    assignments = TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, section=section, is_active=True).select_related("teacher", "class_subject__subject")
    slots = _slots(request, year=year, section=section)
    return {"metadata": [_row(_("Academic year"), year.name), _row(_("Class"), section.school_class.name), _row(_("Section"), section.name), _row(_("Class teacher"), section.class_teacher.full_name if section.class_teacher else "—")], "sections": [_table(_("Subject Teachers"), [_('Teacher'), _('Subject')], [[a.teacher.full_name, a.class_subject.subject.name] for a in assignments]), _table(_("Timetable"), [_('Day'), _('Period'), _('Subject'), _('Teacher'), _('Room')], [[s.get_weekday_display(), f"P{s.period}", s.class_subject.subject.name, s.teacher.full_name if s.teacher else "—", s.room or "—"] for s in slots])]}


def teacher_assignments(request):
    year = _year(request)
    if not year:
        raise Http404(_("Choose an academic year first."))
    qs = TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, is_active=True).select_related("teacher", "class_subject__subject", "class_subject__school_class", "section").order_by("teacher__full_name", "class_subject__school_class__level", "class_subject__subject__name")
    teacher_id = request.GET.get("teacher")
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)
    return {"metadata": [_row(_("Academic year"), year.name), _row(_("Assignments"), qs.count())], "sections": [_table(_("Teacher Assignments"), [_('Teacher'), _('Class'), _('Section'), _('Subject'), _('Scope')], [[a.teacher.full_name, a.class_subject.school_class.name, a.section.name if a.section else "—", a.class_subject.subject.name, a.assignment_scope] for a in qs])]}


def academic_year_summary(request):
    year = _year(request)
    if not year:
        raise Http404(_("Choose an academic year first."))
    user, branch = request.user, request.active_branch
    classes = list(SchoolClass.objects.for_user(user, branch).filter(is_active=True).order_by("level", "name"))
    terms = list(year.terms.order_by("sequence"))
    subjects = list(ClassSubject.objects.for_user(user, branch).filter(academic_year=year, is_active=True).select_related("school_class", "subject"))
    assignments = list(TeacherAssignment.objects.for_user(user, branch).filter(academic_year=year, is_active=True).select_related("teacher", "class_subject__school_class", "class_subject__subject", "section"))
    return {"metadata": [_row(_("Academic year"), year.name), _row(_("Dates"), f"{year.start_date:%d %b %Y} — {year.end_date:%d %b %Y}"), _row(_("Terms"), len(terms)), _row(_("Classes"), len(classes))], "sections": [_table(_("Terms"), [_('Term'), _('Start'), _('End')], [[t.name, t.start_date, t.end_date] for t in terms]), _table(_("Classes"), [_('Class'), _('Sections')], [[c.name, c.section_count] for c in classes]), _table(_("Class Subjects"), [_('Class'), _('Subject'), _('Weekly Periods')], [[cs.school_class.name, cs.subject.name, cs.weekly_periods] for cs in subjects]), _table(_("Teacher Assignments"), [_('Teacher'), _('Class'), _('Subject'), _('Section')], [[a.teacher.full_name, a.class_subject.school_class.name, a.class_subject.subject.name, a.section.name if a.section else _('All sections')] for a in assignments])]}


BUILDERS = {name: globals()[definition.builder] for name, definition in DOCUMENTS.items()}


def render_document(request, key):
    definition = DOCUMENTS.get(key)
    if definition is None:
        raise Http404(_("Document not found."))
    data = BUILDERS[key](request)
    return {"definition": definition, "document": data}
