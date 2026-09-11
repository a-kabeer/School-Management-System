"""Seed the platform-level data a fresh install needs.

This writes configuration only - plans and system settings. It never creates
business records, so it is safe to run against a live database.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import SystemSetting
from apps.subscriptions.models import Plan

PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "One branch, up to 200 students.",
        "monthly_price": Decimal("2500.00"),
        "yearly_price": Decimal("25000.00"),
        "max_branches": 1,
        "max_students": 200,
        "max_users": 10,
        "storage_limit_mb": 2048,
        "monthly_sms_limit": 0,
        "monthly_whatsapp_limit": 0,
        "features": {"hifz": True, "payroll": False, "finance": True},
        "sort_order": 1,
    },
    {
        "code": "standard",
        "name": "Standard",
        "description": "Up to three branches with payroll.",
        "monthly_price": Decimal("6000.00"),
        "yearly_price": Decimal("60000.00"),
        "max_branches": 3,
        "max_students": 1000,
        "max_users": 40,
        "storage_limit_mb": 10240,
        "monthly_sms_limit": 1000,
        "monthly_whatsapp_limit": 500,
        "features": {"hifz": True, "payroll": True, "finance": True},
        "sort_order": 2,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Unlimited branches and students.",
        "monthly_price": Decimal("15000.00"),
        "yearly_price": Decimal("150000.00"),
        "max_branches": None,
        "max_students": None,
        "max_users": None,
        "storage_limit_mb": None,
        "monthly_sms_limit": 10000,
        "monthly_whatsapp_limit": 10000,
        "features": {"hifz": True, "payroll": True, "finance": True},
        "sort_order": 3,
    },
]

SETTINGS = [
    ("invoice_due_days", {"value": 10}, "Default days between issue and due date."),
    ("attendance_lock_after_days", {"value": 7}, "Days before a register locks."),
    ("academic_year_start_month", {"value": 4}, "Month a new academic year starts."),
    ("currency_symbol", {"value": "Rs"}, "Symbol shown beside money amounts."),
]


class Command(BaseCommand):
    help = "Seed subscription plans and baseline system settings."

    @transaction.atomic
    def handle(self, *args, **options):
        created_plans = 0
        for plan in PLANS:
            _obj, created = Plan.objects.get_or_create(
                code=plan["code"], defaults=plan
            )
            created_plans += 1 if created else 0

        created_settings = 0
        for key, value, description in SETTINGS:
            _obj, created = SystemSetting.objects.get_or_create(
                key=key,
                organization=None,
                defaults={"value": value, "description": description},
            )
            created_settings += 1 if created else 0

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_plans} plans and {created_settings} settings."
            )
        )
