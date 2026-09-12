"""The View screens for Academics.

Each one answers three questions in order: what is this record, what state is
it in, and what hangs off it that the reader is probably on their way to. The
related blocks are links into the existing lists — already filtered to this
record — rather than new screens, so search, sorting and paging keep working
and there is one list per thing, not two.
"""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.detail import active_badge, badge, cell, meta, related_card, row, tab
from apps.core.mixins import TenantDetailView

from . import selectors
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
#: How many related records a View shows before sending the reader to the list.
PREVIEW = 8


class AcademicsDetailView(TenantDetailView):
    """Shared plumbing for the Academics View screens."""

    required_permission = ACADEMICS
    template_name = None
    back_url_name = None
    back_label = None

    def preview(self, queryset):
        """A short preview plus the real total, so nothing is silently cut."""
        return list(queryset[:PREVIEW]), queryset.count()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["detail_timestamps"] = True
        if self.back_url_name:
            context["back_url"] = reverse(self.back_url_name)
            context["back_label"] = self.back_label
        context.update(self.get_detail_context())
        return context

    def get_detail_context(self):
        return {}


# --------------------------------------------------------------------------
# Academic year
# --------------------------------------------------------------------------
class AcademicYearDetailView(AcademicsDetailView):
    model = AcademicYear
    template_name = "academics/year_detail.html"
    back_url_name = "academics:year_list"
    back_label = _("Back to academic years")
    page_title = _("Academic Year")

    def get_detail_context(self):
        user, branch, year = self.request.user, self.active_branch, self.object

        terms, term_count = self.preview(selectors.year_terms(user, branch, year))
        subjects, subject_count = self.preview(
            selectors.class_subjects_for(user, branch, year=year)
        )
        assignments, assignment_count = self.preview(
            selectors.assignments_for(user, branch, academic_year=year)
        )
        slot_count = selectors.slots_for(user, branch, academic_year=year).count()

        badges = []
        if year.is_current:
            badges.append(badge(_("Current"), "success", "bi-star-fill"))
        if year.is_closed:
            badges.append(badge(_("Closed"), "secondary", "bi-lock-fill"))
        elif not year.is_current:
            badges.append(badge(_("Open"), "info", "bi-unlock"))

        return {
            "detail_icon": "bi-calendar-range",
            "detail_title": year.name,
            "detail_subtitle": _("%(start)s to %(end)s")
            % {"start": year.start_date, "end": year.end_date},
            "detail_badges": badges,
            "detail_meta": [
                meta(_("Starts"), year.start_date, "bi-play-circle"),
                meta(_("Ends"), year.end_date, "bi-stop-circle"),
                meta(_("Terms"), term_count, "bi-signpost-split"),
                meta(_("Timetable slots"), slot_count, "bi-calendar-week"),
            ],
            "detail_tabs": [
                tab("overview", _("Overview"), "bi-info-circle"),
                tab("terms", _("Terms"), "bi-signpost-split", term_count),
                tab("subjects", _("Class Subjects"), "bi-journal-text", subject_count),
                tab("teaching", _("Teaching"), "bi-person-video3", assignment_count),
            ],
            "slot_count": slot_count,
            "term_count": term_count,
            "timetable_url": selectors.listing(
                "academics:timetable", academic_year=year.pk
            ),
            "terms_card": related_card(
                title=_("Terms"),
                icon="bi-signpost-split",
                columns=[_("Term"), _("Sequence"), _("Starts"), _("Ends"), _("Current")],
                rows=[
                    row(
                        reverse("academics:term_detail", args=[term.pk]),
                        cell(_("Term"), term.name),
                        cell(_("Sequence"), term.sequence),
                        cell(_("Starts"), term.start_date),
                        cell(_("Ends"), term.end_date),
                        cell(
                            _("Current"),
                            _("Current") if term.is_current else "—",
                            "success" if term.is_current else None,
                        ),
                    )
                    for term in terms
                ],
                total=term_count,
                all_url=selectors.listing("academics:term_list", academic_year=year.pk),
                add_url=reverse("academics:term_create"),
                add_label=_("Add term"),
                empty=_("No terms yet"),
                empty_hint=_("Terms divide the year into the periods you report on."),
            ),
            "subjects_card": related_card(
                title=_("Class Subjects"),
                icon="bi-journal-text",
                columns=[_("Class"), _("Subject"), _("Weekly periods"), _("Active")],
                rows=[
                    row(
                        reverse("academics:classsubject_detail", args=[item.pk]),
                        cell(_("Class"), item.school_class.name),
                        cell(_("Subject"), item.subject.name),
                        cell(_("Weekly periods"), item.weekly_periods),
                        cell(
                            _("Active"),
                            _("Active") if item.is_active else _("Inactive"),
                            "success" if item.is_active else "secondary",
                        ),
                    )
                    for item in subjects
                ],
                total=subject_count,
                all_url=selectors.listing(
                    "academics:classsubject_list", academic_year=year.pk
                ),
                add_url=reverse("academics:classsubject_create"),
                add_label=_("Add class subject"),
                empty=_("No subjects assigned to classes yet"),
                empty_hint=_("A class subject is what a class studies this year."),
            ),
            "assignments_card": related_card(
                title=_("Teacher Assignments"),
                icon="bi-person-video3",
                columns=[_("Teacher"), _("Class"), _("Subject"), _("Section")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[item.pk]),
                        cell(_("Teacher"), item.teacher.full_name),
                        cell(_("Class"), item.class_subject.school_class.name),
                        cell(_("Subject"), item.class_subject.subject.name),
                        cell(_("Section"), item.section.name if item.section else _("All")),
                    )
                    for item in assignments
                ],
                total=assignment_count,
                all_url=selectors.listing(
                    "academics:assignment_list", academic_year=year.pk
                ),
                add_url=reverse("academics:assignment_create"),
                add_label=_("Assign a teacher"),
                empty=_("Nobody is assigned to teach yet"),
                empty_hint=_("Assignments say who teaches which subject to which class."),
            ),
        }


