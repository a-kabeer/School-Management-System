"""Notification fan-out, preferences and per-user isolation."""

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import (
    build_branch,
    build_guardian_with_portal,
    build_student,
    build_user,
)
from apps.notifications.models import (
    Channel,
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)
from apps.notifications.services import mark_read, notify, unread_count

PASSWORD = "Str0ngPassphrase!42"


class NotificationDeliveryTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.alice = build_user(self.fixture.branch, username="alice")
        self.bob = build_user(self.fixture.branch, username="bob")

    def test_one_recipient_row_per_user_per_channel(self):
        notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="Holiday",
            body="School is closed on Friday.",
            users=[self.alice, self.bob],
            channels=[Channel.IN_APP, Channel.EMAIL],
        )
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(NotificationRecipient.objects.count(), 4)

    def test_an_unknown_channel_falls_back_to_the_null_backend(self):
        notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="SMS test",
            body="Body",
            users=[self.alice],
            channels=[Channel.SMS],
        )
        recipient = NotificationRecipient.objects.get(channel=Channel.SMS)
        # The null backend records the attempt without transmitting.
        self.assertIn(
            recipient.status,
            {
                NotificationRecipient.Status.SKIPPED,
                NotificationRecipient.Status.PENDING,
            },
        )

    def test_a_disabled_preference_suppresses_the_channel(self):
        NotificationPreference.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            user=self.alice,
            event="general.announcement",
            channel=Channel.IN_APP,
            is_enabled=False,
        )
        notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="Quiet",
            body="Body",
            users=[self.alice, self.bob],
            channels=[Channel.IN_APP],
        )
        self.assertFalse(
            NotificationRecipient.objects.filter(user=self.alice).exists()
        )
        self.assertTrue(NotificationRecipient.objects.filter(user=self.bob).exists())

    def test_a_template_overrides_the_default_text(self):
        NotificationTemplate.objects.create(
            organization=self.fixture.organization,
            event="general.announcement",
            channel=Channel.IN_APP,
            language="en",
            title="School notice",
            body="Dear parent, {message}",
        )
        notification = notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="Fallback title",
            body="Fallback body",
            users=[self.alice],
            channels=[Channel.IN_APP],
            context={"message": "the gate closes at 8."},
        )
        notification.refresh_from_db()
        self.assertEqual(notification.title, "School notice")
        self.assertIn("the gate closes at 8.", notification.body)

    def test_a_template_with_an_unknown_placeholder_still_delivers(self):
        NotificationTemplate.objects.create(
            organization=self.fixture.organization,
            event="general.announcement",
            channel=Channel.IN_APP,
            language="en",
            title="Notice",
            body="Hello {not_supplied}",
        )
        notification = notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="T",
            body="B",
            users=[self.alice],
            channels=[Channel.IN_APP],
        )
        self.assertIsNotNone(notification)

    def test_unread_counts_and_marking_read(self):
        notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="One",
            body="Body",
            users=[self.alice],
            channels=[Channel.IN_APP],
        )
        self.assertEqual(unread_count(self.alice), 1)
        mark_read(self.alice)
        self.assertEqual(unread_count(self.alice), 0)


class InboxTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.alice = build_user(self.fixture.branch, username="alice")
        self.bob = build_user(self.fixture.branch, username="bob")
        notify(
            branch=self.fixture.branch,
            event="general.announcement",
            title="For Alice only",
            body="Private",
            users=[self.alice],
            channels=[Channel.IN_APP],
        )

    def test_the_inbox_shows_only_the_signed_in_users_notifications(self):
        self.client.login(username="bob", password=PASSWORD)
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "For Alice only")

        self.client.login(username="alice", password=PASSWORD)
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "For Alice only")

    def test_a_user_cannot_mark_another_users_notification_read(self):
        recipient = NotificationRecipient.objects.get(user=self.alice)
        self.client.login(username="bob", password=PASSWORD)
        self.client.post(
            reverse("notifications:mark_read"), {"recipient": [str(recipient.pk)]}
        )
        recipient.refresh_from_db()
        self.assertNotEqual(recipient.status, NotificationRecipient.Status.READ)


class PaymentNotificationTests(TestCase):
    def test_a_payment_notifies_the_guardian(self):
        from decimal import Decimal

        from apps.core.tests.factories import build_fee_type
        from apps.fees.services import generate_invoice, record_payment
        from apps.finance.models import PaymentMethod

        fixture = build_branch()
        build_fee_type(fixture, "Tuition", Decimal("1000.00"))
        student = build_student(fixture)
        build_guardian_with_portal(fixture, student, username="paying_parent")

        invoice = generate_invoice(
            student=student,
            academic_year=fixture.academic_year,
            issue_date="2026-06-01",
            due_date="2026-06-10",
        )
        record_payment(
            invoice=invoice,
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.objects.get(
                branch=fixture.branch, method_type="cash"
            ),
            payment_date="2026-06-01",
        )
        self.assertTrue(
            Notification.objects.filter(event="fee.payment_received").exists()
        )
