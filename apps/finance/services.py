"""Finance service layer - the only way money reaches the ledger.

:func:`post_journal_entry` refuses to write an unbalanced document, so
"debits equal credits" is enforced before the rows exist rather than checked
by a report afterwards.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity
from apps.core.utils import money, next_sequence_number

from .models import Account, AccountType, FiscalPeriod, Journal, JournalEntry, Transaction

#: Codes the seeder creates; services look accounts up by these rather than
#: by name, so a renamed account does not break posting.
CODE_CASH = "1000"
CODE_BANK = "1010"
CODE_RECEIVABLE = "1100"
CODE_TUITION_INCOME = "4000"
CODE_FEE_DISCOUNT = "5100"
CODE_SALARY_EXPENSE = "5000"
CODE_SALARY_PAYABLE = "2100"


def get_account(branch, code):
    account = Account.objects.filter(branch=branch, code=code, is_active=True).first()
    if account is None:
        raise ValidationError(
            _("Ledger account %(code)s is not set up for this branch.") % {"code": code}
        )
    return account


def get_open_period(branch, date_value):
    """The fiscal period covering ``date_value``. Closed periods are refused."""
    period = FiscalPeriod.objects.filter(
        branch=branch, start_date__lte=date_value, end_date__gte=date_value
    ).first()
    if period is None:
        raise ValidationError(
            _("No fiscal period covers %(date)s.") % {"date": date_value}
        )
    if period.is_closed:
        raise ValidationError(
            _("The fiscal period %(name)s is closed.") % {"name": period.name}
        )
    return period


def get_journal(branch, journal_type):
    journal = Journal.objects.filter(
        branch=branch, journal_type=journal_type, is_active=True
    ).first()
    if journal is None:
        journal = Journal.objects.filter(
            branch=branch, journal_type=Journal.JournalType.GENERAL, is_active=True
        ).first()
    if journal is None:
        raise ValidationError(_("No journal is configured for this branch."))
    return journal


def next_entry_number(branch, prefix="JE-"):
    return next_sequence_number(
        JournalEntry.objects.filter(branch=branch), "entry_number", prefix=prefix, width=6
    )


@transaction.atomic
def post_journal_entry(
    *,
    branch,
    date,
    lines,
    journal_type=Journal.JournalType.GENERAL,
    description="",
    reference="",
    source_module="",
    source_id="",
    actor=None,
    request=None,
    status=JournalEntry.Status.POSTED,
):
    """Create a balanced journal entry with its lines.

    ``lines`` is a sequence of ``{"account": Account, "debit": .., "credit": ..,
    "description": ..}``. Amounts are coerced to 2dp Decimals; floats never
    reach the database.
    """
    if not lines:
        raise ValidationError(_("A journal entry needs at least one line."))

    journal = get_journal(branch, journal_type)
    period = get_open_period(branch, date)

    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    prepared = []
    for index, line in enumerate(lines, start=1):
        account = line["account"]
        if account.branch_id != branch.pk:
            # Posting into another branch's ledger would break tenancy at the
            # one place it matters most.
            raise ValidationError(_("That account belongs to a different branch."))
        debit = money(line.get("debit"))
        credit = money(line.get("credit"))
        if debit and credit:
            raise ValidationError(_("A line cannot be both a debit and a credit."))
        if not debit and not credit:
            continue
        total_debit += debit
        total_credit += credit
        prepared.append(
            {
                "account": account,
                "debit": debit,
                "credit": credit,
                "description": line.get("description", "")[:255],
                "line_number": index,
            }
        )

    if not prepared:
        raise ValidationError(_("A journal entry needs at least one non-zero line."))
    if total_debit != total_credit:
        raise ValidationError(
            _("Entry is out of balance: debits %(d)s, credits %(c)s.")
            % {"d": total_debit, "c": total_credit}
        )

    entry = JournalEntry.objects.create(
        branch=branch,
        organization=branch.organization,
        journal=journal,
        fiscal_period=period,
        entry_number=next_entry_number(branch),
        date=date,
        reference=reference[:150],
        description=description,
        total_debit=total_debit,
        total_credit=total_credit,
        status=status,
        source_module=source_module[:50],
        source_id=str(source_id)[:64],
        created_by=actor,
        posted_at=timezone.now() if status == JournalEntry.Status.POSTED else None,
    )

    Transaction.objects.bulk_create(
        [
            Transaction(
                branch=branch,
                organization=branch.organization,
                journal_entry=entry,
                **line,
            )
            for line in prepared
        ]
    )

    log_activity(
        action="create",
        request=request,
        user=actor,
        instance=entry,
        new_values={
            "entry_number": entry.entry_number,
            "total": str(total_debit),
            "source": f"{source_module}:{source_id}",
        },
        metadata={"event": "journal_posted"},
    )
    return entry


@transaction.atomic
def reverse_journal_entry(*, entry, date=None, reason="", actor=None, request=None):
    """Post the mirror image of an entry instead of editing it.

    A posted document is never rewritten; correcting it means a second,
    opposite document that leaves both visible in the ledger.
    """
    if entry.status != JournalEntry.Status.POSTED:
        raise ValidationError(_("Only a posted entry can be reversed."))
    if hasattr(entry, "reversed_by") and entry.reversed_by is not None:
        raise ValidationError(_("This entry has already been reversed."))

    lines = [
        {
            "account": line.account,
            "debit": line.credit,
            "credit": line.debit,
            "description": line.description,
        }
        for line in entry.lines.select_related("account")
    ]

    reversal = post_journal_entry(
        branch=entry.branch,
        date=date or timezone.localdate(),
        lines=lines,
        journal_type=entry.journal.journal_type,
        description=reason or f"{_('Reversal of')} {entry.entry_number}",
        reference=entry.entry_number,
        source_module=entry.source_module,
        source_id=entry.source_id,
        actor=actor,
        request=request,
    )
    reversal.reversal_of = entry
    reversal.save(update_fields=["reversal_of", "updated_at"])

    entry.status = JournalEntry.Status.REVERSED
    entry.save(update_fields=["status", "updated_at"])
    return reversal


@transaction.atomic
def close_fiscal_period(*, period, actor=None, request=None):
    if period.is_closed:
        return period
    draft_count = period.entries.filter(status=JournalEntry.Status.DRAFT).count()
    if draft_count:
        raise ValidationError(
            _("%(count)s draft entries must be posted or deleted first.")
            % {"count": draft_count}
        )
    period.is_closed = True
    period.closed_at = timezone.now()
    period.closed_by = actor
    period.save(update_fields=["is_closed", "closed_at", "closed_by", "updated_at"])
    log_activity(
        action="settings_change",
        request=request,
        user=actor,
        instance=period,
        new_values={"is_closed": True},
    )
    return period


def trial_balance(user, branch=None, *, date_from=None, date_to=None):
    """Debit/credit totals per account - the ledger's self-check."""
    queryset = Transaction.objects.for_user(user, branch).filter(
        journal_entry__status=JournalEntry.Status.POSTED
    )
    if date_from:
        queryset = queryset.filter(journal_entry__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__date__lte=date_to)

    rows = (
        queryset.values(
            "account__code",
            "account__name",
            "account__account_type__nature",
            "account__account_type__normal_balance",
        )
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code")
    )

    prepared = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for row in rows:
        debit = money(row["debit"])
        credit = money(row["credit"])
        total_debit += debit
        total_credit += credit
        balance = (
            debit - credit
            if row["account__account_type__normal_balance"]
            == AccountType.NormalBalance.DEBIT
            else credit - debit
        )
        prepared.append(
            {
                "code": row["account__code"],
                "name": row["account__name"],
                "nature": row["account__account_type__nature"],
                "debit": debit,
                "credit": credit,
                "balance": money(balance),
            }
        )

    return {
        "rows": prepared,
        "total_debit": money(total_debit),
        "total_credit": money(total_credit),
        "is_balanced": total_debit == total_credit,
    }