# --------------------------------------------------------------------------
# Term
# --------------------------------------------------------------------------
class TermDetailView(AcademicsDetailView):
    """A term is a short record: dates and its place in the year. No tabs."""

    model = Term
    template_name = "academics/term_detail.html"
    select_related = ("academic_year",)
    back_url_name = "academics:term_list"
    back_label = _("Back to terms")
    page_title = _("Term")

    def get_detail_context(self):
        term = self.object
        year = term.academic_year
        siblings = selectors.year_terms(self.request.user, self.active_branch, year)

        return {
            "detail_icon": "bi-signpost-split",
            "detail_title": term.name,
            "detail_subtitle": year.name,
            "detail_badges": (
                [badge(_("Current term"), "success", "bi-star-fill")]
                if term.is_current
                else []
            ),
            "detail_meta": [
                meta(
                    _("Academic year"),
                    year.name,
                    "bi-calendar-range",
                    reverse("academics:year_detail", args=[year.pk]),
                ),
                meta(_("Sequence"), term.sequence, "bi-sort-numeric-down"),
                meta(_("Starts"), term.start_date, "bi-play-circle"),
                meta(_("Ends"), term.end_date, "bi-stop-circle"),
            ],
            "siblings_card": related_card(
                title=_("Other terms this year"),
                icon="bi-signpost-split",
                columns=[_("Term"), _("Sequence"), _("Starts"), _("Ends")],
                rows=[
                    row(
                        reverse("academics:term_detail", args=[other.pk]),
                        cell(_("Term"), other.name),
                        cell(_("Sequence"), other.sequence),
                        cell(_("Starts"), other.start_date),
                        cell(_("Ends"), other.end_date),
                    )
                    for other in siblings.exclude(pk=term.pk)[:PREVIEW]
                ],
                all_url=selectors.listing("academics:term_list", academic_year=year.pk),
                empty=_("This is the only term in %(year)s") % {"year": year.name},
            ),
        }


