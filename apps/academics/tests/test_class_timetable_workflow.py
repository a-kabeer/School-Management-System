import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.academics.models import Section, Timetable
from apps.academics.tests.test_workflow import AcademicsFixture
from apps.core.tests.factories import build_subject


class ClassTimetableWorkflowTests(AcademicsFixture):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)
        self.client.login(username="academics_admin", password="Str0ngPassphrase!42")

    def test_class_detail_opens_timetable_at_class_all_sections(self):
        response = self.client.get(
            reverse("academics:class_detail", args=[self.school_class.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'{reverse("academics:timetable")}?school_class={self.school_class.pk}',
        )

    def test_class_timetable_does_not_select_first_section(self):
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=self.school_class,
            name="B",
        )
        response = self.client.get(
            reverse("academics:timetable"),
            {
                "academic_year": self.year.pk,
                "school_class": self.school_class.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["section"])
        self.assertTrue(response.context["all_sections"])
        self.assertContains(response, "All Sections")
        self.assertContains(response, f'value="{self.section.pk}"')
        self.assertContains(response, f'value="{other_section.pk}"')

    def test_class_all_sections_grid_shows_lessons_from_multiple_sections(self):
        other_section = Section.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            school_class=self.school_class,
            name="B",
        )
        other_class_subject = build_subject(self.fixture, "History")
        other_slot = Timetable.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.year,
            section=other_section,
            class_subject=other_class_subject,
            weekday=0,
            period=2,
            start_time=dt.time(10, 0),
            end_time=dt.time(10, 40),
        )
        response = self.client.get(
            reverse("academics:timetable"),
            {
                "academic_year": self.year.pk,
                "school_class": self.school_class.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        slots = [slot for line in response.context["grid"] for cell in line["cells"] for slot in cell["slots"]]
        self.assertIn(self.slot, slots)
        self.assertIn(other_slot, slots)
