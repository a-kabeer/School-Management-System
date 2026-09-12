import datetime as dt

from django.core.exceptions import ValidationError

from apps.academics.forms import TimetableForm
from apps.academics.models import Timetable
from apps.academics.tests.test_workflow import AcademicsFixture
from apps.academics.timetable_config import working_weekdays
from django.urls import reverse


class WorkingDayPolicyTests(AcademicsFixture):
    def test_default_working_week_is_monday_to_friday(self):
        self.assertEqual(working_weekdays(), (0, 1, 2, 3, 4))

    def test_timetable_form_only_offers_monday_to_friday(self):
        form = TimetableForm(branch=self.fixture.branch)
        self.assertEqual([value for value, _ in form.fields["weekday"].choices], [0, 1, 2, 3, 4])

    def test_weekend_is_rejected_by_the_form(self):
        form = TimetableForm(
            data={
                "academic_year": self.year.pk,
                "section": self.section.pk,
                "class_subject": self.class_subject.pk,
                "weekday": 5,
                "period": 2,
                "start_time": "09:00",
                "end_time": "09:40",
            },
            branch=self.fixture.branch,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("weekday", form.errors)

    def test_model_rejects_direct_weekend_writes(self):
        with self.assertRaises(ValidationError):
            Timetable.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                academic_year=self.year,
                section=self.section,
                class_subject=self.class_subject,
                weekday=6,
                period=2,
                start_time=dt.time(9, 0),
                end_time=dt.time(9, 40),
            )

    def test_existing_weekend_record_is_preserved_and_hidden_from_grid(self):
        Timetable.objects.filter(pk=self.slot.pk).update(weekday=5)
        response = self.client.get(
            reverse("academics:timetable"),
            {"academic_year": str(self.year.pk), "section": str(self.section.pk)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["weekend_slot_count"], 1)
        self.assertContains(response, "existing weekend lesson")
        self.assertNotContains(response, self.subject.name)
        self.assertTrue(Timetable.objects.filter(pk=self.slot.pk, weekday=5).exists())

    def test_grid_has_exactly_five_working_day_columns(self):
        response = self.client.get(
            reverse("academics:timetable"),
            {"academic_year": str(self.year.pk), "section": str(self.section.pk)},
        )
        self.assertEqual(response.context["weekdays"], [
            {"value": 0, "label": Timetable.Weekday.MONDAY.label},
            {"value": 1, "label": Timetable.Weekday.TUESDAY.label},
            {"value": 2, "label": Timetable.Weekday.WEDNESDAY.label},
            {"value": 3, "label": Timetable.Weekday.THURSDAY.label},
            {"value": 4, "label": Timetable.Weekday.FRIDAY.label},
        ])
        self.assertContains(response, "Monday")
        self.assertContains(response, "Friday")
        self.assertNotContains(response, "Saturday")
        self.assertNotContains(response, "Sunday")