# --------------------------------------------------------------------------
# Class
# --------------------------------------------------------------------------
class SchoolClassDetailView(AcademicsDetailView):
    model = SchoolClass
    template_name = "academics/class_detail.html"
    back_url_name = "academics:class_list"
    back_label = _("Back to classes")
    page_title = _("Class")

    def get_detail_context(self):
        user, branch, school_class = self.request.user, self.active_branch, self.object
        year = selectors.current_year(user, branch)

        sections, section_count = self.preview(
            selectors.class_sections(user, branch, school_class)
        )
        subjects, subject_count = self.preview(
            selectors.class_subjects_for(user, branch, school_class=school_class)
        )
        teaching, teaching_count = self.preview(
            selectors.assignments_for(
                user, branch, class_subject__school_class=school_class
            )
        )
        student_count = sum(
            selectors.section_students(user, branch, section).count()
            for section in sections
        )

        return {
            "detail_icon": "bi-mortarboard",
            "detail_title": school_class.name,
            "detail_subtitle": school_class.description or school_class.code,
            "detail_badges": [
                active_badge(school_class.is_active, _("Active"), _("Inactive"))
            ],
            "detail_meta": [
                meta(_("Code"), school_class.code, "bi-hash"),
                meta(_("Level"), school_class.level, "bi-bar-chart-steps"),
                meta(_("Sections"), section_count, "bi-diagram-3"),
                meta(_("Students"), student_count, "bi-people"),
            ],
            "detail_tabs": [
                tab("overview", _("Overview"), "bi-info-circle"),
                tab("sections", _("Sections"), "bi-diagram-3", section_count),
                tab("subjects", _("Subjects"), "bi-journal-text", subject_count),
                tab("teachers", _("Teachers"), "bi-person-video3", teaching_count),
            ],
            "student_count": student_count,
            "timetable_url": selectors.listing(
                "academics:timetable",
                academic_year=year.pk if year else "",
                section=sections[0].pk if sections else "",
            ),
            "sections_card": related_card(
                title=_("Sections"),
                icon="bi-diagram-3",
                columns=[_("Section"), _("Class teacher"), _("Capacity"), _("Active")],
                rows=[
                    row(
                        reverse("academics:section_detail", args=[section.pk]),
                        cell(_("Section"), section.name),
                        cell(
                            _("Class teacher"),
                            section.class_teacher.full_name if section.class_teacher else "—",
                        ),
                        cell(_("Capacity"), section.capacity or "—"),
                        cell(
                            _("Active"),
                            _("Active") if section.is_active else _("Inactive"),
                            "success" if section.is_active else "secondary",
                        ),
                    )
                    for section in sections
                ],
                total=section_count,
                all_url=selectors.listing(
                    "academics:section_list", school_class=school_class.pk
                ),
                add_url=reverse("academics:section_create"),
                add_label=_("Add section"),
                empty=_("No sections yet"),
                empty_hint=_("Sections split a class into the groups that sit together."),
            ),
            "subjects_card": related_card(
                title=_("Subjects taught"),
                icon="bi-journal-text",
                columns=[_("Subject"), _("Academic year"), _("Weekly periods"), _("Active")],
                rows=[
                    row(
                        reverse("academics:classsubject_detail", args=[item.pk]),
                        cell(_("Subject"), item.subject.name),
                        cell(_("Academic year"), item.academic_year.name),
                        cell(_("Weekly periods"), item.weekly_periods),
                        cell(
                            _("Active"),
                            _("Active") if item.is_active else _("Inactive"),
                            "success" if item.is_active else "secondary",
                        ),
                    )
                    for item in subjects
                ],
                total=subject_count,
                all_url=selectors.listing(
                    "academics:classsubject_list", school_class=school_class.pk
                ),
                add_url=reverse("academics:classsubject_create"),
                add_label=_("Add subject to this class"),
                empty=_("No subjects yet"),
                empty_hint=_("Add the subjects this class studies before building its timetable."),
            ),
            "teachers_card": related_card(
                title=_("Teachers"),
                icon="bi-person-video3",
                columns=[_("Teacher"), _("Subject"), _("Section"), _("Active")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[item.pk]),
                        cell(_("Teacher"), item.teacher.full_name),
                        cell(_("Subject"), item.class_subject.subject.name),
                        cell(_("Section"), item.section.name if item.section else _("All")),
                        cell(
                            _("Active"),
                            _("Active") if item.is_active else _("Inactive"),
                            "success" if item.is_active else "secondary",
                        ),
                    )
                    for item in teaching
                ],
                total=teaching_count,
                all_url=selectors.listing(
                    "academics:assignment_list", school_class=school_class.pk
                ),
                add_url=reverse("academics:assignment_create"),
                add_label=_("Assign a teacher"),
                empty=_("Nobody is assigned to this class yet"),
            ),
        }


