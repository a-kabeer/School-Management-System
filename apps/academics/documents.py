"""Data-driven academic document definitions and renderers."""

from dataclasses import dataclass

from django.http import Http404
from django.utils.translation import gettext_lazy as _

from . import selectors
from .models import AcademicYear, ClassSubject, SchoolClass, Section, TeacherAssignment, Timetable
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


def _slots(request, *, section=None, teacher=None, year=None):
    return list(selectors.slots_for(request.user, request.active_branch, academic_year=year, section=section, teacher=teacher).select_related("section__school_class", "class_subject__subject", "teacher"))


def _timetable_rows(slots, weekdays, include_section=False):
    periods = {}
    for slot in slots:
        periods.setdefault(slot.period, {"period": slot.period, "start": slot.start_time, "end": slot.end_time, "days": {}})
        periods[slot.period]["days"][slot.weekday] = {
            "subject": slot.class_subject.subject.name,
            "teacher": slot.teacher.full_name if slot.teacher else "",
            "room": slot.room or "",
            "class_section": (
                f"{slot.section.school_class.name} / {slot.section.name}"
                if include_section and slot.section_id
                else ""
            ),
        }
    rows = []
    for period in sorted(periods):
        item = periods[period]
        rows.append({"period": item["period"], "start": item["start"], "end": item["end"], "days": [item["days"].get(day, {}) for day in weekdays]})
    return rows


def _timetable_document(request, year, slots, **objects):
    weekdays = list(working_weekdays(request.active_branch))
    metadata = [_row(_("Academic Year"), year.name)]
    if objects.get("school_class"):
        metadata.append(_row(_("Class"), objects["school_class"].name))
    if objects.get("section"):
        section = objects["section"]
        metadata.append(_row(_("Section"), section.name))
        if section.class_teacher:
            metadata.append(_row(_("Class Teacher"), section.class_teacher.full_name))
    if objects.get("teacher"):
        metadata.append(_row(_("Teacher"), objects["teacher"].full_name))
    metadata.append(_row(_("Working Days"), [Timetable.Weekday(day).label for day in weekdays]))
    metadata.append(_row(_("Effective From"), year.start_date))
    return {
        "metadata": metadata,
        "document_layout": "timetable",
        "sections": [{
            "title": _("Weekly Timetable"),
            "timetable": True,
            "weekdays": [{"value": day, "label": Timetable.Weekday(day).label} for day in weekdays],
            "rows": _timetable_rows(
                slots,
                weekdays,
                include_section=bool(objects.get("teacher") or (objects.get("school_class") and not objects.get("section"))),
            ),
        }],
        "objects": objects,
    }


def class_timetable(request):
    year = _year(request)
    school_class = SchoolClass.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("school_class")).first()
    if not year or not school_class:
        raise Http404(_("Choose an academic year and class first."))
    slots = [slot for slot in _slots(request, year=year) if slot.section.school_class_id == school_class.pk]
    return _timetable_document(request, year, slots, school_class=school_class)


def section_timetable(request):
    year = _year(request)
    section = Section.objects.for_user(request.user, request.active_branch).select_related("school_class", "class_teacher").filter(pk=request.GET.get("section")).first()
    if not year or not section:
        raise Http404(_("Choose an academic year and section first."))
    return _timetable_document(request, year, _slots(request, year=year, section=section), school_class=section.school_class, section=section)


def teacher_timetable(request):
    year = _year(request)
    from apps.staff.models import Staff
    teacher = Staff.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("teacher"), staff_type="teacher").first()
    if not year or not teacher:
        raise Http404(_("Choose an academic year and teacher first."))
    return _timetable_document(request, year, _slots(request, year=year, teacher=teacher), teacher=teacher)


def class_summary(request):
    year = _year(request)
    klass = SchoolClass.objects.for_user(request.user, request.active_branch).filter(pk=request.GET.get("school_class")).first()
    if not year or not klass:
        raise Http404(_("Choose an academic year and class first."))
    sections = list(klass.sections.filter(is_active=True).select_related("class_teacher").order_by("name"))
    subjects = list(klass.class_subjects.filter(academic_year=year, is_active=True).select_related("subject"))
    assignments = list(TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, class_subject__school_class=klass, is_active=True).select_related("teacher", "class_subject__subject", "section"))
    return {"metadata": [_row(_("Academic Year"), year.name), _row(_("Class"), klass.name)], "sections": [_table(_("Sections"), [_('Section'), _('Capacity'), _('Class Teacher')], [[s.name, s.capacity or "—", s.class_teacher.full_name if s.class_teacher else "—"] for s in sections]), _table(_("Class Subjects"), [_('Subject'), _('Weekly Periods')], [[cs.subject.name, cs.weekly_periods] for cs in subjects]), _table(_("Subject Teachers"), [_('Teacher'), _('Subject'), _('Section')], [[a.teacher.full_name, a.class_subject.subject.name, a.section.name if a.section else _('All sections')] for a in assignments])]}


