"""The dashboard shows each role its own work, and nobody else's branch."""

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.core.dashboard import build_dashboard
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_fee_type,
    build_student,
    build_user,
    two_branches,
)

PASSWORD = "Str0ngPassphrase!42"


class EnglishLabelMixin:
    """Pin the language for tests that assert on translated label text.

    Django does not reset the active language between tests, so a test that
    switched to Urdu or Arabic earlier in the run would otherwise make these
    assertions fail on a perfectly correct dashboard.
    """

    def setUp(self):
        super().setUp()
        translation.activate("en")
        self.addCleanup(translation.activate, settings.LANGUAGE_CODE)


class RoleAwarenessTests(EnglishLabelMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.fixture = build_branch()
        build_student(self.fixture, "Dashboard Student", "D-001")

    def _board(self, user):
        return build_dashboard(user, self.fixture.branch)

    def test_a_user_without_module_access_gets_no_sections(self):
        user = build_user(self.fixture.branch, username="plain")
        board = self._board(user)
        self.assertEqual(board.kpis, [])
        self.assertEqual(board.fees, {})
        self.assertEqual(board.attendance, {})
        self.assertTrue(board.is_personal)

    def test_student_access_adds_a_student_kpi_but_no_fees(self):
        user = build_user(
            self.fixture.branch,
            username="registrar",
            permissions=["core.access_students", "students.view_student"],
        )
        board = self._board(user)
        labels = [str(k.label) for k in board.kpis]
        self.assertIn("Active students", labels)
        self.assertEqual(board.fees, {})
        self.assertTrue(board.recent_students)

    def test_fee_access_adds_fee_sections_but_no_attendance(self):
        user = build_user(
            self.fixture.branch,
            username="cashier",
            permissions=["core.access_fees", "fees.view_feeinvoice"],
        )
        board = self._board(user)
        self.assertIn("collected", board.fees)
        self.assertEqual(board.attendance, {})

    def test_quick_actions_follow_permissions(self):
        plain = build_user(self.fixture.branch, username="noactions")
        self.assertEqual(build_dashboard(plain, self.fixture.branch).quick_actions, [])

        collector = build_user(
            self.fixture.branch,
            username="collector",
            permissions=["core.access_fees", "core.collect_fee_payment"],
        )
        actions = build_dashboard(collector, self.fixture.branch).quick_actions
        labels = [str(a.label) for a in actions]
        self.assertIn("Collect fee", labels)
        self.assertNotIn("Add staff", labels)

    def test_an_admin_sees_the_operational_picture(self):
        admin = build_admin(self.fixture.branch, username="boss")
        board = build_dashboard(admin, self.fixture.branch)
        labels = [str(k.label) for k in board.kpis]
        self.assertIn("Active students", labels)
        self.assertIn("Staff", labels)
        self.assertTrue(board.quick_actions)


class BranchIsolationTests(EnglishLabelMixin, TestCase):
    """The dashboard must never total or list another branch's data."""

    def setUp(self):
        super().setUp()
        self.branch_a, self.branch_b = two_branches()
        build_student(self.branch_a, "Branch A Student", "A-900")
        build_student(self.branch_b, "Branch B Student", "B-900")
        build_student(self.branch_b, "Second B Student", "B-901")

    def test_student_counts_are_branch_scoped(self):
        user = build_user(
            self.branch_a.branch,
            username="branch_a",
            permissions=["core.access_students", "students.view_student"],
        )
        board = build_dashboard(user, self.branch_a.branch)
        kpi = next(k for k in board.kpis if str(k.label) == "Active students")
        self.assertEqual(kpi.value, 1)

    def test_recent_students_never_include_another_branch(self):
        user = build_user(
            self.branch_a.branch,
            username="branch_a2",
            permissions=["core.access_students", "students.view_student"],
        )
        board = build_dashboard(user, self.branch_a.branch)
        names = [s.full_name for s in board.recent_students]
        self.assertIn("Branch A Student", names)
        self.assertNotIn("Branch B Student", names)

    def test_the_activity_feed_is_branch_scoped(self):
        # A previous implementation filtered the feed by organization only, so
        # a single-branch user could read another branch's activity here.
        from apps.audit.services import log_activity

        log_activity(
            action="other",
            organization=self.branch_a.organization,
            branch=self.branch_a.branch,
            object_repr="Branch A event",
        )
        log_activity(
            action="other",
            organization=self.branch_b.organization,
            branch=self.branch_b.branch,
            object_repr="Branch B event",
        )

        user = build_user(
            self.branch_a.branch,
            username="auditor_a",
            permissions=["core.access_audit", "audit.view_activitylog"],
        )
        board = build_dashboard(user, self.branch_a.branch)
        reprs = [entry.object_repr for entry in board.activity]
        self.assertIn("Branch A event", reprs)
        self.assertNotIn("Branch B event", reprs)

    def test_fee_totals_are_branch_scoped(self):
        from apps.fees.services import generate_invoice

        build_fee_type(self.branch_b, "Tuition", Decimal("5000.00"))
        student_b = self.branch_b and build_student(self.branch_b, "Payer", "B-902")
        generate_invoice(
            student=student_b,
            academic_year=self.branch_b.academic_year,
            issue_date=dt.date(2026, 6, 1),
            due_date=dt.date(2026, 6, 10),
        )

        user = build_user(
            self.branch_a.branch,
            username="fees_a",
            permissions=["core.access_fees", "fees.view_feeinvoice"],
        )
        board = build_dashboard(user, self.branch_a.branch)
        self.assertEqual(board.fees["billed"], Decimal("0.00"))
        self.assertEqual(board.fees["outstanding"], Decimal("0.00"))


class RenderingTests(EnglishLabelMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.fixture = build_branch()
        build_admin(self.fixture.branch, username="viewer")
        self.client.login(username="viewer", password=PASSWORD)

    def test_the_dashboard_renders(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs attention")

    def test_an_empty_branch_shows_empty_states_not_bare_zeros(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Nothing needs attention right now.")
        self.assertContains(response, "No attendance has been marked today.")

    def test_the_dashboard_renders_in_every_language(self):
        for code in ("en", "ur", "ar"):
            with self.subTest(language=code):
                response = self.client.get(f"/{code}/dashboard/")
                self.assertEqual(response.status_code, 200)
                expected = "rtl" if code in {"ur", "ar"} else "ltr"
                self.assertContains(response, f'dir="{expected}"')

    def test_a_parent_account_is_sent_to_the_portal(self):
        from apps.core.tests.factories import build_guardian_with_portal

        student = build_student(self.fixture, "Portal Child", "P-900")
        build_guardian_with_portal(self.fixture, student, username="dash_parent")
        self.client.login(username="dash_parent", password=PASSWORD)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("parents", response.headers["Location"])