# --------------------------------------------------------------------------
# Section
# --------------------------------------------------------------------------
class SectionDetailView(AcademicsDetailView):
    model = Section
    template_name = "academics/section_detail.html"
    select_related = ("school_class", "class_teacher")
    back_url_name = "academics:section_list"
    back_label = _("Back to sections")
    page_title = _("Section")

    def get_detail_context(self):
        user, branch, section = self.request.user, self.active_branch, self.object
        year = selectors.current_year(user, branch)

        enrollments, student_count = self.preview(
            selectors.section_students(user, branch, section)
        )
        subjects, subject_count = self.preview(
            selectors.class_subjects_for(user, branch, school_class=section.school_class)
        )
        teaching, teaching_count = self.preview(
            selectors.assignments_for(user, branch, section=section)
        )
        slots, slot_count = self.preview(selectors.slots_for(user, branch, section=section))

        return {
            "detail_icon": "bi-diagram-3",
            "detail_title": f"{section.school_class.name} — {section.name}",
            "detail_subtitle": (
                _("Class teacher: %(name)s") % {"name": section.class_teacher.full_name}
                if section.class_teacher
                else _("No class teacher assigned")
            ),
            "detail_badges": [active_badge(section.is_active, _("Active"), _("Inactive"))],
            "detail_meta": [
                meta(
                    _("Class"),
                    section.school_class.name,
                    "bi-mortarboard",
                    reverse("academics:class_detail", args=[section.school_class.pk]),
                ),
                meta(_("Students"), student_count, "bi-people"),
                meta(
                    _("Capacity"),
                    section.capacity if section.capacity else _("Not set"),
                    "bi-person-plus",
                ),
                meta(_("Timetable slots"), slot_count, "bi-calendar-week"),
            ],
            "detail_tabs": [
                tab("overview", _("Overview"), "bi-info-circle"),
                tab("students", _("Students"), "bi-people", student_count),
                tab("subjects", _("Subjects"), "bi-journal-text", subject_count),
                tab("teachers", _("Teachers"), "bi-person-video3", teaching_count),
                tab("timetable", _("Timetable"), "bi-calendar-week", slot_count),
            ],
            "capacity_used": (
                round(student_count / section.capacity * 100)
                if section.capacity
                else None
            ),
            "student_count": student_count,
            "timetable_url": selectors.listing(
                "academics:timetable",
                academic_year=year.pk if year else "",
                section=section.pk,
            ),
            "students_card": related_card(
                title=_("Students"),
                icon="bi-people",
                columns=[_("Student"), _("Admission #"), _("Roll number")],
                rows=[
                    row(
                        reverse("students:student_detail", args=[item.student.pk]),
                        cell(_("Student"), item.student.full_name),
                        cell(_("Admission #"), item.student.admission_no),
                        cell(_("Roll number"), item.roll_number or "—"),
                    )
                    for item in enrollments
                ],
                total=student_count,
                all_url=selectors.listing(
                    "students:student_list", school_class=section.school_class_id
                ),
                all_label=_("View in students"),
                empty=_("Nobody is enrolled in this section"),
                empty_hint=_("Students appear here once they are enrolled into it."),
            ),
            "subjects_card": related_card(
                title=_("Subjects"),
                icon="bi-journal-text",
                columns=[_("Subject"), _("Academic year"), _("Weekly periods")],
                rows=[
                    row(
                        reverse("academics:classsubject_detail", args=[item.pk]),
                        cell(_("Subject"), item.subject.name),
                        cell(_("Academic year"), item.academic_year.name),
                        cell(_("Weekly periods"), item.weekly_periods),
                    )
                    for item in subjects
                ],
                total=subject_count,
                all_url=selectors.listing(
                    "academics:classsubject_list", school_class=section.school_class_id
                ),
                empty=_("This class has no subjects yet"),
                empty_hint=_("Subjects belong to the class, and every section studies them."),
            ),
            "teachers_card": related_card(
                title=_("Teachers"),
                icon="bi-person-video3",
                columns=[_("Teacher"), _("Subject"), _("Active")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[item.pk]),
                        cell(_("Teacher"), item.teacher.full_name),
                        cell(_("Subject"), item.class_subject.subject.name),
                        cell(
                            _("Active"),
                            _("Active") if item.is_active else _("Inactive"),
                            "success" if item.is_active else "secondary",
                        ),
                    )
                    for item in teaching
                ],
                total=teaching_count,
                all_url=selectors.listing("academics:assignment_list", section=section.pk),
                add_url=reverse("academics:assignment_create"),
                add_label=_("Assign a teacher"),
                empty=_("Nobody is assigned to this section yet"),
            ),
            "slots_card": related_card(
                title=_("Timetable"),
                icon="bi-calendar-week",
                columns=[_("Day"), _("Period"), _("Subject"), _("Teacher"), _("Time")],
                rows=[
                    row(
                        reverse("academics:timetable_detail", args=[slot.pk]),
                        cell(_("Day"), slot.get_weekday_display()),
                        cell(_("Period"), slot.period),
                        cell(_("Subject"), slot.class_subject.subject.name),
                        cell(
                            _("Teacher"),
                            slot.teacher.full_name if slot.teacher else "—",
                        ),
                        cell(
                            _("Time"),
                            f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
                        ),
                    )
                    for slot in slots
                ],
                total=slot_count,
                all_url=selectors.listing(
                    "academics:timetable",
                    academic_year=year.pk if year else "",
                    section=section.pk,
                ),
                all_label=_("Open weekly grid"),
                empty=_("No timetable yet"),
                empty_hint=_("Build this section's week in the timetable grid."),
            ),
        }


