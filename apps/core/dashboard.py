"""Role-aware dashboard assembly.

The dashboard answers three questions in order: what is happening, what needs
attention, and what can I do next. Which of those a user sees is decided by the
permissions they hold - not by their role name - so a new role gets a sensible
dashboard without any change here.

Every section is computed only when the user can actually open it. A teacher's
dashboard runs no fee queries at all, which keeps the page cheap as well as
correct.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .permissions import user_has_permission
from .utils import money

ZERO = Decimal("0.00")


# --------------------------------------------------------------------------
# Small value objects the template renders
# --------------------------------------------------------------------------
@dataclass
class Kpi:
    label: str
    value: object
    hint: str = ""
    icon: str = "•"
    url: str = ""
    tone: str = "secondary"


@dataclass
class Attention:
    """One actionable item. ``count`` of zero is never shown."""

    label: str
    count: int
    description: str
    url: str = ""
    action: str = ""
    tone: str = "warning"


@dataclass
class Action:
    label: str
    url: str
    icon: str = "+"


@dataclass
class Dashboard:
    kpis: list = field(default_factory=list)
    attention: list = field(default_factory=list)
    quick_actions: list = field(default_factory=list)
    attendance: dict = field(default_factory=dict)
    fees: dict = field(default_factory=dict)
    trend: list = field(default_factory=list)
    trend_max: Decimal = Decimal("1")
    academics: dict = field(default_factory=dict)
    recent_students: list = field(default_factory=list)
    recent_payments: list = field(default_factory=list)
    hifz: dict = field(default_factory=dict)
    activity: list = field(default_factory=list)
    academic_year: object = None
    is_personal: bool = False


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def build_dashboard(user, branch):
    """Assemble everything the dashboard shows for this user, in this branch."""
    board = Dashboard()
    today = timezone.localdate()

    def can(permission):
        return user_has_permission(user, permission, branch)

    board.academic_year = _current_year(user, branch)

    if can("core.access_students"):
        _students(board, user, branch, today)
    if can("core.access_staff"):
        _staff(board, user, branch)
    if can("core.access_attendance"):
        _attendance(board, user, branch, today)
    if can("core.access_fees"):
        _fees(board, user, branch, today)
    if can("core.access_exams"):
        _exams(board, user, branch, today)
    if can("core.access_hifz"):
        _hifz(board, user, branch, today)
    if can("core.access_academics"):
        _timetable(board, user, branch, today)
    if can("core.access_parents"):
        _parent_requests(board, user, branch)

    _notifications(board, user)
    _quick_actions(board, can)

    if can("core.access_audit"):
        board.activity = _activity(user, branch)

    # Nothing to show means this is a self-service account (a Student role, or
    # a new user with only dashboard access). Say so rather than rendering an
    # empty grid.
    board.is_personal = not (board.kpis or board.attention)
    return board


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------
def _current_year(user, branch):
    from apps.academics.models import AcademicYear

    return (
        AcademicYear.objects.for_user(user, branch)
        .filter(is_current=True)
        .order_by("-start_date")
        .first()
    )


def _students(board, user, branch, today):
    from apps.students.models import Student

    students = Student.objects.for_user(user, branch)
    counts = students.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
        joined_30d=Count(
            "id", filter=Q(admission_date__gte=today - dt.timedelta(days=30))
        ),
    )
    board.kpis.append(
        Kpi(
            label=_("Active students"),
            value=counts["active"] or 0,
            hint=_("%(n)s on the register") % {"n": counts["total"] or 0},
            icon="👥",
            url=_url("students:student_list"),
            tone="primary",
        )
    )

    if counts["joined_30d"]:
        board.kpis.append(
            Kpi(
                label=_("Admissions, 30 days"),
                value=counts["joined_30d"],
                icon="🆕",
                url=_url("students:student_list"),
                tone="info",
            )
        )

    # current_class_display walks the student's enrollments, so prefetch them:
    # without this the six-row table costs six extra queries.
    from django.db.models import Prefetch

    from apps.students.models import StudentEnrollment

    board.recent_students = list(
        students.filter(status=Student.Status.ACTIVE)
        .select_related("branch")
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=StudentEnrollment.objects.filter(is_current=True)
                .select_related("school_class", "section"),
            )
        )
        .order_by("-created_at")[:6]
    )


def _staff(board, user, branch):
    from apps.staff.models import Staff

    counts = Staff.objects.for_user(user, branch).aggregate(
        total=Count("id"),
        teaching=Count("id", filter=Q(staff_type=Staff.StaffType.TEACHER)),
    )
    board.kpis.append(
        Kpi(
            label=_("Staff"),
            value=counts["total"] or 0,
            hint=_("%(n)s teaching") % {"n": counts["teaching"] or 0},
            icon="🧑‍🏫",
            url=_url("staff:staff_list"),
            tone="secondary",
        )
    )


def _attendance(board, user, branch, today):
    from apps.academics.models import Section
    from apps.attendance.models import AttendanceSession, StudentAttendance
    from apps.core.constants import AttendanceStatus

    counts = (
        StudentAttendance.objects.for_user(user, branch)
        .filter(date=today)
        .aggregate(
            present=Count("id", filter=Q(status=AttendanceStatus.PRESENT)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
            late=Count("id", filter=Q(status=AttendanceStatus.LATE)),
            leave=Count("id", filter=Q(status=AttendanceStatus.LEAVE)),
            excused=Count("id", filter=Q(status=AttendanceStatus.EXCUSED)),
        )
    )
    marked = sum(v or 0 for v in counts.values())
    rate = (
        (Decimal(counts["present"] or 0) * 100 / marked).quantize(Decimal("0.1"))
        if marked
        else None
    )

    board.attendance = {
        "marked": marked,
        "rate": rate,
        "rows": [
            (_("Present"), counts["present"] or 0, "success"),
            (_("Absent"), counts["absent"] or 0, "danger"),
            (_("Late"), counts["late"] or 0, "warning"),
            (_("Leave"), counts["leave"] or 0, "info"),
            (_("Excused"), counts["excused"] or 0, "secondary"),
        ],
        "url": _url("attendance:record_list"),
        "mark_url": _url("attendance:mark"),
    }

    if marked:
        board.kpis.append(
            Kpi(
                label=_("Attendance today"),
                value=f"{rate}%",
                hint=_("%(n)s marked") % {"n": marked},
                icon="✅",
                url=_url("attendance:session_list"),
                tone="success" if rate and rate >= 90 else "warning",
            )
        )

    if counts["absent"]:
        board.attention.append(
            Attention(
                label=_("Students absent today"),
                count=counts["absent"],
                description=_("Follow up with their families."),
                url=f"{_url('attendance:record_list')}?status=absent",
                action=_("Review"),
                tone="danger",
            )
        )

    # Sections with students enrolled but no register taken today.
    taken = set(
        AttendanceSession.objects.for_user(user, branch)
        .filter(date=today)
        .values_list("section_id", flat=True)
    )
    expected = set(
        Section.objects.for_user(user, branch)
        .filter(is_active=True, enrollments__is_current=True)
        .values_list("id", flat=True)
    )
    missing = len(expected - taken)
    if missing:
        board.attention.append(
            Attention(
                label=_("Registers not taken"),
                count=missing,
                description=_("Sections with no attendance recorded today."),
                url=_url("attendance:mark"),
                action=_("Mark"),
                tone="warning",
            )
        )


def _fees(board, user, branch, today):
    from apps.fees.models import FeeInvoice, FeePayment

    month_start = today.replace(day=1)
    # Deliberately not scoped to the current academic year: an unpaid invoice
    # from last year is still money owed today, and hiding it would understate
    # what the desk has to chase. Collections below are date-scoped instead.
    invoices = FeeInvoice.objects.for_user(user, branch).exclude(
        status=FeeInvoice.Status.CANCELLED
    )

    totals = invoices.aggregate(
        billed=Sum("total_amount"),
        paid=Sum("paid_amount"),
        waived=Sum("waiver_amount"),
    )
    billed = money(totals["billed"])
    collected = money(totals["paid"])
    waived = money(totals["waived"])
    outstanding = money(billed - collected - waived)

    payments = FeePayment.objects.for_user(user, branch).filter(is_void=False)
    period = payments.aggregate(
        today=Sum("amount", filter=Q(payment_date=today)),
        month=Sum("amount", filter=Q(payment_date__gte=month_start)),
    )

    board.fees = {
        "billed": billed,
        "collected": collected,
        "waived": waived,
        "outstanding": outstanding,
        "today": money(period["today"]),
        "month": money(period["month"]),
        "rate": (
            (collected * 100 / billed).quantize(Decimal("0.1")) if billed else None
        ),
        "invoice_url": _url("fees:invoice_list"),
        "payment_url": _url("fees:payment_list"),
        "collect_url": _url("fees:payment_create"),
    }

    board.kpis.append(
        Kpi(
            label=_("Collected this month"),
            value=money(period["month"]),
            hint=_("%(n)s today") % {"n": money(period["today"])},
            icon="💰",
            url=_url("fees:payment_list"),
            tone="success",
        )
    )
    board.kpis.append(
        Kpi(
            label=_("Outstanding fees"),
            value=outstanding,
            hint=_("of %(n)s billed") % {"n": billed},
            icon="📄",
            url=_url("fees:invoice_list"),
            tone="warning",
        )
    )

    overdue = invoices.filter(
        due_date__lt=today,
        status__in=[FeeInvoice.Status.ISSUED, FeeInvoice.Status.PARTIALLY_PAID,
                    FeeInvoice.Status.OVERDUE],
    ).aggregate(
        count=Count("id"),
        due=Sum(F("total_amount") - F("paid_amount") - F("waiver_amount")),
    )
    if overdue["count"]:
        board.attention.append(
            Attention(
                label=_("Overdue invoices"),
                count=overdue["count"],
                description=_("%(amount)s past its due date.")
                % {"amount": money(overdue["due"])},
                url=f"{_url('fees:invoice_list')}?status=overdue",
                action=_("Collect"),
                tone="danger",
            )
        )

    board.recent_payments = list(
        payments.select_related("student", "payment_method")
        .order_by("-payment_date", "-created_at")[:6]
    )
    board.trend = _collection_trend(payments, today)
    board.trend_max = max([row["total"] for row in board.trend] or [ZERO]) or Decimal("1")


def _collection_trend(payments, today, days=14):
    start = today - dt.timedelta(days=days - 1)
    rows = (
        payments.filter(payment_date__gte=start)
        .values("payment_date")
        .annotate(total=Sum("amount"))
    )
    by_date = {row["payment_date"]: money(row["total"]) for row in rows}
    return [
        {
            "date": start + dt.timedelta(days=offset),
            "total": by_date.get(start + dt.timedelta(days=offset), ZERO),
        }
        for offset in range(days)
    ]


def _exams(board, user, branch, today):
    from apps.exams.models import Exam, ExamSubject

    exams = Exam.objects.for_user(user, branch).select_related("school_class", "exam_term")

    upcoming = list(
        exams.filter(
            start_date__gte=today,
            status__in=[Exam.Status.PLANNED, Exam.Status.ONGOING],
        ).order_by("start_date")[:5]
    )
    published = list(
        exams.filter(status=Exam.Status.PUBLISHED)
        .order_by("-published_at")[:4]
    )

    # A paper is outstanding when fewer marks exist than students registered.
    pending = (
        ExamSubject.objects.for_user(user, branch)
        .filter(
            exam__status__in=[
                Exam.Status.PLANNED, Exam.Status.ONGOING, Exam.Status.MARKING
            ]
        )
        .annotate(
            entered=Count("marks", distinct=True),
            registered=Count("exam__student_exams", distinct=True),
        )
        .filter(registered__gt=0, entered__lt=F("registered"))
    )
    pending_count = pending.count()

    board.academics.update(
        {
            "upcoming_exams": upcoming,
            "published_exams": published,
            "pending_marks": pending_count,
            "exam_url": _url("exams:exam_list"),
            "result_url": _url("exams:result_list"),
        }
    )

    if upcoming:
        board.kpis.append(
            Kpi(
                label=_("Upcoming exams"),
                value=len(upcoming),
                hint=_("next on %(d)s") % {"d": upcoming[0].start_date},
                icon="📝",
                url=_url("exams:exam_list"),
                tone="info",
            )
        )

    if pending_count and user_has_permission(user, "exams.add_mark", branch):
        board.attention.append(
            Attention(
                label=_("Papers awaiting marks"),
                count=pending_count,
                description=_("Marks have not been entered for every student."),
                url=_url("exams:exam_list"),
                action=_("Enter marks"),
                tone="warning",
            )
        )


def _hifz(board, user, branch, today):
    from apps.hifz.models import DailyProgress, HifzStudentProfile, LessonType, Revision

    profiles = HifzStudentProfile.objects.for_user(user, branch).filter(is_active=True)
    total = profiles.count()
    if not total:
        return

    heard_today = (
        DailyProgress.objects.for_user(user, branch)
        .filter(date=today, lesson_type=LessonType.SABAQ)
        .values("hifz_profile_id")
        .distinct()
        .count()
    )
    overdue_revisions = (
        Revision.objects.for_user(user, branch)
        .filter(
            scheduled_date__lt=today,
            status__in=[Revision.Status.PLANNED, Revision.Status.IN_PROGRESS],
        )
        .count()
    )

    board.hifz = {
        "students": total,
        "heard_today": heard_today,
        "not_heard": max(total - heard_today, 0),
        "overdue_revisions": overdue_revisions,
        "profile_url": _url("hifz:profile_list"),
        "progress_url": _url("hifz:progress_list"),
        "revision_url": _url("hifz:revision_list"),
    }

    board.kpis.append(
        Kpi(
            label=_("Hifz students"),
            value=total,
            hint=_("%(n)s heard today") % {"n": heard_today},
            icon="📖",
            url=_url("hifz:profile_list"),
            tone="info",
        )
    )

    if overdue_revisions:
        board.attention.append(
            Attention(
                label=_("Revisions overdue"),
                count=overdue_revisions,
                description=_("Scheduled Manzil that has not been heard."),
                url=_url("hifz:revision_list"),
                action=_("Review"),
                tone="warning",
            )
        )


def _timetable(board, user, branch, today):
    from apps.academics.models import Timetable

    slots = (
        Timetable.objects.for_user(user, branch)
        .filter(weekday=today.weekday())
        .select_related(
            "section__school_class", "class_subject__subject", "teacher"
        )
        .order_by("period")
    )

    # A teacher sees their own day; anyone else sees the branch's day.
    staff = getattr(user, "staff_profile", None)
    mine = bool(staff) and slots.filter(teacher=staff).exists()
    if mine:
        slots = slots.filter(teacher=staff)

    board.academics["today_slots"] = list(slots[:8])
    board.academics["today_is_mine"] = mine
    board.academics["timetable_url"] = _url("academics:timetable_list")


def _parent_requests(board, user, branch):
    from apps.parents.models import ParentRequest

    open_requests = (
        ParentRequest.objects.for_user(user, branch)
        .filter(status__in=[ParentRequest.Status.OPEN, ParentRequest.Status.IN_REVIEW])
        .count()
    )
    if open_requests:
        board.attention.append(
            Attention(
                label=_("Parent requests"),
                count=open_requests,
                description=_("Leave applications and queries awaiting a reply."),
                url=_url("parents:request_list"),
                action=_("Respond"),
                tone="info",
            )
        )


def _notifications(board, user):
    from apps.notifications.services import unread_count

    unread = unread_count(user)
    if unread:
        board.attention.append(
            Attention(
                label=_("Unread notifications"),
                count=unread,
                description=_("Messages waiting in your inbox."),
                url=_url("notifications:list"),
                action=_("Open"),
                tone="info",
            )
        )


def _quick_actions(board, can):
    candidates = [
        ("students.add_student", _("Add student"), "students:student_create", "👤"),
        ("attendance.add_studentattendance", _("Mark attendance"), "attendance:mark", "✅"),
        ("core.collect_fee_payment", _("Collect fee"), "fees:payment_create", "💰"),
        ("fees.add_feeinvoice", _("Generate invoices"), "fees:invoice_generate", "📄"),
        ("staff.add_staff", _("Add staff"), "staff:staff_create", "🧑‍🏫"),
        ("exams.add_exam", _("Create exam"), "exams:exam_create", "📝"),
        ("hifz.add_dailyprogress", _("Record Hifz"), "hifz:progress_create", "📖"),
        ("core.access_reports", _("Reports"), "reports:index", "📊"),
    ]
    for permission, label, url_name, icon in candidates:
        if not can(permission):
            continue
        url = _url(url_name)
        if url:
            board.quick_actions.append(Action(label=label, url=url, icon=icon))


def _activity(user, branch, limit=8):
    from apps.audit.models import ActivityLog

    # for_user() restricts to the branches this user may enter. The previous
    # implementation filtered only by organization, so a single-branch user
    # could read another branch's activity from the dashboard.
    return list(
        ActivityLog.objects.for_user(user, branch)
        .select_related("user", "branch")
        .order_by("-created_at")[:limit]
    )