def income_statement(user, branch=None, *, date_from=None, date_to=None):
    """Income and expense totals for the period."""
    queryset = Transaction.objects.for_user(user, branch).filter(
        journal_entry__status=JournalEntry.Status.POSTED
    )
    if date_from:
        queryset = queryset.filter(journal_entry__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__date__lte=date_to)

    def _totals(nature):
        rows = (
            queryset.filter(account__account_type__nature=nature)
            .values("account__code", "account__name")
            .annotate(debit=Sum("debit"), credit=Sum("credit"))
            .order_by("account__code")
        )
        prepared, total = [], Decimal("0.00")
        for row in rows:
            amount = (
                money(row["credit"]) - money(row["debit"])
                if nature == AccountType.Nature.INCOME
                else money(row["debit"]) - money(row["credit"])
            )
            total += amount
            prepared.append(
                {
                    "code": row["account__code"],
                    "name": row["account__name"],
                    "amount": money(amount),
                }
            )
        return prepared, money(total)

    income_rows, income_total = _totals(AccountType.Nature.INCOME)
    expense_rows, expense_total = _totals(AccountType.Nature.EXPENSE)
    return {
        "income": income_rows,
        "income_total": income_total,
        "expenses": expense_rows,
        "expense_total": expense_total,
        "surplus": money(income_total - expense_total),
    }