# --------------------------------------------------------------------------
# Subject
# --------------------------------------------------------------------------
class SubjectDetailView(AcademicsDetailView):
    model = Subject
    template_name = "academics/subject_detail.html"
    back_url_name = "academics:subject_list"
    back_label = _("Back to subjects")
    page_title = _("Subject")

    def get_detail_context(self):
        user, branch, subject = self.request.user, self.active_branch, self.object

        taught, taught_count = self.preview(
            selectors.class_subjects_for(user, branch, subject=subject)
        )
        teaching, teaching_count = self.preview(
            selectors.assignments_for(user, branch, class_subject__subject=subject)
        )
        slot_count = selectors.slots_for(
            user, branch, class_subject__subject=subject
        ).count()

        badges = [active_badge(subject.is_active, _("Active"), _("Inactive"))]
        if subject.is_elective:
            badges.append(badge(_("Elective"), "info", "bi-star"))

        return {
            "detail_icon": "bi-journal-text",
            "detail_title": subject.name,
            "detail_subtitle": subject.get_kind_display(),
            "detail_badges": badges,
            "detail_meta": [
                meta(_("Code"), subject.code or "—", "bi-hash"),
                meta(_("Kind"), subject.get_kind_display(), "bi-tag"),
                meta(_("Taught to"), taught_count, "bi-mortarboard"),
                meta(_("Timetable slots"), slot_count, "bi-calendar-week"),
            ],
            "detail_tabs": [
                tab("overview", _("Overview"), "bi-info-circle"),
                tab("classes", _("Classes"), "bi-mortarboard", taught_count),
                tab("teachers", _("Teachers"), "bi-person-video3", teaching_count),
            ],
            "slot_count": slot_count,
            "classes_card": related_card(
                title=_("Classes studying this subject"),
                icon="bi-mortarboard",
                columns=[_("Class"), _("Academic year"), _("Weekly periods"), _("Active")],
                rows=[
                    row(
                        reverse("academics:classsubject_detail", args=[item.pk]),
                        cell(_("Class"), item.school_class.name),
                        cell(_("Academic year"), item.academic_year.name),
                        cell(_("Weekly periods"), item.weekly_periods),
                        cell(
                            _("Active"),
                            _("Active") if item.is_active else _("Inactive"),
                            "success" if item.is_active else "secondary",
                        ),
                    )
                    for item in taught
                ],
                total=taught_count,
                all_url=selectors.listing(
                    "academics:classsubject_list", subject=subject.pk
                ),
                add_url=reverse("academics:classsubject_create"),
                add_label=_("Teach this to a class"),
                empty=_("No class studies this subject yet"),
                empty_hint=_("Add it to a class to put it on a timetable."),
            ),
            "teachers_card": related_card(
                title=_("Teachers"),
                icon="bi-person-video3",
                columns=[_("Teacher"), _("Class"), _("Section")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[item.pk]),
                        cell(_("Teacher"), item.teacher.full_name),
                        cell(_("Class"), item.class_subject.school_class.name),
                        cell(_("Section"), item.section.name if item.section else _("All")),
                    )
                    for item in teaching
                ],
                total=teaching_count,
                all_url=selectors.listing("academics:assignment_list", subject=subject.pk),
                add_url=reverse("academics:assignment_create"),
                add_label=_("Assign a teacher"),
                empty=_("Nobody teaches this subject yet"),
            ),
        }


