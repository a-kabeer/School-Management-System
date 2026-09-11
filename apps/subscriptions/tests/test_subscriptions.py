"""Plan limits and usage."""

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.core.tests.factories import build_branch, build_student, build_user
from apps.subscriptions.models import FeatureUsage, Plan, Subscription
from apps.subscriptions.services import (
    current_subscription,
    expire_due_subscriptions,
    has_feature,
    plan_limits,
    record_usage,
)

TODAY = dt.date(2026, 6, 1)


class SubscriptionTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.plan = Plan.objects.create(
            name="Test Starter",
            code="test-starter",
            monthly_price=Decimal("1000.00"),
            max_branches=1,
            max_students=2,
            max_users=5,
            monthly_sms_limit=10,
            features={"hifz": True, "payroll": False},
        )
        self.subscription = Subscription.objects.create(
            organization=self.fixture.organization,
            plan=self.plan,
            start_date=TODAY,
            end_date=TODAY + dt.timedelta(days=30),
            status=Subscription.Status.ACTIVE,
        )

    def test_the_live_subscription_is_found(self):
        self.assertEqual(
            current_subscription(self.fixture.organization), self.subscription
        )

    def test_usage_is_measured_against_the_plan(self):
        build_student(self.fixture, "One", "U-1")
        usage = plan_limits(self.fixture.organization)
        students = next(r for r in usage["rows"] if r["metric"] == "students")
        self.assertEqual(students["used"], 1)
        self.assertEqual(students["limit"], 2)
        self.assertFalse(students["exceeded"])

    def test_exceeding_a_limit_is_reported(self):
        for index in range(3):
            build_student(self.fixture, f"Student {index}", f"U-{index}")
        usage = plan_limits(self.fixture.organization)
        students = next(r for r in usage["rows"] if r["metric"] == "students")
        self.assertTrue(students["exceeded"])

    def test_feature_switches_follow_the_plan(self):
        self.assertTrue(has_feature(self.fixture.organization, "hifz"))
        self.assertFalse(has_feature(self.fixture.organization, "payroll"))
        # An unlisted feature defaults to available.
        self.assertTrue(has_feature(self.fixture.organization, "exams"))

    def test_metered_usage_accumulates(self):
        record_usage(self.fixture.organization, "sms", 4, month=TODAY)
        record_usage(self.fixture.organization, "sms", 3, month=TODAY)
        usage = FeatureUsage.objects.get(metric="sms", period_month=TODAY)
        self.assertEqual(usage.used, 7)
        self.assertEqual(usage.limit, 10)
        self.assertFalse(usage.is_exceeded)

        record_usage(self.fixture.organization, "sms", 5, month=TODAY)
        usage.refresh_from_db()
        self.assertTrue(usage.is_exceeded)

    def test_a_past_subscription_expires(self):
        # The start date moves back with the end date; the check constraint
        # refuses a period that ends before it begins.
        self.subscription.start_date = TODAY - dt.timedelta(days=40)
        self.subscription.end_date = TODAY - dt.timedelta(days=1)
        self.subscription.save(update_fields=["start_date", "end_date"])

        expire_due_subscriptions(today=TODAY)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.EXPIRED)

    def test_a_period_that_ends_before_it_starts_is_refused(self):
        from django.db.utils import IntegrityError

        with self.assertRaises(IntegrityError):
            Subscription.objects.create(
                organization=build_branch().organization,
                plan=self.plan,
                start_date=TODAY,
                end_date=TODAY - dt.timedelta(days=1),
                status=Subscription.Status.ACTIVE,
            )

    def test_an_organization_has_at_most_one_live_subscription(self):
        from django.db.utils import IntegrityError

        with self.assertRaises(IntegrityError):
            Subscription.objects.create(
                organization=self.fixture.organization,
                plan=self.plan,
                start_date=TODAY,
                end_date=TODAY + dt.timedelta(days=30),
                status=Subscription.Status.ACTIVE,
            )

    def test_a_subscription_is_scoped_to_its_organization(self):
        other = build_branch()
        user = build_user(other.branch, username="other_org_user")
        self.assertEqual(
            Subscription.objects.for_user(user).filter(pk=self.subscription.pk).count(),
            0,
        )
