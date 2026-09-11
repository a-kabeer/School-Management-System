"""The headline security scenario.

    User from Branch A → tries to open a Branch B record id → ACCESS DENIED

Every route into a record is exercised: detail, edit, delete, the service
layer and the JSON search endpoint.
"""

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import build_student, build_user, two_branches

PASSWORD = "Str0ngPassphrase!42"
STUDENT_PERMISSIONS = [
    "core.access_students",
    "students.view_student",
    "students.add_student",
    "students.change_student",
    "students.delete_student",
]


class CrossBranchRecordAccessTests(TestCase):
    def setUp(self):
        self.branch_a, self.branch_b = two_branches()
        self.student_a = build_student(self.branch_a, "Ali A", "A-100")
        self.student_b = build_student(self.branch_b, "Bilal B", "B-100")

        build_user(
            self.branch_a.branch,
            username="branch_a_user",
            permissions=STUDENT_PERMISSIONS,
        )
        self.client.login(username="branch_a_user", password=PASSWORD)

    def test_own_branch_record_opens(self):
        response = self.client.get(
            reverse("students:student_detail", args=[self.student_a.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_other_branch_record_is_denied(self):
        response = self.client.get(
            reverse("students:student_detail", args=[self.student_b.pk])
        )
        self.assertIn(response.status_code, (403, 404))

    def test_other_branch_record_cannot_be_edited(self):
        response = self.client.get(
            reverse("students:student_update", args=[self.student_b.pk])
        )
        self.assertIn(response.status_code, (403, 404))

    def test_other_branch_record_cannot_be_posted_to(self):
        response = self.client.post(
            reverse("students:student_update", args=[self.student_b.pk]),
            {"full_name": "Renamed", "admission_no": "B-100", "status": "active"},
        )
        self.assertIn(response.status_code, (403, 404))
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.full_name, "Bilal B")

    def test_other_branch_record_cannot_be_deleted(self):
        response = self.client.post(
            reverse("students:student_delete", args=[self.student_b.pk])
        )
        self.assertIn(response.status_code, (403, 404))
        self.student_b.refresh_from_db()
        self.assertFalse(self.student_b.is_deleted)

    def test_other_branch_record_cannot_have_its_status_changed(self):
        response = self.client.post(
            reverse("students:student_status", args=[self.student_b.pk]),
            {"status": "withdrawn", "effective_date": "2026-06-01", "reason": "test"},
        )
        self.assertIn(response.status_code, (403, 404))
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.status, "active")

    def test_list_view_excludes_other_branches(self):
        response = self.client.get(reverse("students:student_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ali A")
        self.assertNotContains(response, "Bilal B")

    def test_search_endpoint_excludes_other_branches(self):
        response = self.client.get(reverse("students:student_search"), {"q": "B"})
        self.assertEqual(response.status_code, 200)
        names = [row["text"] for row in response.json()["results"]]
        self.assertFalse(any("Bilal" in name for name in names))

    def test_enrollment_form_rejects_another_branch_class(self):
        from apps.students.forms import EnrollmentForm

        form = EnrollmentForm(
            data={
                "student": str(self.student_a.pk),
                "academic_year": str(self.branch_b.academic_year.pk),
                "school_class": str(self.branch_b.school_class.pk),
                "start_date": "2026-06-01",
                "is_current": True,
            },
            branch=self.branch_a.branch,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("school_class", form.errors)


class BranchSwitchingTests(TestCase):
    def setUp(self):
        self.branch_a, self.branch_b = two_branches()
        self.user = build_user(
            self.branch_a.branch,
            username="switcher",
            permissions=["core.access_dashboard"],
        )
        self.client.login(username="switcher", password=PASSWORD)

    def test_switching_to_an_unauthorized_branch_is_refused(self):
        response = self.client.post(
            reverse("tenants:switch_branch"), {"branch": str(self.branch_b.branch.pk)}
        )
        self.assertEqual(response.status_code, 403)

    def test_switching_to_an_authorized_branch_works(self):
        from apps.accounts.rbac import grant_branch_access
        from apps.core.constants import ACTIVE_BRANCH_SESSION_KEY

        grant_branch_access(self.user, self.branch_b.branch)
        response = self.client.post(
            reverse("tenants:switch_branch"),
            {"branch": str(self.branch_b.branch.pk)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session[ACTIVE_BRANCH_SESSION_KEY], str(self.branch_b.branch.pk)
        )

    def test_a_tampered_session_branch_is_discarded(self):
        from apps.core.constants import ACTIVE_BRANCH_SESSION_KEY

        session = self.client.session
        session[ACTIVE_BRANCH_SESSION_KEY] = str(self.branch_b.branch.pk)
        session.save()

        self.client.get(reverse("core:dashboard"))
        # The middleware falls back to a branch the user may actually enter.
        self.assertEqual(
            self.client.session[ACTIVE_BRANCH_SESSION_KEY], str(self.branch_a.branch.pk)
        )