# --------------------------------------------------------------------------
# Class subject
# --------------------------------------------------------------------------
class ClassSubjectDetailView(AcademicsDetailView):
    model = ClassSubject
    template_name = "academics/classsubject_detail.html"
    select_related = ("academic_year", "school_class", "subject")
    back_url_name = "academics:classsubject_list"
    back_label = _("Back to class subjects")
    page_title = _("Class Subject")

    def get_detail_context(self):
        user, branch, item = self.request.user, self.active_branch, self.object

        teaching, teaching_count = self.preview(
            selectors.assignments_for(user, branch, class_subject=item)
        )
        slots, slot_count = self.preview(
            selectors.slots_for(user, branch, class_subject=item)
        )

        return {
            "detail_icon": "bi-journal-text",
            "detail_title": f"{item.subject.name} — {item.school_class.name}",
            "detail_subtitle": item.academic_year.name,
            "detail_badges": [active_badge(item.is_active, _("Active"), _("Inactive"))],
            "detail_meta": [
                meta(
                    _("Subject"),
                    item.subject.name,
                    "bi-journal-text",
                    reverse("academics:subject_detail", args=[item.subject.pk]),
                ),
                meta(
                    _("Class"),
                    item.school_class.name,
                    "bi-mortarboard",
                    reverse("academics:class_detail", args=[item.school_class.pk]),
                ),
                meta(
                    _("Academic year"),
                    item.academic_year.name,
                    "bi-calendar-range",
                    reverse("academics:year_detail", args=[item.academic_year.pk]),
                ),
                meta(_("Weekly periods"), item.weekly_periods, "bi-clock-history"),
            ],
            "weekly_periods": item.weekly_periods,
            "scheduled_periods": slot_count,
            "periods_short": max(item.weekly_periods - slot_count, 0),
            "teachers_card": related_card(
                title=_("Teachers"),
                icon="bi-person-video3",
                columns=[_("Teacher"), _("Section"), _("Active")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[assignment.pk]),
                        cell(_("Teacher"), assignment.teacher.full_name),
                        cell(
                            _("Section"),
                            assignment.section.name if assignment.section else _("All"),
                        ),
                        cell(
                            _("Active"),
                            _("Active") if assignment.is_active else _("Inactive"),
                            "success" if assignment.is_active else "secondary",
                        ),
                    )
                    for assignment in teaching
                ],
                total=teaching_count,
                all_url=selectors.listing(
                    "academics:assignment_list", class_subject=item.pk
                ),
                add_url=reverse("academics:assignment_create"),
                add_label=_("Assign a teacher"),
                empty=_("Nobody teaches this yet"),
            ),
            "slots_card": related_card(
                title=_("On the timetable"),
                icon="bi-calendar-week",
                columns=[_("Day"), _("Period"), _("Section"), _("Teacher"), _("Time")],
                rows=[
                    row(
                        reverse("academics:timetable_detail", args=[slot.pk]),
                        cell(_("Day"), slot.get_weekday_display()),
                        cell(_("Period"), slot.period),
                        cell(_("Section"), slot.section.name),
                        cell(_("Teacher"), slot.teacher.full_name if slot.teacher else "—"),
                        cell(_("Time"), f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"),
                    )
                    for slot in slots
                ],
                total=slot_count,
                all_url=selectors.listing(
                    "academics:timetable_list", class_subject=item.pk
                ),
                empty=_("Not on the timetable yet"),
                empty_hint=_("Schedule it so teachers and students know when it meets."),
            ),
        }


