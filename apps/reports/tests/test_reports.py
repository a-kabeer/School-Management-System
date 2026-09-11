"""Reports respect permissions, tenancy and the export gate."""

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    build_branch,
    build_fee_type,
    build_student,
    build_user,
    two_branches,
)
from apps.reports.models import ReportExport
from apps.reports.registry import REGISTRY, available_reports

PASSWORD = "Str0ngPassphrase!42"
ISSUE = dt.date(2026, 6, 1)


class ReportVisibilityTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()

    def test_only_permitted_reports_are_listed(self):
        user = build_user(
            self.fixture.branch,
            username="fees_only",
            permissions=["core.access_reports", "core.access_fees"],
        )
        keys = {report.key for report in available_reports(user, self.fixture.branch)}
        self.assertIn("fee_collection", keys)
        self.assertNotIn("payroll", keys)
        self.assertNotIn("students", keys)

    def test_opening_a_report_without_its_permission_is_refused(self):
        build_user(
            self.fixture.branch,
            username="reader",
            permissions=["core.access_reports"],
        )
        self.client.login(username="reader", password=PASSWORD)
        response = self.client.get(reverse("reports:detail", args=["payroll"]))
        self.assertEqual(response.status_code, 403)

    def test_an_unknown_report_key_is_a_404(self):
        build_user(
            self.fixture.branch,
            username="reader2",
            permissions=["core.access_reports"],
        )
        self.client.login(username="reader2", password=PASSWORD)
        response = self.client.get(reverse("reports:detail", args=["not-a-report"]))
        self.assertEqual(response.status_code, 404)

    def test_every_registered_report_builds_without_error(self):
        user = build_user(
            self.fixture.branch, username="super", is_superuser=True
        )
        build_fee_type(self.fixture, "Tuition", Decimal("1000.00"))
        build_student(self.fixture)

        for key, definition in REGISTRY.items():
            with self.subTest(report=key):
                data = definition.builder(
                    user,
                    None if definition.organization_wide else self.fixture.branch,
                    {"date_from": None, "date_to": None, "status": ""},
                )
                self.assertIn("headers", data)
                self.assertIn("rows", data)


class ReportScopingTests(TestCase):
    def test_a_report_never_reaches_another_branch(self):
        branch_a, branch_b = two_branches()
        build_student(branch_a, "Visible Student", "A-700")
        build_student(branch_b, "Hidden Student", "B-700")

        user_a = build_user(
            branch_a.branch,
            username="report_a",
            permissions=["core.access_reports", "core.access_students"],
        )
        self.client.login(username="report_a", password=PASSWORD)
        response = self.client.get(reverse("reports:detail", args=["students"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Student")
        self.assertNotContains(response, "Hidden Student")


class ReportExportTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        build_student(self.fixture)

    def test_exporting_requires_the_export_permission(self):
        build_user(
            self.fixture.branch,
            username="no_export",
            permissions=["core.access_reports", "core.access_students"],
        )
        self.client.login(username="no_export", password=PASSWORD)
        response = self.client.get(
            reverse("reports:detail", args=["students"]), {"export": "xlsx"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReportExport.objects.count(), 0)

    def test_an_allowed_export_returns_a_spreadsheet_and_is_recorded(self):
        build_user(
            self.fixture.branch,
            username="exporter",
            permissions=[
                "core.access_reports",
                "core.access_students",
                "core.export_report",
            ],
        )
        self.client.login(username="exporter", password=PASSWORD)
        response = self.client.get(
            reverse("reports:detail", args=["students"]), {"export": "xlsx"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(ReportExport.objects.count(), 1)

    def test_an_export_is_written_to_the_audit_log(self):
        from apps.audit.models import ActivityLog

        build_user(
            self.fixture.branch,
            username="exporter2",
            permissions=[
                "core.access_reports",
                "core.access_students",
                "core.export_report",
            ],
        )
        self.client.login(username="exporter2", password=PASSWORD)
        self.client.get(
            reverse("reports:detail", args=["students"]), {"export": "xlsx"}
        )
        self.assertTrue(ActivityLog.objects.filter(action="export").exists())
