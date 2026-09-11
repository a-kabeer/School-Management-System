"""The report catalogue.

Each report is a builder function returning headers and rows. Every builder
takes ``user`` and ``branch`` and must scope its queryset through ``for_user``,
so a report can never widen what its caller is allowed to see.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class ReportDefinition:
    key: str
    label: str
    description: str
    permission: str
    builder: Callable
    #: Filters this report understands, drawn from the shared filter bar.
    filters: tuple = field(default_factory=tuple)
    #: True when the report reads across every branch the user may see.
    organization_wide: bool = False


REGISTRY: dict[str, ReportDefinition] = {}


def register(definition):
    REGISTRY[definition.key] = definition
    return definition


def available_reports(user, branch=None):
    """Only the reports this user is allowed to open."""
    from apps.core.permissions import user_has_permission

    return [
        definition
        for definition in REGISTRY.values()
        if user_has_permission(user, definition.permission, branch)
    ]


def get_report(key):
    return REGISTRY.get(key)


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------
def _students_report(user, branch, params):
    from apps.students.selectors import students_for

    queryset = students_for(user, branch)
    status = params.get("status")
    if status:
        queryset = queryset.filter(status=status)

    rows = [
        (
            student.admission_no,
            student.full_name,
            student.father_name,
            student.get_gender_display() if student.gender else "",
            student.current_class_display,
            student.branch.name,
            student.get_status_display(),
            student.admission_date,
        )
        for student in queryset.select_related("branch")
    ]
    return {
        "headers": [
            _("Admission #"), _("Name"), _("Father"), _("Gender"),
            _("Class"), _("Branch"), _("Status"), _("Admitted"),
        ],
        "rows": rows,
    }


def _attendance_report(user, branch, params):
    from django.db.models import Count, Q

    from apps.core.constants import AttendanceStatus
    from apps.students.models import Student

    queryset = Student.objects.for_user(user, branch).filter(
        status=Student.Status.ACTIVE
    )
    date_from, date_to = params.get("date_from"), params.get("date_to")

    attendance_filter = Q()
    if date_from:
        attendance_filter &= Q(attendance_records__date__gte=date_from)
    if date_to:
        attendance_filter &= Q(attendance_records__date__lte=date_to)

    queryset = queryset.annotate(
        total=Count("attendance_records", filter=attendance_filter),
        present=Count(
            "attendance_records",
            filter=attendance_filter
            & Q(attendance_records__status=AttendanceStatus.PRESENT),
        ),
        absent=Count(
            "attendance_records",
            filter=attendance_filter
            & Q(attendance_records__status=AttendanceStatus.ABSENT),
        ),
        late=Count(
            "attendance_records",
            filter=attendance_filter
            & Q(attendance_records__status=AttendanceStatus.LATE),
        ),
    ).select_related("branch")

    rows = []
    for student in queryset:
        percentage = (
            round(student.present / student.total * 100, 1) if student.total else 0
        )
        rows.append(
            (
                student.admission_no,
                student.full_name,
                student.current_class_display,
                student.total,
                student.present,
                student.absent,
                student.late,
                percentage,
            )
        )
    return {
        "headers": [
            _("Admission #"), _("Name"), _("Class"), _("Marked"),
            _("Present"), _("Absent"), _("Late"), _("Attendance %"),
        ],
        "rows": rows,
    }


def _fee_collection_report(user, branch, params):
    from apps.fees.models import FeePayment

    queryset = FeePayment.objects.for_user(user, branch).filter(is_void=False)
    if params.get("date_from"):
        queryset = queryset.filter(payment_date__gte=params["date_from"])
    if params.get("date_to"):
        queryset = queryset.filter(payment_date__lte=params["date_to"])

    rows = [
        (
            payment.receipt_number,
            payment.payment_date,
            payment.student.full_name,
            payment.invoice.invoice_number,
            payment.payment_method.name,
            payment.amount,
            payment.branch.name,
            payment.received_by.display_name if payment.received_by else "",
        )
        for payment in queryset.select_related(
            "student", "invoice", "payment_method", "branch", "received_by"
        )
    ]
    total = sum((row[5] for row in rows), Decimal("0.00"))
    return {
        "headers": [
            _("Receipt #"), _("Date"), _("Student"), _("Invoice"),
            _("Method"), _("Amount"), _("Branch"), _("Received By"),
        ],
        "rows": rows,
        "totals": {5: total},
    }


def _fee_outstanding_report(user, branch, params):
    from apps.fees.services import defaulters

    rows = [
        (
            invoice.invoice_number,
            invoice.student.admission_no,
            invoice.student.full_name,
            invoice.due_date,
            invoice.total_amount,
            invoice.paid_amount,
            invoice.balance,
            invoice.get_status_display(),
        )
        for invoice in defaulters(user, branch)
    ]
    total = sum((row[6] for row in rows), Decimal("0.00"))
    return {
        "headers": [
            _("Invoice #"), _("Admission #"), _("Student"), _("Due"),
            _("Total"), _("Paid"), _("Balance"), _("Status"),
        ],
        "rows": rows,
        "totals": {6: total},
    }


def _finance_trial_balance_report(user, branch, params):
    from apps.finance.services import trial_balance

    report = trial_balance(
        user, branch, date_from=params.get("date_from"), date_to=params.get("date_to")
    )
    rows = [
        (r["code"], r["name"], r["nature"], r["debit"], r["credit"], r["balance"])
        for r in report["rows"]
    ]
    return {
        "headers": [
            _("Code"), _("Account"), _("Nature"), _("Debit"), _("Credit"), _("Balance"),
        ],
        "rows": rows,
        "totals": {3: report["total_debit"], 4: report["total_credit"]},
        "meta": {"balanced": report["is_balanced"]},
    }


def _payroll_report(user, branch, params):
    from apps.payroll.models import PayrollItem

    queryset = PayrollItem.objects.for_user(user, branch).select_related(
        "staff", "run__period", "branch"
    )
    if params.get("date_from"):
        queryset = queryset.filter(run__run_date__gte=params["date_from"])
    if params.get("date_to"):
        queryset = queryset.filter(run__run_date__lte=params["date_to"])

    rows = [
        (
            item.run.reference,
            item.run.period.name,
            item.staff.employee_no,
            item.staff.full_name,
            item.basic_salary,
            item.total_allowances,
            item.total_deductions,
            item.net_salary,
            item.branch.name,
        )
        for item in queryset
    ]
    total = sum((row[7] for row in rows), Decimal("0.00"))
    return {
        "headers": [
            _("Run"), _("Period"), _("Employee #"), _("Name"), _("Basic"),
            _("Allowances"), _("Deductions"), _("Net"), _("Branch"),
        ],
        "rows": rows,
        "totals": {7: total},
    }


def _exam_results_report(user, branch, params):
    from apps.exams.models import ResultSummary

    queryset = ResultSummary.objects.for_user(user, branch).select_related(
        "student_exam__student", "student_exam__exam", "grade", "branch"
    )
    rows = [
        (
            summary.student_exam.exam.name,
            summary.student_exam.student.admission_no,
            summary.student_exam.student.full_name,
            summary.obtained_marks,
            summary.total_marks,
            summary.percentage,
            summary.grade.name if summary.grade else "",
            summary.position,
            summary.get_outcome_display(),
        )
        for summary in queryset
    ]
    return {
        "headers": [
            _("Exam"), _("Admission #"), _("Student"), _("Obtained"), _("Total"),
            _("Percentage"), _("Grade"), _("Position"), _("Outcome"),
        ],
        "rows": rows,
    }


def _hifz_report(user, branch, params):
    from apps.hifz.models import HifzStudentProfile
    from apps.hifz.services import progress_summary

    queryset = HifzStudentProfile.objects.for_user(user, branch).select_related(
        "student", "branch"
    )
    rows = []
    for profile in queryset:
        summary = progress_summary(
            user,
            branch,
            hifz_profile=profile,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
        )
        rows.append(
            (
                profile.student.admission_no,
                profile.student.full_name,
                profile.get_stage_display(),
                profile.current_para,
                profile.paras_memorized,
                summary["entries"] or 0,
                summary["total_pages"] or 0,
                summary["total_mistakes"] or 0,
                profile.branch.name,
            )
        )
    return {
        "headers": [
            _("Admission #"), _("Student"), _("Stage"), _("Current Para"),
            _("Paras Memorized"), _("Lessons"), _("Pages"), _("Mistakes"), _("Branch"),
        ],
        "rows": rows,
    }


def _staff_report(user, branch, params):
    from apps.staff.models import Staff

    queryset = Staff.objects.for_user(user, branch).select_related(
        "department", "designation", "branch"
    )
    rows = [
        (
            staff.employee_no,
            staff.full_name,
            staff.get_staff_type_display(),
            staff.department.name if staff.department else "",
            staff.designation.name if staff.designation else "",
            staff.phone,
            staff.joining_date,
            staff.get_status_display(),
            staff.branch.name,
        )
        for staff in queryset
    ]
    return {
        "headers": [
            _("Employee #"), _("Name"), _("Type"), _("Department"), _("Designation"),
            _("Phone"), _("Joined"), _("Status"), _("Branch"),
        ],
        "rows": rows,
    }


def _branch_summary_report(user, branch, params):
    """One row per branch - the organization-wide roll-up."""
    from django.db.models import Count, Sum

    from apps.accounts.rbac import accessible_branches
    from apps.fees.models import FeeInvoice
    from apps.staff.models import Staff
    from apps.students.models import Student

    rows = []
    for each in accessible_branches(user):
        students = Student.objects.filter(
            branch=each, status=Student.Status.ACTIVE
        ).count()
        staff = Staff.objects.filter(branch=each, status=Staff.Status.ACTIVE).count()
        totals = (
            FeeInvoice.objects.filter(branch=each)
            .exclude(status=FeeInvoice.Status.CANCELLED)
            .aggregate(billed=Sum("total_amount"), paid=Sum("paid_amount"))
        )
        billed = totals["billed"] or Decimal("0.00")
        paid = totals["paid"] or Decimal("0.00")
        rows.append(
            (each.name, each.code, students, staff, billed, paid, billed - paid)
        )
    return {
        "headers": [
            _("Branch"), _("Code"), _("Students"), _("Staff"),
            _("Billed"), _("Collected"), _("Outstanding"),
        ],
        "rows": rows,
    }


DATE_FILTERS = ("date_from", "date_to")

register(ReportDefinition(
    key="students",
    label=_("Student Register"),
    description=_("Every student with class, status and admission details."),
    permission="core.access_students",
    builder=_students_report,
    filters=("status",),
))
register(ReportDefinition(
    key="attendance",
    label=_("Attendance Summary"),
    description=_("Present, absent and late counts per student for a date range."),
    permission="core.access_attendance",
    builder=_attendance_report,
    filters=DATE_FILTERS,
))
register(ReportDefinition(
    key="fee_collection",
    label=_("Fee Collection"),
    description=_("Receipts collected in a date range."),
    permission="core.access_fees",
    builder=_fee_collection_report,
    filters=DATE_FILTERS,
))
register(ReportDefinition(
    key="fee_outstanding",
    label=_("Outstanding Fees"),
    description=_("Invoices past their due date with a balance."),
    permission="core.access_fees",
    builder=_fee_outstanding_report,
))
register(ReportDefinition(
    key="finance_trial_balance",
    label=_("Trial Balance"),
    description=_("Debits and credits per ledger account."),
    permission="core.access_finance",
    builder=_finance_trial_balance_report,
    filters=DATE_FILTERS,
))
register(ReportDefinition(
    key="payroll",
    label=_("Payroll Register"),
    description=_("Payslip figures per staff member."),
    permission="core.access_payroll",
    builder=_payroll_report,
    filters=DATE_FILTERS,
))
register(ReportDefinition(
    key="exam_results",
    label=_("Exam Results"),
    description=_("Result summaries with grade and position."),
    permission="core.access_exams",
    builder=_exam_results_report,
))
register(ReportDefinition(
    key="hifz",
    label=_("Hifz Progress"),
    description=_("Memorization stage and effort per student."),
    permission="core.access_hifz",
    builder=_hifz_report,
    filters=DATE_FILTERS,
))
register(ReportDefinition(
    key="staff",
    label=_("Staff Register"),
    description=_("Every staff member with department and status."),
    permission="core.access_staff",
    builder=_staff_report,
))
register(ReportDefinition(
    key="branch_summary",
    label=_("Branch Summary"),
    description=_("Students, staff and fee totals for every accessible branch."),
    permission="core.view_all_branches",
    builder=_branch_summary_report,
    organization_wide=True,
))
