"""Shared services: system settings and the dashboard aggregate."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import SystemSetting
from .utils import money


def get_setting(key, default=None, organization=None):
    setting = SystemSetting.objects.filter(
        key=key, organization=organization
    ).first()
    if setting is None and organization is not None:
        setting = SystemSetting.objects.filter(key=key, organization=None).first()
    return setting.value if setting else default


def set_setting(key, value, *, organization=None, description="", actor=None):
    setting, _created = SystemSetting.objects.update_or_create(
        key=key,
        organization=organization,
        defaults={"value": value, "description": description},
    )
    if actor is not None:
        from apps.audit.services import log_activity

        log_activity(
            user=actor,
            organization=organization,
            action="settings_change",
            instance=setting,
            new_values={"key": key, "value": value},
        )
    return setting


def dashboard_summary(user, branch=None):
    """Headline numbers for the dashboard, scoped to what the user may see.

    Every queryset goes through ``for_user`` so a branch administrator's
    dashboard can never total another branch's money.
    """
    from apps.attendance.models import StudentAttendance
    from apps.fees.models import FeeInvoice, FeePayment
    from apps.staff.models import Staff
    from apps.students.models import Student

    today = timezone.localdate()
    month_start = today.replace(day=1)

    students = Student.objects.for_user(user, branch)
    staff = Staff.objects.for_user(user, branch)
    invoices = FeeInvoice.objects.for_user(user, branch)
    payments = FeePayment.objects.for_user(user, branch).filter(is_void=False)
    attendance = StudentAttendance.objects.for_user(user, branch).filter(date=today)

    student_counts = students.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
    )
    invoice_totals = invoices.exclude(status=FeeInvoice.Status.CANCELLED).aggregate(
        billed=Sum("total_amount"),
        paid=Sum("paid_amount"),
    )
    billed = money(invoice_totals["billed"])
    paid = money(invoice_totals["paid"])

    attendance_counts = attendance.aggregate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        leave=Count("id", filter=Q(status="leave")),
    )
    marked = sum(v or 0 for v in attendance_counts.values())

    return {
        "students_total": student_counts["total"] or 0,
        "students_active": student_counts["active"] or 0,
        "staff_total": staff.count(),
        "fees_billed": billed,
        "fees_collected": paid,
        "fees_outstanding": money(billed - paid),
        "collected_this_month": money(
            payments.filter(payment_date__gte=month_start).aggregate(
                total=Sum("amount")
            )["total"]
        ),
        "collected_today": money(
            payments.filter(payment_date=today).aggregate(total=Sum("amount"))["total"]
        ),
        "attendance_present": attendance_counts["present"] or 0,
        "attendance_absent": attendance_counts["absent"] or 0,
        "attendance_late": attendance_counts["late"] or 0,
        "attendance_leave": attendance_counts["leave"] or 0,
        "attendance_marked": marked,
        "attendance_rate": (
            Decimal(attendance_counts["present"] or 0) * 100 / marked
            if marked
            else Decimal("0")
        ).quantize(Decimal("0.1")),
        "today": today,
    }


def recent_activity(user, branch=None, limit=8):
    from apps.audit.models import ActivityLog

    queryset = ActivityLog.objects.select_related("user", "branch")
    if not user.is_superuser:
        queryset = queryset.filter(organization_id=user.organization_id)
        if branch is not None:
            queryset = queryset.filter(branch=branch)
    return queryset.order_by("-created_at")[:limit]


def collection_trend(user, branch=None, days=14):
    """Daily collected totals for the dashboard chart."""
    from apps.fees.models import FeePayment

    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = (
        FeePayment.objects.for_user(user, branch)
        .filter(is_void=False, payment_date__gte=start)
        .values("payment_date")
        .annotate(total=Sum("amount"))
    )
    by_date = {row["payment_date"]: money(row["total"]) for row in rows}
    return [
        {"date": start + timedelta(days=offset),
         "total": by_date.get(start + timedelta(days=offset), Decimal("0.00"))}
        for offset in range(days)
    ]
