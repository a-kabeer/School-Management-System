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


class AcademicYearListView(TenantListView):
    model = AcademicYear
    required_permission = ACADEMICS
    create_permission = "academics.add_academicyear"
    page_title = _("Academic Years")
    ordering = ["-start_date"]
    create_url_name = "academics:year_create"
    update_url_name = "academics:year_update"
    delete_url_name = "academics:year_delete"
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


class TermListView(TenantListView):
    model = Term
    required_permission = ACADEMICS
    create_permission = "academics.add_term"
    page_title = _("Terms")
    select_related = ("academic_year",)
    ordering = ["-academic_year__start_date", "sequence"]
    create_url_name = "academics:term_create"
    update_url_name = "academics:term_update"
    delete_url_name = "academics:term_delete"
    filter_spec = FilterSpec(search_fields=("name", "academic_year__name"))
    table_columns = (
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Term"), "field": "name"},
        {"label": _("Sequence"), "field": "sequence"},
        {"label": _("Start"), "field": "start_date", "type": "date"},
        {"label": _("End"), "field": "end_date", "type": "date"},
        {"label": _("Current"), "field": "is_current", "type": "bool"},
    )


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


class SchoolClassListView(TenantListView):
    model = SchoolClass
    required_permission = ACADEMICS
    create_permission = "academics.add_schoolclass"
    page_title = _("Classes")
    ordering = ["level", "name"]
    create_url_name = "academics:class_create"
    update_url_name = "academics:class_update"
    delete_url_name = "academics:class_delete"
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


class SectionListView(TenantListView):
    model = Section
    required_permission = ACADEMICS
    create_permission = "academics.add_section"
    page_title = _("Sections")
    select_related = ("school_class", "class_teacher")
    ordering = ["school_class__level", "name"]
    create_url_name = "academics:section_create"
    update_url_name = "academics:section_update"
    delete_url_name = "academics:section_delete"
    filter_spec = FilterSpec(search_fields=("name", "school_class__name"))
    table_columns = (
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Section"), "field": "name"},
        {"label": _("Capacity"), "field": "capacity"},
        {"label": _("Class Teacher"), "field": "class_teacher.full_name"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


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


class SubjectListView(TenantListView):
    model = Subject
    required_permission = ACADEMICS
    create_permission = "academics.add_subject"
    page_title = _("Subjects")
    ordering = ["name"]
    create_url_name = "academics:subject_create"
    update_url_name = "academics:subject_update"
    delete_url_name = "academics:subject_delete"
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


class ClassSubjectListView(TenantListView):
    model = ClassSubject
    required_permission = ACADEMICS
    create_permission = "academics.add_classsubject"
    page_title = _("Class Subjects")
    select_related = ("academic_year", "school_class", "subject")
    ordering = ["school_class__level", "subject__name"]
    create_url_name = "academics:classsubject_create"
    update_url_name = "academics:classsubject_update"
    delete_url_name = "academics:classsubject_delete"
    filter_spec = FilterSpec(search_fields=("school_class__name", "subject__name"))
    table_columns = (
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Subject"), "field": "subject.name"},
        {"label": _("Weekly Periods"), "field": "weekly_periods"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


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


class TeacherAssignmentListView(TenantListView):
    model = TeacherAssignment
    required_permission = ACADEMICS
    create_permission = "academics.add_teacherassignment"
    page_title = _("Teacher Assignments")
    select_related = (
        "teacher",
        "class_subject__subject",
        "class_subject__school_class",
        "section",
    )
    ordering = ["teacher__full_name"]
    create_url_name = "academics:assignment_create"
    update_url_name = "academics:assignment_update"
    delete_url_name = "academics:assignment_delete"
    filter_spec = FilterSpec(
        search_fields=("teacher__full_name", "class_subject__subject__name")
    )
    table_columns = (
        {"label": _("Teacher"), "field": "teacher.full_name"},
        {"label": _("Class"), "field": "class_subject.school_class.name"},
        {"label": _("Subject"), "field": "class_subject.subject.name"},
        {"label": _("Section"), "field": "section.name"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


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


class TimetableListView(TenantListView):
    model = Timetable
    required_permission = ACADEMICS
    create_permission = "academics.add_timetable"
    page_title = _("Timetable")
    select_related = (
        "section__school_class",
        "class_subject__subject",
        "teacher",
    )
    ordering = ["weekday", "period"]
    create_url_name = "academics:timetable_create"
    update_url_name = "academics:timetable_update"
    delete_url_name = "academics:timetable_delete"
    filter_spec = FilterSpec(
        search_fields=("section__name", "class_subject__subject__name", "room"),
        choices={"weekday": "weekday"},
        selects={
            "weekday": {"label": _("Weekday"), "options": Timetable.Weekday.choices}
        },
    )
    table_columns = (
        {"label": _("Day"), "field": "weekday", "type": "choice"},
        {"label": _("Period"), "field": "period"},
        {"label": _("Section"), "field": "section"},
        {"label": _("Subject"), "field": "class_subject.subject.name"},
        {"label": _("Teacher"), "field": "teacher.full_name"},
        {"label": _("Time"), "field": "start_time", "type": "time"},
        {"label": _("Room"), "field": "room"},
    )


class TimetableCreateView(TenantCreateView):
    model = Timetable
    form_class = TimetableForm
    required_permission = "academics.add_timetable"
    success_url = reverse_lazy("academics:timetable_list")
    page_title = _("New Timetable Slot")


class TimetableUpdateView(TenantUpdateView):
    model = Timetable
    form_class = TimetableForm
    required_permission = "academics.change_timetable"
    success_url = reverse_lazy("academics:timetable_list")
    page_title = _("Edit Timetable Slot")


class TimetableDeleteView(TenantDeleteView):
    model = Timetable
    required_permission = "academics.delete_timetable"
    success_url = reverse_lazy("academics:timetable_list")
    page_title = _("Delete Timetable Slot")