# --------------------------------------------------------------------------
# Teacher assignment
# --------------------------------------------------------------------------
class TeacherAssignmentDetailView(AcademicsDetailView):
    model = TeacherAssignment
    template_name = "academics/assignment_detail.html"
    select_related = (
        "teacher",
        "section",
        "academic_year",
        "class_subject__subject",
        "class_subject__school_class",
    )
    back_url_name = "academics:assignment_list"
    back_label = _("Back to teacher assignments")
    page_title = _("Teacher Assignment")

    def get_detail_context(self):
        user, branch, item = self.request.user, self.active_branch, self.object
        class_subject = item.class_subject

        filters = {"class_subject": class_subject, "teacher": item.teacher}
        if item.section_id:
            filters["section"] = item.section
        slots, slot_count = self.preview(selectors.slots_for(user, branch, **filters))

        other, other_count = self.preview(
            selectors.assignments_for(user, branch, teacher=item.teacher).exclude(
                pk=item.pk
            )
        )

        return {
            "detail_icon": "bi-person-video3",
            "detail_title": item.teacher.full_name,
            "detail_subtitle": _("%(subject)s · %(klass)s")
            % {
                "subject": class_subject.subject.name,
                "klass": class_subject.school_class.name,
            },
            "detail_badges": [active_badge(item.is_active, _("Active"), _("Inactive"))],
            "detail_meta": [
                meta(
                    _("Teacher"),
                    item.teacher.full_name,
                    "bi-person",
                    reverse("staff:staff_detail", args=[item.teacher.pk]),
                ),
                meta(
                    _("Subject"),
                    class_subject.subject.name,
                    "bi-journal-text",
                    reverse("academics:subject_detail", args=[class_subject.subject.pk]),
                ),
                meta(
                    _("Class"),
                    class_subject.school_class.name,
                    "bi-mortarboard",
                    reverse(
                        "academics:class_detail", args=[class_subject.school_class.pk]
                    ),
                ),
                meta(
                    _("Section"),
                    item.section.name if item.section else _("All sections"),
                    "bi-diagram-3",
                    reverse("academics:section_detail", args=[item.section.pk])
                    if item.section
                    else None,
                ),
            ],
            "slots_card": related_card(
                title=_("Schedule"),
                icon="bi-calendar-week",
                columns=[_("Day"), _("Period"), _("Section"), _("Time"), _("Room")],
                rows=[
                    row(
                        reverse("academics:timetable_detail", args=[slot.pk]),
                        cell(_("Day"), slot.get_weekday_display()),
                        cell(_("Period"), slot.period),
                        cell(_("Section"), slot.section.name),
                        cell(_("Time"), f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}"),
                        cell(_("Room"), slot.room or "—"),
                    )
                    for slot in slots
                ],
                total=slot_count,
                all_url=selectors.listing(
                    "academics:timetable_list", teacher=item.teacher_id
                ),
                empty=_("Nothing scheduled for this assignment"),
                empty_hint=_(
                    "An assignment says who teaches what; the timetable says when."
                ),
            ),
            "other_card": related_card(
                title=_("Also taught by %(name)s") % {"name": item.teacher.full_name},
                icon="bi-list-check",
                columns=[_("Subject"), _("Class"), _("Section")],
                rows=[
                    row(
                        reverse("academics:assignment_detail", args=[other_item.pk]),
                        cell(_("Subject"), other_item.class_subject.subject.name),
                        cell(_("Class"), other_item.class_subject.school_class.name),
                        cell(
                            _("Section"),
                            other_item.section.name if other_item.section else _("All"),
                        ),
                    )
                    for other_item in other
                ],
                total=other_count,
                all_url=selectors.listing(
                    "academics:assignment_list", teacher=item.teacher_id
                ),
                empty=_("This is their only assignment"),
            ),
        }


