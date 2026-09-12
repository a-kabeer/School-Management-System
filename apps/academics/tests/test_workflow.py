"""The Academics workflow: moving between related records, and being stopped
from creating ones that contradict each other.

The hierarchy these tests walk is the one the screens are built around:

    Academic Year -> Terms -> Classes -> Sections -> Subjects
                  -> Teacher Assignments -> Timetable
"""

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.academics.models import (
    ClassSubject,
    SchoolClass,
    Section,
    Subject,
    TeacherAssignment,
    Term,
    Timetable,
)
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_staff,
    build_student,
    build_subject,
    build_user,
)

PASSWORD = "Str0ngPassphrase!42"
MONDAY = 0


class AcademicsFixture(TestCase):
    """One branch with a whole academic structure standing up in it."""

    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        cls.year = cls.fixture.academic_year
        cls.school_class = cls.fixture.school_class
        cls.section = cls.fixture.section
        cls.teacher = build_staff(cls.fixture, "Amina Yusuf", "EMP-T1")

        cls.term = Term.objects.create(
            branch=cls.fixture.branch,
            organization=cls.fixture.organization,
            academic_year=cls.year,
            name="First Term",
            sequence=1,
            start_date=cls.year.start_date,
            end_date=cls.year.start_date + dt.timedelta(days=100),
            is_current=True,
        )
        cls.class_subject = build_subject(cls.fixture, "Mathematics")
        cls.subject = cls.class_subject.subject
        cls.assignment = TeacherAssignment.objects.create(
            branch=cls.fixture.branch,
            organization=cls.fixture.organization,
            academic_year=cls.year,
            teacher=cls.teacher,
            class_subject=cls.class_subject,
            section=cls.section,
        )
        cls.slot = Timetable.objects.create(
            branch=cls.fixture.branch,
            organization=cls.fixture.organization,
            academic_year=cls.year,
            section=cls.section,
            class_subject=cls.class_subject,
            teacher=cls.teacher,
            weekday=MONDAY,
            period=1,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 40),
        )
        build_admin(cls.fixture.branch, username="academics_admin")

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.client.login(username="academics_admin", password=PASSWORD)


class ViewScreenTests(AcademicsFixture):
    def records(self):
        return [
            ("academics:year_detail", self.year),
            ("academics:term_detail", self.term),
            ("academics:class_detail", self.school_class),
            ("academics:section_detail", self.section),
            ("academics:subject_detail", self.subject),
            ("academics:classsubject_detail", self.class_subject),
            ("academics:assignment_detail", self.assignment),
            ("academics:timetable_detail", self.slot),
        ]

    def test_every_record_has_a_view_screen(self):
        for name, record in self.records():
            with self.subTest(screen=name):
                response = self.client.get(reverse(name, args=[record.pk]))
                self.assertEqual(response.status_code, 200)
                # Not a dump of fields: a header that says what this is.
                self.assertContains(response, "detail-icon")

    def test_a_view_screen_offers_the_way_back_to_its_list(self):
        response = self.client.get(reverse("academics:section_detail", args=[self.section.pk]))
        self.assertContains(response, reverse("academics:section_list"))

    def test_a_class_shows_its_sections_subjects_and_teachers(self):
        response = self.client.get(
            reverse("academics:class_detail", args=[self.school_class.pk])
        )
        self.assertContains(response, self.section.name)
        self.assertContains(response, self.subject.name)
        self.assertContains(response, self.teacher.full_name)

    def test_a_section_reaches_its_students_class_and_timetable(self):
        student = build_student(self.fixture, "Section Student", "SEC-1")
        response = self.client.get(
            reverse("academics:section_detail", args=[self.section.pk])
        )
        self.assertContains(response, student.full_name)
        self.assertContains(
            response, reverse("academics:class_detail", args=[self.school_class.pk])
        )
        self.assertContains(response, reverse("academics:timetable"))

    def test_a_view_screen_links_into_the_filtered_list_rather_than_a_new_one(self):
        response = self.client.get(
            reverse("academics:class_detail", args=[self.school_class.pk])
        )
        self.assertContains(
            response,
            f"{reverse('academics:section_list')}?school_class={self.school_class.pk}",
        )

    def test_an_empty_relationship_says_so_and_offers_the_action(self):
        empty_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Empty Class",
            code="EMPTY",
            level=9,
        )
        response = self.client.get(
            reverse("academics:class_detail", args=[empty_class.pk])
        )
        self.assertContains(response, "No sections yet")
        self.assertContains(response, "Add section")

    def test_a_simple_record_gets_no_tabs(self):
        # A term is dates and a place in the year; tabs would be decoration.
        response = self.client.get(reverse("academics:term_detail", args=[self.term.pk]))
        self.assertNotContains(response, 'role="tablist"')

    def test_a_comprehensive_record_gets_tabs(self):
        response = self.client.get(
            reverse("academics:section_detail", args=[self.section.pk])
        )
        self.assertContains(response, 'role="tablist"')
        for label in ("Students", "Subjects", "Teachers", "Timetable"):
            self.assertContains(response, label)


