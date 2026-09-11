"""Payroll service layer.

A payroll run computes every payslip from the staff member's active salary
structure, then posts one journal entry for the whole run. Every figure is a
Decimal from start to finish.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity, snapshot
from apps.core.utils import money, next_sequence_number
from apps.finance.models import Journal
from apps.finance.services import (
    CODE_SALARY_EXPENSE,
    CODE_SALARY_PAYABLE,
    get_account,
    post_journal_entry,
)

from .models import (
    EmployeeSalary,
    PayrollItem,
    PayrollPeriod,
    PayrollRun,
    SalaryComponent,
    SalaryPayment,
)

ZERO = Decimal("0.00")


def next_run_reference(branch):
    return next_sequence_number(
        PayrollRun.objects.filter(branch=branch),
        "reference",
        prefix=f"PR-{branch.code.upper()}-",
        width=5,
    )


def next_voucher_number(branch):
    return next_sequence_number(
        SalaryPayment.objects.filter(branch=branch),
        "voucher_number",
        prefix=f"SV-{branch.code.upper()}-",
        width=6,
    )


def compute_payslip(employee_salary, *, days_present=None, days_absent=None):
    """Work out one payslip from a salary structure.

    Returns the totals plus a line-by-line breakdown, which is what the
    payslip and any later query both need.
    """
    basic = money(employee_salary.basic_salary)
    allowances = ZERO
    deductions = ZERO
    breakdown = []

    lines = employee_salary.structure.lines.select_related("component").order_by(
        "sequence"
    )
    for line in lines:
        component = line.component
        if component.calculation_type == SalaryComponent.CalculationType.PERCENT_OF_BASIC:
            amount = money(basic * money(line.value) / Decimal("100"))
        else:
            amount = money(line.value)

        if component.component_type == SalaryComponent.ComponentType.EARNING:
            allowances += amount
        else:
            deductions += amount

        breakdown.append(
            {
                "code": component.code,
                "name": component.name,
                "type": component.component_type,
                "amount": str(amount),
            }
        )

    gross = money(basic + allowances)
    net = money(gross - deductions)
    if net < ZERO:
        # Deductions larger than earnings mean a misconfigured structure, not
        # a negative salary.
        raise ValidationError(
            _("Deductions exceed earnings for %(staff)s.")
            % {"staff": employee_salary.staff}
        )

    return {
        "basic_salary": basic,
        "total_allowances": money(allowances),
        "total_deductions": money(deductions),
        "gross_salary": gross,
        "net_salary": net,
        "breakdown": breakdown,
        "days_present": Decimal(days_present or 0),
        "days_absent": Decimal(days_absent or 0),
    }


@transaction.atomic
def process_payroll(*, period, staff_queryset=None, run_date=None, actor=None, request=None):
    """Create a draft run with one payslip per active salary."""
    if period.status == PayrollPeriod.Status.CLOSED:
        raise ValidationError(_("This payroll period is closed."))

    run_date = run_date or timezone.localdate()
    salaries = EmployeeSalary.objects.filter(
        branch=period.branch, is_active=True
    ).select_related("staff", "structure")
    if staff_queryset is not None:
        salaries = salaries.filter(staff__in=staff_queryset)
    salaries = [s for s in salaries if s.staff.status == "active"]

    if not salaries:
        raise ValidationError(_("No active salaries to process for this period."))

    run = PayrollRun.objects.create(
        branch=period.branch,
        organization=period.organization,
        period=period,
        reference=next_run_reference(period.branch),
        run_date=run_date,
        processed_by=actor,
    )

    total_gross = ZERO
    total_deductions = ZERO
    total_net = ZERO
    items = []
    for salary in salaries:
        figures = compute_payslip(salary)
        items.append(
            PayrollItem(
                branch=run.branch,
                organization=run.organization,
                run=run,
                staff=salary.staff,
                **figures,
            )
        )
        total_gross += figures["gross_salary"]
        total_deductions += figures["total_deductions"]
        total_net += figures["net_salary"]

    PayrollItem.objects.bulk_create(items)

    run.total_gross = money(total_gross)
    run.total_deductions = money(total_deductions)
    run.total_net = money(total_net)
    run.employee_count = len(items)
    run.save(
        update_fields=[
            "total_gross",
            "total_deductions",
            "total_net",
            "employee_count",
            "updated_at",
        ]
    )

    period.status = PayrollPeriod.Status.PROCESSING
    period.save(update_fields=["status", "updated_at"])

    log_activity(
        action="payroll",
        request=request,
        user=actor,
        instance=run,
        new_values={
            "reference": run.reference,
            "employees": run.employee_count,
            "net": str(run.total_net),
        },
        metadata={"event": "payroll_processed"},
    )
    return run


@transaction.atomic
def approve_payroll_run(*, run, actor=None, request=None):
    """Approve a run and post the salary expense to the ledger."""
    if run.status != PayrollRun.Status.DRAFT:
        raise ValidationError(_("Only a draft run can be approved."))
    if run.total_net <= ZERO:
        raise ValidationError(_("This run has nothing to post."))

    previous = snapshot(run)
    entry = post_journal_entry(
        branch=run.branch,
        date=run.run_date,
        lines=[
            {
                "account": get_account(run.branch, CODE_SALARY_EXPENSE),
                "debit": run.total_gross,
                "description": f"{_('Payroll')} {run.reference}",
            },
            {
                "account": get_account(run.branch, CODE_SALARY_PAYABLE),
                "credit": run.total_gross,
                "description": f"{_('Salaries payable')} {run.reference}",
            },
        ],
        journal_type=Journal.JournalType.PAYROLL,
        description=f"{_('Payroll run')} {run.reference}",
        reference=run.reference,
        source_module="payroll.run",
        source_id=run.pk,
        actor=actor,
        request=request,
    )

    run.journal_entry = entry
    run.status = PayrollRun.Status.APPROVED
    run.save(update_fields=["journal_entry", "status", "updated_at"])

    log_activity(
        action="payroll",
        request=request,
        user=actor,
        instance=run,
        previous_values=previous,
        new_values=snapshot(run),
        metadata={"event": "payroll_approved"},
    )
    return run


@transaction.atomic
def pay_salary(
    *, payroll_item, payment_method, amount=None, payment_date=None, reference="",
    actor=None, request=None,
):
    """Disburse one payslip and post the cash movement."""
    if payroll_item.run.status not in {PayrollRun.Status.APPROVED, PayrollRun.Status.PAID}:
        raise ValidationError(_("Approve the payroll run before paying salaries."))
    if payment_method.branch_id != payroll_item.branch_id:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(_("That payment method belongs to a different branch."))

    payment_date = payment_date or timezone.localdate()
    already = money(
        payroll_item.payments.aggregate(total=Sum("amount"))["total"]
    )
    amount = money(amount if amount is not None else payroll_item.net_salary - already)
    if amount <= ZERO:
        raise ValidationError({"amount": _("Amount must be greater than zero.")})
    if already + amount > payroll_item.net_salary:
        raise ValidationError({"amount": _("That is more than the net salary due.")})

    payment = SalaryPayment.objects.create(
        branch=payroll_item.branch,
        organization=payroll_item.organization,
        payroll_item=payroll_item,
        payment_method=payment_method,
        voucher_number=next_voucher_number(payroll_item.branch),
        amount=amount,
        payment_date=payment_date,
        reference=reference[:150],
        paid_by=actor,
    )

    entry = post_journal_entry(
        branch=payroll_item.branch,
        date=payment_date,
        lines=[
            {
                "account": get_account(payroll_item.branch, CODE_SALARY_PAYABLE),
                "debit": amount,
                "description": f"{payment.voucher_number} — {payroll_item.staff}",
            },
            {
                "account": payment_method.account,
                "credit": amount,
                "description": payment.voucher_number,
            },
        ],
        journal_type=Journal.JournalType.CASH_PAYMENT,
        description=f"{_('Salary payment')} {payment.voucher_number}",
        reference=payment.voucher_number,
        source_module="payroll.payment",
        source_id=payment.pk,
        actor=actor,
        request=request,
    )
    payment.journal_entry = entry
    payment.save(update_fields=["journal_entry", "updated_at"])

    # Mark the run paid once every payslip is fully disbursed.
    run = payroll_item.run
    unpaid = False
    for item in run.items.prefetch_related("payments"):
        item_paid = money(sum((p.amount for p in item.payments.all()), ZERO))
        if item_paid < item.net_salary:
            unpaid = True
            break
    if not unpaid:
        run.status = PayrollRun.Status.PAID
        run.save(update_fields=["status", "updated_at"])
        run.period.status = PayrollPeriod.Status.CLOSED
        run.period.save(update_fields=["status", "updated_at"])

    log_activity(
        action="payroll",
        request=request,
        user=actor,
        instance=payment,
        new_values={
            "voucher": payment.voucher_number,
            "amount": str(amount),
            "staff": str(payroll_item.staff),
        },
        metadata={"event": "salary_paid"},
    )
    return payment


def payroll_summary(user, branch=None, *, period=None):
    queryset = PayrollItem.objects.for_user(user, branch)
    if period is not None:
        queryset = queryset.filter(run__period=period)
    totals = queryset.aggregate(
        gross=Sum("gross_salary"),
        deductions=Sum("total_deductions"),
        net=Sum("net_salary"),
    )
    return {
        "gross": money(totals["gross"]),
        "deductions": money(totals["deductions"]),
        "net": money(totals["net"]),
        "employees": queryset.count(),
    }
