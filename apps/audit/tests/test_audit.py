"""The audit trail: what it records, and that it cannot be rewritten."""

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import ActivityLog
from apps.audit.services import log_activity, snapshot
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_fee_type,
    build_student,
    build_user,
    two_branches,
)

PASSWORD = "Str0ngPassphrase!42"
ISSUE = dt.date(2026, 6, 1)


class AuditWritingTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.user = build_user(self.fixture.branch, username="actor")

    def test_a_payment_is_logged(self):
        from apps.fees.services import generate_invoice, record_payment
        from apps.finance.models import PaymentMethod

        build_fee_type(self.fixture, "Tuition", Decimal("1000.00"))
        student = build_student(self.fixture)
        invoice = generate_invoice(
            student=student,
            academic_year=self.fixture.academic_year,
            issue_date=ISSUE,
            due_date=ISSUE,
            actor=self.user,
        )
        record_payment(
            invoice=invoice,
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.objects.get(
                branch=self.fixture.branch, method_type="cash"
            ),
            payment_date=ISSUE,
            actor=self.user,
        )

        entry = ActivityLog.objects.filter(action="payment").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user_id, self.user.pk)
        self.assertEqual(entry.branch_id, self.fixture.branch.pk)
        self.assertEqual(entry.new_values["amount"], "500.00")

    def test_a_student_admission_is_logged(self):
        student = build_student(self.fixture)
        entry = ActivityLog.objects.filter(
            model_name="student", object_id=str(student.pk)
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, "create")

    def test_a_login_is_logged(self):
        build_admin(self.fixture.branch, username="loginner")
        self.client.post(
            reverse("accounts:login"), {"username": "loginner", "password": PASSWORD}
        )
        self.assertTrue(ActivityLog.objects.filter(action="login").exists())

    def test_a_failed_login_is_logged(self):
        build_admin(self.fixture.branch, username="loginner")
        self.client.post(
            reverse("accounts:login"), {"username": "loginner", "password": "nope"}
        )
        entry = ActivityLog.objects.filter(action="login_failed").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.metadata.get("username"), "loginner")

    def test_a_refused_page_is_logged(self):
        build_user(self.fixture.branch, username="nosy")
        self.client.login(username="nosy", password=PASSWORD)
        self.client.get(reverse("fees:invoice_list"))
        self.assertTrue(ActivityLog.objects.filter(action="access_denied").exists())

    def test_a_branch_switch_is_logged(self):
        from apps.accounts.rbac import grant_branch_access

        branch_a, branch_b = two_branches()
        user = build_user(branch_a.branch, username="mover")
        grant_branch_access(user, branch_b.branch)
        self.client.login(username="mover", password=PASSWORD)
        self.client.post(
            reverse("tenants:switch_branch"), {"branch": str(branch_b.branch.pk)}
        )
        self.assertTrue(ActivityLog.objects.filter(action="branch_change").exists())

    def test_passwords_are_redacted_from_snapshots(self):
        data = snapshot(self.user)
        self.assertEqual(data["password"], "***")

    def test_logging_never_raises_into_the_caller(self):
        # A bad payload must not take the business operation down with it.
        result = log_activity(action="other", metadata={"bad": object()})
        self.assertTrue(result is None or isinstance(result, ActivityLog))


class AuditImmutabilityTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.entry = log_activity(
            action="other",
            user=build_user(self.fixture.branch, username="writer"),
            organization=self.fixture.organization,
            branch=self.fixture.branch,
        )

    def test_an_entry_cannot_be_edited(self):
        self.entry.action = "create"
        with self.assertRaises(ValueError):
            self.entry.save()

    def test_an_entry_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            self.entry.delete()

    def test_the_queryset_refuses_bulk_changes(self):
        with self.assertRaises(NotImplementedError):
            ActivityLog.objects.all().delete()
        with self.assertRaises(NotImplementedError):
            ActivityLog.objects.all().update(action="create")

    def test_the_model_exposes_no_change_permissions(self):
        from django.contrib.auth.models import Permission

        codenames = set(
            Permission.objects.filter(
                content_type__app_label="audit", content_type__model="activitylog"
            ).values_list("codename", flat=True)
        )
        self.assertEqual(codenames, {"view_activitylog"})


class AuditVisibilityTests(TestCase):
    def test_the_log_is_scoped_to_the_users_branches(self):
        branch_a, branch_b = two_branches()
        user_a = build_user(branch_a.branch, username="reader_a")

        log_activity(
            action="other",
            organization=branch_a.organization,
            branch=branch_a.branch,
            object_repr="Branch A event",
        )
        log_activity(
            action="other",
            organization=branch_b.organization,
            branch=branch_b.branch,
            object_repr="Branch B event",
        )

        visible = ActivityLog.objects.for_user(user_a)
        reprs = set(visible.values_list("object_repr", flat=True))
        self.assertIn("Branch A event", reprs)
        self.assertNotIn("Branch B event", reprs)

    def test_the_audit_page_needs_its_permission(self):
        fixture = build_branch()
        build_user(fixture.branch, username="curious")
        self.client.login(username="curious", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("audit:list")).status_code, 403)

        build_user(
            fixture.branch,
            username="auditor",
            permissions=["core.access_audit", "audit.view_activitylog"],
            role_name="Auditor",
        )
        self.client.login(username="auditor", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("audit:list")).status_code, 200)
