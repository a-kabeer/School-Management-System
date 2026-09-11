"""A parent must never reach another family's child."""

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    build_branch,
    build_guardian_with_portal,
    build_student,
)
from apps.parents.selectors import accessible_students

PASSWORD = "Str0ngPassphrase!42"


class ParentAccessTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.own_child = build_student(self.fixture, "Own Child", "P-001")
        self.other_child = build_student(self.fixture, "Other Child", "P-002")
        self.parent_user, self.guardian = build_guardian_with_portal(
            self.fixture, self.own_child, username="parent_one"
        )
        build_guardian_with_portal(self.fixture, self.other_child, username="parent_two")
        self.client.login(username="parent_one", password=PASSWORD)

    def test_portal_lists_only_the_parents_own_children(self):
        children = accessible_students(self.parent_user)
        self.assertIn(self.own_child, children)
        self.assertNotIn(self.other_child, children)

    def test_portal_home_opens(self):
        response = self.client.get(reverse("parents:portal_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Own Child")
        self.assertNotContains(response, "Other Child")

    def test_own_child_detail_opens(self):
        response = self.client.get(
            reverse("parents:child_detail", args=[self.own_child.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_another_familys_child_is_denied(self):
        response = self.client.get(
            reverse("parents:child_detail", args=[self.other_child.pk])
        )
        self.assertIn(response.status_code, (403, 404))

    def test_a_request_cannot_be_raised_about_another_child(self):
        response = self.client.post(
            reverse("parents:request_create"),
            {
                "student": str(self.other_child.pk),
                "request_type": "leave",
                "subject": "Leave",
                "message": "Please grant leave.",
            },
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with an error
        from apps.parents.models import ParentRequest

        self.assertFalse(
            ParentRequest.objects.filter(student=self.other_child).exists()
        )

    def test_a_request_about_their_own_child_is_accepted(self):
        response = self.client.post(
            reverse("parents:request_create"),
            {
                "student": str(self.own_child.pk),
                "request_type": "leave",
                "subject": "Leave",
                "message": "Please grant leave.",
            },
        )
        self.assertEqual(response.status_code, 302)
        from apps.parents.models import ParentRequest

        self.assertTrue(ParentRequest.objects.filter(student=self.own_child).exists())

    def test_a_parent_cannot_open_the_staff_student_list(self):
        response = self.client.get(reverse("students:student_list"))
        self.assertIn(response.status_code, (403, 404))

    def test_unpublished_results_are_hidden_from_parents(self):
        from apps.core.tests.factories import build_subject
        from apps.exams.models import Exam, ExamSubject, ExamTerm
        from apps.exams.services import generate_results, publish_results, register_students

        class_subject = build_subject(self.fixture)
        term = ExamTerm.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            academic_year=self.fixture.academic_year,
            name="Mid Term",
        )
        exam = Exam.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            exam_term=term,
            academic_year=self.fixture.academic_year,
            school_class=self.fixture.school_class,
            name="Mid Term Exam",
            start_date="2026-06-01",
        )
        ExamSubject.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            exam=exam,
            class_subject=class_subject,
        )
        register_students(exam=exam)
        generate_results(exam=exam)

        from apps.parents.selectors import child_results

        self.assertEqual(child_results(self.parent_user, self.own_child).count(), 0)

        publish_results(exam=exam)
        self.assertEqual(child_results(self.parent_user, self.own_child).count(), 1)


class NonParentTests(TestCase):
    def test_a_staff_account_cannot_open_the_parent_portal(self):
        from apps.core.tests.factories import build_user

        fixture = build_branch()
        build_user(fixture.branch, username="staffer")
        self.client.login(username="staffer", password=PASSWORD)
        response = self.client.get(reverse("parents:portal_home"))
        self.assertEqual(response.status_code, 403)