class RowClickTests(AcademicsFixture):
    def test_a_list_row_carries_the_link_that_opens_it(self):
        response = self.client.get(reverse("academics:class_list"))
        self.assertContains(
            response,
            f'data-row-url="{reverse("academics:class_detail", args=[self.school_class.pk])}"',
        )

    def test_the_actions_column_still_holds_edit_and_delete(self):
        response = self.client.get(reverse("academics:class_list"))
        self.assertContains(
            response, reverse("academics:class_update", args=[self.school_class.pk])
        )
        self.assertContains(
            response, reverse("academics:class_delete", args=[self.school_class.pk])
        )


class ContextualFilterTests(AcademicsFixture):
    def test_a_list_narrows_to_the_parent_it_was_opened_from(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Other Class",
            code="OTHER",
            level=5,
        )
        Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=other_class,
            name="Z",
        )

        response = self.client.get(
            reverse("academics:section_list"), {"school_class": str(self.school_class.pk)}
        )
        names = [section.school_class_id for section in response.context["objects"]]
        self.assertEqual(set(names), {self.school_class.pk})

    def test_the_filter_survives_sorting_and_paging(self):
        response = self.client.get(
            reverse("academics:section_list"),
            {"school_class": str(self.school_class.pk), "sort": "name", "dir": "desc"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{self.school_class.pk}"')
        self.assertContains(response, 'name="sort" value="name"')

    def test_timetable_slots_narrow_to_one_teacher(self):
        response = self.client.get(
            reverse("academics:timetable_list"), {"teacher": str(self.teacher.pk)}
        )
        self.assertEqual(len(response.context["objects"]), 1)


class ModalWorkflowTests(AcademicsFixture):
    def test_a_form_renders_as_a_fragment_for_the_dialog(self):
        response = self.client.get(
            reverse("academics:subject_create"), headers={"X-Modal": "1"}
        )
        self.assertEqual(response.status_code, 200)
        # A fragment, not a page: no shell around it.
        self.assertNotContains(response, "<body")
        self.assertContains(response, "data-modal-form")

    def test_the_same_form_is_still_a_page_on_a_direct_visit(self):
        response = self.client.get(reverse("academics:subject_create"))
        self.assertContains(response, "<body")

    def test_saving_from_the_dialog_reports_what_it_created(self):
        response = self.client.post(
            reverse("academics:subject_create"),
            {"name": "Geography", "code": "GEO", "kind": "academic", "is_active": "on"},
            headers={"X-Modal": "1"},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["X-Modal-Success"], "1")

        created = Subject.objects.get(name="Geography")
        self.assertEqual(response["X-Modal-Object-Id"], str(created.pk))

    def test_a_rejected_form_comes_back_with_its_errors(self):
        response = self.client.post(
            reverse("academics:subject_create"),
            {"name": "", "kind": "academic"},
            headers={"X-Modal": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid-feedback")

    def test_the_dialog_obeys_the_same_permissions_as_the_page(self):
        reader = build_user(
            self.fixture.branch, username="reader", permissions=("core.access_academics",)
        )
        self.client.force_login(reader)
        response = self.client.get(
            reverse("academics:subject_create"), headers={"X-Modal": "1"}
        )
        self.assertEqual(response.status_code, 403)


class ComboBoxTests(AcademicsFixture):
    def test_a_relation_picker_is_searchable(self):
        response = self.client.get(reverse("academics:section_create"))
        self.assertContains(response, "data-combo")

    def test_a_child_picker_knows_which_parent_its_options_belong_to(self):
        response = self.client.get(reverse("academics:assignment_create"))
        # The subject picker narrows by year and advertises its class...
        self.assertContains(response, 'data-combo-parent="#id_academic_year"')
        self.assertContains(response, f'data-key="{self.school_class.pk}"')
        # ...and the section picker narrows by that class.
        self.assertContains(response, 'data-combo-parent="#id_class_subject"')
        self.assertContains(response, f'data-parent="{self.school_class.pk}"')

    def test_quick_add_is_offered_to_someone_who_may_create_one(self):
        response = self.client.get(reverse("academics:classsubject_create"))
        self.assertContains(response, "data-combo-add-url")
        self.assertContains(response, reverse("academics:subject_create"))

    def test_quick_add_is_not_a_way_around_a_permission(self):
        reader = build_user(
            self.fixture.branch,
            username="no_subjects",
            permissions=("core.access_academics", "academics.add_classsubject"),
        )
        self.client.force_login(reader)
        response = self.client.get(reverse("academics:classsubject_create"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-combo-add-url")


class GuardTests(AcademicsFixture):
    def test_the_same_subject_cannot_be_added_to_a_class_twice(self):
        response = self.client.post(
            reverse("academics:classsubject_create"),
            {
                "academic_year": str(self.year.pk),
                "school_class": str(self.school_class.pk),
                "subject": str(self.subject.pk),
                "weekly_periods": "4",
                "is_active": "on",
            },
        )
        # A refusal the reader can read, not a server error.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ClassSubject.objects.filter(subject=self.subject).count(), 1)

    def test_a_term_cannot_fall_outside_its_year(self):
        response = self.client.post(
            reverse("academics:term_create"),
            {
                "academic_year": str(self.year.pk),
                "name": "Stray Term",
                "sequence": "2",
                "start_date": (self.year.end_date + dt.timedelta(days=10)).isoformat(),
                "end_date": (self.year.end_date + dt.timedelta(days=40)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ends after")
        self.assertFalse(Term.objects.filter(name="Stray Term").exists())

    def test_a_section_cannot_be_taught_a_subject_from_another_class(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Distant Class",
            code="DIST",
            level=7,
        )
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=other_class,
            name="A",
        )
        response = self.client.post(
            reverse("academics:assignment_create"),
            {
                "academic_year": str(self.year.pk),
                "teacher": str(self.teacher.pk),
                "class_subject": str(self.class_subject.pk),
                "section": str(other_section.pk),
                "is_active": "on",
            },
        )
        self.assertContains(response, "belongs to a different class")

    def test_a_period_already_taken_by_the_section_is_refused(self):
        second_subject = build_subject(self.fixture, "History")
        response = self.client.post(
            reverse("academics:timetable_create"),
            {
                "academic_year": str(self.year.pk),
                "section": str(self.section.pk),
                "class_subject": str(second_subject.pk),
                "weekday": str(MONDAY),
                "period": "1",
                "start_time": "09:00",
                "end_time": "09:40",
            },
        )
        self.assertContains(response, "already has")
        self.assertEqual(Timetable.objects.count(), 1)

    def test_a_teacher_cannot_be_in_two_rooms_at_once(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Parallel Class",
            code="PARA",
            level=3,
        )
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=other_class,
            name="A",
        )
        other_subject = Subject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Parallel Subject",
        )
        other_class_subject = ClassSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            school_class=other_class,
            subject=other_subject,
            weekly_periods=3,
        )

        response = self.client.post(
            reverse("academics:timetable_create"),
            {
                "academic_year": str(self.year.pk),
                "section": str(other_section.pk),
                "class_subject": str(other_class_subject.pk),
                "teacher": str(self.teacher.pk),
                "weekday": str(MONDAY),
                "period": "1",
                "start_time": "09:00",
                "end_time": "09:40",
            },
        )
        self.assertContains(response, "already teaches")

    def test_deleting_a_class_says_what_hangs_off_it(self):
        response = self.client.get(
            reverse("academics:class_delete", args=[self.school_class.pk])
        )
        self.assertContains(response, "Other records depend on this one")
        self.assertContains(response, "sections")


class TimetableGridTests(AcademicsFixture):
    def test_the_week_is_drawn_as_a_grid_with_the_lesson_in_place(self):
        response = self.client.get(
            reverse("academics:timetable"),
            {"academic_year": str(self.year.pk), "section": str(self.section.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "timetable-grid")
        self.assertContains(response, self.subject.name)
        self.assertContains(response, "Monday")

    def test_an_empty_period_offers_to_be_filled_without_re_asking_where(self):
        response = self.client.get(
            reverse("academics:timetable"),
            {"academic_year": str(self.year.pk), "section": str(self.section.pk)},
        )
        # Ampersands arrive escaped, as they must in an href.
        expected = (
            f"{reverse('academics:timetable_create')}?academic_year={self.year.pk}"
            f"&amp;section={self.section.pk}&amp;weekday=0&amp;period=2"
        )
        self.assertContains(response, expected)

    def test_a_link_like_that_pre_fills_the_form_it_opens(self):
        response = self.client.get(
            reverse("academics:timetable_create"),
            {
                "academic_year": str(self.year.pk),
                "section": str(self.section.pk),
                "weekday": "0",
                "period": "3",
            },
        )
        form = response.context["form"]
        self.assertEqual(form.initial["period"], "3")
        self.assertEqual(form.initial["section"], str(self.section.pk))

    def test_a_double_booked_teacher_is_marked_on_the_grid(self):
        other_class = SchoolClass.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Clashing Class",
            code="CLASH",
            level=4,
        )
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=other_class,
            name="A",
        )
        other_subject = Subject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            name="Clashing Subject",
        )
        other_class_subject = ClassSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            school_class=other_class,
            subject=other_subject,
        )
        # Written straight to the database: the form refuses this, and the
        # grid has to surface the ones that are already there.
        Timetable.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=other_section,
            class_subject=other_class_subject,
            teacher=self.teacher,
            weekday=MONDAY,
            period=1,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 40),
        )

        response = self.client.get(
            reverse("academics:timetable"),
            {"academic_year": str(self.year.pk), "section": str(self.section.pk)},
        )
        self.assertContains(response, "is-conflicted")
        self.assertContains(response, "double-booked")

    def test_a_branch_with_no_sections_is_told_what_it_needs_first(self):
        empty = build_branch(self.fixture.organization, name="Bare", code="BARE")
        admin = build_admin(empty.branch, username="bare_admin")
        empty.section.delete()
        self.client.force_login(admin)

        response = self.client.get(reverse("academics:timetable"))
        self.assertContains(response, "Nothing to show yet")
        self.assertContains(response, reverse("academics:section_list"))
