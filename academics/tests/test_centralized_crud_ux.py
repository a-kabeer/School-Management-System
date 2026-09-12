"""Regression tests for the unified Academics CRUD entry point and table UX."""

from django.urls import reverse

from .test_workflow import AcademicsFixture


class CentralizedCreateTests(AcademicsFixture):
    def test_add_new_chooser_exposes_only_top_level_academic_resources(self):
        response = self.client.get(reverse("academics:add"))
        self.assertEqual(response.status_code, 200)
        for label in (
            "Academic Year", "Term", "Class", "Section", "Subject",
            "Teacher Assignment", "Timetable",
        ):
            self.assertContains(response, label)
        # ClassSubject is an internal relationship resource and remains
        # available contextually (for example, from a class's Subjects card).
        self.assertNotContains(response, "Class Subject")

    def test_central_create_uses_the_shared_modal_success_contract(self):
        response = self.client.get(
            reverse("academics:add"), {"resource": "subject"},
            headers={"X-Modal": "1"},
        )
        self.assertContains(response, "data-modal-form")
        self.assertContains(response, 'name="resource" value="subject"')

        response = self.client.post(
            reverse("academics:add"),
            {"resource": "subject", "name": "Geography", "code": "GEO",
             "kind": "academic", "is_active": "on"},
            headers={"X-Modal": "1"},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["X-Modal-Success"], "1")

    def test_class_subject_creation_remains_available_contextually(self):
        response = self.client.get(
            reverse("academics:add"), {"resource": "class_subject"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class Subject")


class SharedTableViewTriggerTests(AcademicsFixture):
    def test_explicit_timetable_view_action_uses_shared_row_trigger(self):
        response = self.client.get(reverse("academics:timetable_list"))
        self.assertContains(response, "app-row-view")
        self.assertContains(
            response, reverse("academics:timetable_detail", args=[self.slot.pk])
        )

    def test_all_academic_lists_keep_the_shared_view_action(self):
        for name in (
            "year_list", "term_list", "class_list", "section_list",
            "subject_list", "classsubject_list", "assignment_list", "timetable_list",
        ):
            with self.subTest(list=name):
                response = self.client.get(reverse(f"academics:{name}"))
                self.assertContains(response, "app-row-view")