def section_summary(request):
    year = _year(request)
    section = Section.objects.for_user(request.user, request.active_branch).select_related("school_class", "class_teacher").filter(pk=request.GET.get("section")).first()
    if not year or not section:
        raise Http404(_("Choose an academic year and section first."))
    assignments = TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, section=section, is_active=True).select_related("teacher", "class_subject__subject")
    slots = _slots(request, year=year, section=section)
    return {"metadata": [_row(_("Academic Year"), year.name), _row(_("Class"), section.school_class.name), _row(_("Section"), section.name)], "sections": [_table(_("Subject Teachers"), [_('Teacher'), _('Subject')], [[a.teacher.full_name, a.class_subject.subject.name] for a in assignments]), _table(_("Timetable"), [_('Day'), _('Period'), _('Subject'), _('Teacher'), _('Room')], [[s.get_weekday_display(), f"P{s.period}", s.class_subject.subject.name, s.teacher.full_name if s.teacher else "—", s.room or "—"] for s in slots])]}


def teacher_assignments(request):
    year = _year(request)
    if not year:
        raise Http404(_("Choose an academic year first."))
    qs = TeacherAssignment.objects.for_user(request.user, request.active_branch).filter(academic_year=year, is_active=True).select_related("teacher", "class_subject__subject", "class_subject__school_class", "section").order_by("teacher__full_name", "class_subject__school_class__level", "class_subject__subject__name")
    teacher_id = request.GET.get("teacher")
    if teacher_id:
        qs = qs.filter(teacher_id=teacher_id)
    metadata = [_row(_("Academic Year"), year.name)]
    if teacher_id:
        assignment = qs.first()
        if assignment:
            metadata.append(_row(_("Teacher"), assignment.teacher.full_name))
    return {"metadata": metadata, "sections": [_table(_("Teacher Assignments"), [_('Teacher'), _('Class'), _('Section'), _('Subject'), _('Scope')], [[a.teacher.full_name, a.class_subject.school_class.name, a.section.name if a.section else "—", a.class_subject.subject.name, a.assignment_scope] for a in qs])]}


def academic_year_summary(request):
    year = _year(request)
    if not year:
        raise Http404(_("Choose an academic year first."))
    user, branch = request.user, request.active_branch
    classes = list(SchoolClass.objects.for_user(user, branch).filter(is_active=True).order_by("level", "name"))
    terms = list(year.terms.order_by("sequence"))
    subjects = list(ClassSubject.objects.for_user(user, branch).filter(academic_year=year, is_active=True).select_related("school_class", "subject"))
    assignments = list(TeacherAssignment.objects.for_user(user, branch).filter(academic_year=year, is_active=True).select_related("teacher", "class_subject__school_class", "class_subject__subject", "section"))
    return {"metadata": [_row(_("Academic Year"), year.name)], "sections": [_table(_("Terms"), [_('Term'), _('Start'), _('End')], [[t.name, t.start_date, t.end_date] for t in terms]), _table(_("Classes"), [_('Class'), _('Sections')], [[c.name, c.section_count] for c in classes]), _table(_("Class Subjects"), [_('Class'), _('Subject'), _('Weekly Periods')], [[cs.school_class.name, cs.subject.name, cs.weekly_periods] for cs in subjects]), _table(_("Teacher Assignments"), [_('Teacher'), _('Class'), _('Subject'), _('Section')], [[a.teacher.full_name, a.class_subject.school_class.name, a.class_subject.subject.name, a.section.name if a.section else _('All sections')] for a in assignments])]}


BUILDERS = {name: globals()[definition.builder] for name, definition in DOCUMENTS.items()}


def render_document(request, key):
    definition = DOCUMENTS.get(key)
    if definition is None:
        raise Http404(_("Document not found."))
    return {"definition": definition, "document": BUILDERS[key](request)}
