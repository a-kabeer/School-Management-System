"""Academics lists and forms.

The lists are the one place each kind of record is listed. A View screen that
wants to show "the sections of this class" links here with a filter rather
than growing a list of its own, which is why every list below can be narrowed
by the records above it in the hierarchy:

    Academic Year -> Terms -> Classes -> Sections -> Subjects
                  -> Teacher Assignments -> Timetable
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    TenantCreateView,
    TenantDeleteView,
    TenantListView,
    TenantUpdateView,
)

from .forms import (
    AcademicYearForm,
    ClassSubjectForm,
    SchoolClassForm,
    SectionForm,
    SubjectForm,
    TeacherAssignmentForm,
    TermForm,
    TimetableForm,
)
from .models import (
    AcademicYear,
    ClassSubject,
    SchoolClass,
    Section,
    Subject,
    TeacherAssignment,
    Term,
    Timetable,
)

ACADEMICS = "core.access_academics"


def record_select(request, param, label, queryset, labeller=str):
    """A filter dropdown listing records rather than fixed choices.

    Built per request because the options are rows: this branch's years, its
    classes, its teachers.
    """
    return {
        "param": param,
        "label": label,
        "options": [(str(obj.pk), labeller(obj)) for obj in queryset],
        "value": request.GET.get(param, ""),
    }


class ContextFilterMixin:
    """Adds record-backed filter dropdowns to a list.

    These are what make a View screen's "View sections" land on the sections
    of *that* class: the link carries the filter, and the list applies it with
    its search, sorting and paging untouched.
    """

    def record_filters(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_selects"] = list(context.get("filter_selects", ())) + list(
            self.record_filters()
        )
        return context

    def years(self):
        return AcademicYear.objects.for_user(
            self.request.user, self.active_branch
        ).order_by("-start_date")

    def classes(self):
        return (
            SchoolClass.objects.for_user(self.request.user, self.active_branch)
            .filter(is_active=True)
            .order_by("level", "name")
        )

    def sections(self):
        return (
            Section.objects.for_user(self.request.user, self.active_branch)
            .filter(is_active=True)
            .select_related("school_class")
            .order_by("school_class__level", "name")
        )

    def subjects(self):
        return (
            Subject.objects.for_user(self.request.user, self.active_branch)
            .filter(is_active=True)
            .order_by("name")
        )

    def teachers(self):
        from apps.staff.models import Staff

        return (
            Staff.objects.for_user(self.request.user, self.active_branch)
            .filter(staff_type="teacher", status="active")
            .order_by("full_name")
        )


# --------------------------------------------------------------------------
# Academic years
# --------------------------------------------------------------------------
class AcademicYearListView(TenantListView):
    model = AcademicYear
    required_permission = ACADEMICS
    create_permission = "academics.add_academicyear"
    page_title = _("Academic Years")
    page_subtitle = _("The years everything else is organised under.")
    ordering = ["-start_date"]
    create_url_name = "academics:year_create"
    detail_url_name = "academics:year_detail"
    update_url_name = "academics:year_update"
    delete_url_name = "academics:year_delete"
    empty_message = _("No academic years yet")
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Start"), "field": "start_date", "type": "date"},
        {"label": _("End"), "field": "end_date", "type": "date"},
        {"label": _("Current"), "field": "is_current", "type": "bool"},
        {"label": _("Closed"), "field": "is_closed", "type": "bool"},
    )


class AcademicYearCreateView(TenantCreateView):
    model = AcademicYear
    form_class = AcademicYearForm
    required_permission = "academics.add_academicyear"
    success_url = reverse_lazy("academics:year_list")
    page_title = _("New Academic Year")


class AcademicYearUpdateView(TenantUpdateView):
    model = AcademicYear
    form_class = AcademicYearForm
    required_permission = "academics.change_academicyear"
    success_url = reverse_lazy("academics:year_list")
    page_title = _("Edit Academic Year")


class AcademicYearDeleteView(TenantDeleteView):
    model = AcademicYear
    required_permission = "academics.delete_academicyear"
    success_url = reverse_lazy("academics:year_list")
    page_title = _("Delete Academic Year")
    dependants = (
        ("terms", _("terms")),
        ("class_subjects", _("class subjects")),
        ("teacher_assignments", _("teacher assignments")),
        ("timetable_slots", _("timetable slots")),
        ("enrollments", _("enrollments")),
    )


# --------------------------------------------------------------------------
# Terms
# --------------------------------------------------------------------------
class TermListView(ContextFilterMixin, TenantListView):
    model = Term
    required_permission = ACADEMICS
    create_permission = "academics.add_term"
    page_title = _("Terms")
    page_subtitle = _("The periods each academic year is divided into.")
    select_related = ("academic_year",)
    ordering = ["-academic_year__start_date", "sequence"]
    create_url_name = "academics:term_create"
    detail_url_name = "academics:term_detail"
    update_url_name = "academics:term_update"
    delete_url_name = "academics:term_delete"
    empty_message = _("No terms yet")
    filter_spec = FilterSpec(
        search_fields=("name", "academic_year__name"),
        choices={"academic_year": "academic_year_id"},
    )
    table_columns = (
        {"label": _("Term"), "field": "name"},
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Sequence"), "field": "sequence"},
        {"label": _("Start"), "field": "start_date", "type": "date"},
        {"label": _("End"), "field": "end_date", "type": "date"},
        {"label": _("Current"), "field": "is_current", "type": "bool"},
    )

    def record_filters(self):
        return [
            record_select(
                self.request, "academic_year", _("Academic year"), self.years()
            )
        ]


class TermCreateView(TenantCreateView):
    model = Term
    form_class = TermForm
    required_permission = "academics.add_term"
    success_url = reverse_lazy("academics:term_list")
    page_title = _("New Term")


class TermUpdateView(TenantUpdateView):
    model = Term
    form_class = TermForm
    required_permission = "academics.change_term"
    success_url = reverse_lazy("academics:term_list")
    page_title = _("Edit Term")


class TermDeleteView(TenantDeleteView):
    model = Term
    required_permission = "academics.delete_term"
    success_url = reverse_lazy("academics:term_list")
    page_title = _("Delete Term")


# --------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------
class SchoolClassListView(TenantListView):
    model = SchoolClass
    required_permission = ACADEMICS
    create_permission = "academics.add_schoolclass"
    page_title = _("Classes")
    page_subtitle = _("Each grade taught at this branch.")
    ordering = ["level", "name"]
    create_url_name = "academics:class_create"
    detail_url_name = "academics:class_detail"
    update_url_name = "academics:class_update"
    delete_url_name = "academics:class_delete"
    empty_message = _("No classes yet")
    filter_spec = FilterSpec(search_fields=("name", "code"))
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Code"), "field": "code"},
        {"label": _("Level"), "field": "level"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class SchoolClassCreateView(TenantCreateView):
    model = SchoolClass
    form_class = SchoolClassForm
    required_permission = "academics.add_schoolclass"
    success_url = reverse_lazy("academics:class_list")
    page_title = _("New Class")


class SchoolClassUpdateView(TenantUpdateView):
    model = SchoolClass
    form_class = SchoolClassForm
    required_permission = "academics.change_schoolclass"
    success_url = reverse_lazy("academics:class_list")
    page_title = _("Edit Class")


class SchoolClassDeleteView(TenantDeleteView):
    model = SchoolClass
    required_permission = "academics.delete_schoolclass"
    success_url = reverse_lazy("academics:class_list")
    page_title = _("Delete Class")
    dependants = (
        ("sections", _("sections")),
        ("class_subjects", _("class subjects")),
        ("enrollments", _("enrollments")),
    )


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------
class SectionListView(ContextFilterMixin, TenantListView):
    model = Section
    required_permission = ACADEMICS
    create_permission = "academics.add_section"
    page_title = _("Sections")
    page_subtitle = _("The groups each class is split into.")
    select_related = ("school_class", "class_teacher")
    ordering = ["school_class__level", "name"]
    create_url_name = "academics:section_create"
    detail_url_name = "academics:section_detail"
    update_url_name = "academics:section_update"
    delete_url_name = "academics:section_delete"
    empty_message = _("No sections yet")
    filter_spec = FilterSpec(
        search_fields=("name", "school_class__name"),
        choices={"school_class": "school_class_id", "class_teacher": "class_teacher_id"},
    )
    table_columns = (
        {"label": _("Section"), "field": "name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Capacity"), "field": "capacity"},
        {"label": _("Class Teacher"), "field": "class_teacher.full_name"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )

    def record_filters(self):
        return [
            record_select(self.request, "school_class", _("Class"), self.classes()),
            record_select(
                self.request,
                "class_teacher",
                _("Class teacher"),
                self.teachers(),
                lambda staff: staff.full_name,
            ),
        ]


class SectionCreateView(TenantCreateView):
    model = Section
    form_class = SectionForm
    required_permission = "academics.add_section"
    success_url = reverse_lazy("academics:section_list")
    page_title = _("New Section")


class SectionUpdateView(TenantUpdateView):
    model = Section
    form_class = SectionForm
    required_permission = "academics.change_section"
    success_url = reverse_lazy("academics:section_list")
    page_title = _("Edit Section")


class SectionDeleteView(TenantDeleteView):
    model = Section
    required_permission = "academics.delete_section"
    success_url = reverse_lazy("academics:section_list")
    page_title = _("Delete Section")
    dependants = (
        ("enrollments", _("enrollments")),
        ("teacher_assignments", _("teacher assignments")),
        ("timetable_slots", _("timetable slots")),
    )


# --------------------------------------------------------------------------
# Subjects
# --------------------------------------------------------------------------
class SubjectListView(TenantListView):
    model = Subject
    required_permission = ACADEMICS
    create_permission = "academics.add_subject"
    page_title = _("Subjects")
    page_subtitle = _("Everything that can be taught here.")
    ordering = ["name"]
    create_url_name = "academics:subject_create"
    detail_url_name = "academics:subject_detail"
    update_url_name = "academics:subject_update"
    delete_url_name = "academics:subject_delete"
    empty_message = _("No subjects yet")
    filter_spec = FilterSpec(
        search_fields=("name", "code"),
        choices={"kind": "kind"},
        selects={"kind": {"label": _("Kind"), "options": Subject.Kind.choices}},
    )
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Code"), "field": "code"},
        {"label": _("Kind"), "field": "kind", "type": "choice"},
        {"label": _("Elective"), "field": "is_elective", "type": "bool"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class SubjectCreateView(TenantCreateView):
    model = Subject
    form_class = SubjectForm
    required_permission = "academics.add_subject"
    success_url = reverse_lazy("academics:subject_list")
    page_title = _("New Subject")


class SubjectUpdateView(TenantUpdateView):
    model = Subject
    form_class = SubjectForm
    required_permission = "academics.change_subject"
    success_url = reverse_lazy("academics:subject_list")
    page_title = _("Edit Subject")


class SubjectDeleteView(TenantDeleteView):
    model = Subject
    required_permission = "academics.delete_subject"
    success_url = reverse_lazy("academics:subject_list")
    page_title = _("Delete Subject")
    dependants = (("class_subjects", _("class subjects")),)


# --------------------------------------------------------------------------
# Class subjects
# --------------------------------------------------------------------------
class ClassSubjectListView(ContextFilterMixin, TenantListView):
    model = ClassSubject
    required_permission = ACADEMICS
    create_permission = "academics.add_classsubject"
    page_title = _("Class Subjects")
    page_subtitle = _("What each class studies, in which year.")
    select_related = ("academic_year", "school_class", "subject")
    ordering = ["school_class__level", "subject__name"]
    create_url_name = "academics:classsubject_create"
    detail_url_name = "academics:classsubject_detail"
    update_url_name = "academics:classsubject_update"
    delete_url_name = "academics:classsubject_delete"
    empty_message = _("No class subjects yet")
    filter_spec = FilterSpec(
        search_fields=("school_class__name", "subject__name"),
        choices={
            "academic_year": "academic_year_id",
            "school_class": "school_class_id",
            "subject": "subject_id",
        },
    )
    table_columns = (
        {"label": _("Subject"), "field": "subject.name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Weekly Periods"), "field": "weekly_periods"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )

    def record_filters(self):
        return [
            record_select(
                self.request, "academic_year", _("Academic year"), self.years()
            ),
            record_select(self.request, "school_class", _("Class"), self.classes()),
            record_select(self.request, "subject", _("Subject"), self.subjects()),
        ]


class ClassSubjectCreateView(TenantCreateView):
    model = ClassSubject
    form_class = ClassSubjectForm
    required_permission = "academics.add_classsubject"
    success_url = reverse_lazy("academics:classsubject_list")
    page_title = _("New Class Subject")


class ClassSubjectUpdateView(TenantUpdateView):
    model = ClassSubject
    form_class = ClassSubjectForm
    required_permission = "academics.change_classsubject"
    success_url = reverse_lazy("academics:classsubject_list")
    page_title = _("Edit Class Subject")


class ClassSubjectDeleteView(TenantDeleteView):
    model = ClassSubject
    required_permission = "academics.delete_classsubject"
    success_url = reverse_lazy("academics:classsubject_list")
    page_title = _("Delete Class Subject")
    dependants = (
        ("teacher_assignments", _("teacher assignments")),
        ("timetable_slots", _("timetable slots")),
    )


# --------------------------------------------------------------------------
# Teacher assignments
# --------------------------------------------------------------------------
class TeacherAssignmentListView(ContextFilterMixin, TenantListView):
    model = TeacherAssignment
    required_permission = ACADEMICS
    create_permission = "academics.add_teacherassignment"
    page_title = _("Teacher Assignments")
    page_subtitle = _("Who teaches which subject, to which class.")
    select_related = (
        "teacher",
        "academic_year",
        "class_subject__subject",
        "class_subject__school_class",
        "section",
    )
    ordering = ["teacher__full_name"]
    create_url_name = "academics:assignment_create"
    detail_url_name = "academics:assignment_detail"
    update_url_name = "academics:assignment_update"
    delete_url_name = "academics:assignment_delete"
    empty_message = _("Nobody is assigned to teach yet")
    filter_spec = FilterSpec(
        search_fields=("teacher__full_name", "class_subject__subject__name"),
        choices={
            "academic_year": "academic_year_id",
            "teacher": "teacher_id",
            "school_class": "class_subject__school_class_id",
            "subject": "class_subject__subject_id",
            "class_subject": "class_subject_id",
            "section": "section_id",
        },
    )
    table_columns = (
        {"label": _("Teacher"), "field": "teacher.full_name"},
        {"label": _("Subject"), "field": "class_subject.subject.name"},
        {"label": _("Class"), "field": "class_subject.school_class.name"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )

    def record_filters(self):
        return [
            record_select(
                self.request, "academic_year", _("Academic year"), self.years()
            ),
            record_select(
                self.request,
                "teacher",
                _("Teacher"),
                self.teachers(),
                lambda staff: staff.full_name,
            ),
            record_select(self.request, "school_class", _("Class"), self.classes()),
            record_select(self.request, "subject", _("Subject"), self.subjects()),
        ]


class TeacherAssignmentCreateView(TenantCreateView):
    model = TeacherAssignment
    form_class = TeacherAssignmentForm
    required_permission = "academics.add_teacherassignment"
    success_url = reverse_lazy("academics:assignment_list")
    page_title = _("New Teacher Assignment")


class TeacherAssignmentUpdateView(TenantUpdateView):
    model = TeacherAssignment
    form_class = TeacherAssignmentForm
    required_permission = "academics.change_teacherassignment"
    success_url = reverse_lazy("academics:assignment_list")
    page_title = _("Edit Teacher Assignment")


class TeacherAssignmentDeleteView(TenantDeleteView):
    model = TeacherAssignment
    required_permission = "academics.delete_teacherassignment"
    success_url = reverse_lazy("academics:assignment_list")
    page_title = _("Delete Teacher Assignment")


# --------------------------------------------------------------------------
# Timetable
# --------------------------------------------------------------------------
class TimetableListView(ContextFilterMixin, TenantListView):
    model = Timetable
    required_permission = ACADEMICS
    create_permission = "academics.add_timetable"
    page_title = _("Timetable Slots")
    page_subtitle = _("Every scheduled lesson, searchable.")
    select_related = (
        "academic_year",
        "section__school_class",
        "class_subject__subject",
        "teacher",
    )
    ordering = ["weekday", "period"]
    create_url_name = "academics:timetable_create"
    detail_url_name = "academics:timetable_detail"
    update_url_name = "academics:timetable_update"
    delete_url_name = "academics:timetable_delete"
    empty_message = _("Nothing scheduled yet")
    filter_spec = FilterSpec(
        search_fields=("section__name", "class_subject__subject__name", "room"),
        choices={
            "weekday": "weekday",
            "academic_year": "academic_year_id",
            "section": "section_id",
            "school_class": "section__school_class_id",
            "teacher": "teacher_id",
            "class_subject": "class_subject_id",
        },
        selects={
            "weekday": {"label": _("Weekday"), "options": Timetable.Weekday.choices}
        },
    )
    table_columns = (
        {"label": _("Day"), "field": "weekday", "type": "choice"},
        {"label": _("Period"), "field": "period"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Class"), "field": "section.school_class.name"},
        {"label": _("Subject"), "field": "class_subject.subject.name"},
        {"label": _("Teacher"), "field": "teacher.full_name"},
        {"label": _("Time"), "field": "start_time", "type": "time"},
        {"label": _("Room"), "field": "room"},
    )

    def record_filters(self):
        return [
            record_select(
                self.request, "academic_year", _("Academic year"), self.years()
            ),
            record_select(self.request, "school_class", _("Class"), self.classes()),
            record_select(self.request, "section", _("Section"), self.sections()),
            record_select(
                self.request,
                "teacher",
                _("Teacher"),
                self.teachers(),
                lambda staff: staff.full_name,
            ),
        ]


class TimetableCreateView(TenantCreateView):
    model = Timetable
    form_class = TimetableForm
    required_permission = "academics.add_timetable"
    success_url = reverse_lazy("academics:timetable")
    page_title = _("New Timetable Slot")


class TimetableUpdateView(TenantUpdateView):
    model = Timetable
    form_class = TimetableForm
    required_permission = "academics.change_timetable"
    success_url = reverse_lazy("academics:timetable")
    page_title = _("Edit Timetable Slot")


class TimetableDeleteView(TenantDeleteView):
    model = Timetable
    required_permission = "academics.delete_timetable"
    success_url = reverse_lazy("academics:timetable")
    page_title = _("Delete Timetable Slot")