# --------------------------------------------------------------------------
# Timetable slot
# --------------------------------------------------------------------------
class TimetableDetailView(AcademicsDetailView):
    model = Timetable
    template_name = "academics/timetable_detail.html"
    select_related = (
        "academic_year",
        "teacher",
        "section__school_class",
        "class_subject__subject",
    )
    back_url_name = "academics:timetable_list"
    back_label = _("Back to timetable slots")
    page_title = _("Timetable Slot")

    def get_detail_context(self):
        user, branch, slot = self.request.user, self.active_branch, self.object

        same_day, same_day_count = self.preview(
            selectors.slots_for(
                user,
                branch,
                section=slot.section,
                weekday=slot.weekday,
                academic_year=slot.academic_year,
            )
        )

        return {
            "detail_icon": "bi-calendar-week",
            "detail_title": slot.class_subject.subject.name,
            "detail_subtitle": _("%(section)s · %(day)s · period %(period)s")
            % {
                "section": slot.section,
                "day": slot.get_weekday_display(),
                "period": slot.period,
            },
            "detail_badges": [
                badge(f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}", "info", "bi-clock")
            ],
            "detail_meta": [
                meta(
                    _("Section"),
                    str(slot.section),
                    "bi-diagram-3",
                    reverse("academics:section_detail", args=[slot.section.pk]),
                ),
                meta(
                    _("Subject"),
                    slot.class_subject.subject.name,
                    "bi-journal-text",
                    reverse(
                        "academics:classsubject_detail", args=[slot.class_subject.pk]
                    ),
                ),
                meta(
                    _("Teacher"),
                    slot.teacher.full_name if slot.teacher else _("Not assigned"),
                    "bi-person-video3",
                    reverse("staff:staff_detail", args=[slot.teacher.pk])
                    if slot.teacher
                    else None,
                ),
                meta(_("Room"), slot.room or "—", "bi-door-open"),
            ],
            "grid_url": selectors.listing(
                "academics:timetable",
                academic_year=slot.academic_year_id,
                section=slot.section_id,
            ),
            "day_card": related_card(
                title=_("The rest of %(day)s") % {"day": slot.get_weekday_display()},
                icon="bi-calendar-day",
                columns=[_("Period"), _("Subject"), _("Teacher"), _("Time")],
                rows=[
                    row(
                        reverse("academics:timetable_detail", args=[other.pk]),
                        cell(_("Period"), other.period),
                        cell(_("Subject"), other.class_subject.subject.name),
                        cell(_("Teacher"), other.teacher.full_name if other.teacher else "—"),
                        cell(_("Time"), f"{other.start_time:%H:%M}–{other.end_time:%H:%M}"),
                    )
                    for other in same_day
                ],
                total=same_day_count,
                all_url=selectors.listing(
                    "academics:timetable",
                    academic_year=slot.academic_year_id,
                    section=slot.section_id,
                ),
                all_label=_("Open weekly grid"),
                empty=_("Nothing else scheduled that day"),
            ),
        }
