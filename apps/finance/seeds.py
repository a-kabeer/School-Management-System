"""Chart of accounts and finance defaults for a new branch.

The codes here are the ones :mod:`apps.finance.services` looks up when fees
and payroll post, so a branch is not ready to take money until this has run.
"""

from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _

from .models import Account, AccountType, FiscalPeriod, Journal, PaymentMethod
from .services import (
    CODE_BANK,
    CODE_CASH,
    CODE_FEE_DISCOUNT,
    CODE_RECEIVABLE,
    CODE_SALARY_EXPENSE,
    CODE_SALARY_PAYABLE,
    CODE_TUITION_INCOME,
)

ACCOUNT_TYPES = [
    ("100", "Assets", AccountType.Nature.ASSET, AccountType.NormalBalance.DEBIT),
    ("200", "Liabilities", AccountType.Nature.LIABILITY, AccountType.NormalBalance.CREDIT),
    ("300", "Equity", AccountType.Nature.EQUITY, AccountType.NormalBalance.CREDIT),
    ("400", "Income", AccountType.Nature.INCOME, AccountType.NormalBalance.CREDIT),
    ("500", "Expenses", AccountType.Nature.EXPENSE, AccountType.NormalBalance.DEBIT),
]

ACCOUNTS = [
    (CODE_CASH, "Cash in Hand", "100", True),
    (CODE_BANK, "Bank Account", "100", True),
    (CODE_RECEIVABLE, "Fees Receivable", "100", False),
    ("2000", "Accounts Payable", "200", False),
    (CODE_SALARY_PAYABLE, "Salaries Payable", "200", False),
    ("3000", "Opening Balance Equity", "300", False),
    (CODE_TUITION_INCOME, "Tuition Fee Income", "400", False),
    ("4010", "Admission Fee Income", "400", False),
    ("4020", "Other Income", "400", False),
    (CODE_SALARY_EXPENSE, "Salaries and Wages", "500", False),
    (CODE_FEE_DISCOUNT, "Fee Concessions", "500", False),
    ("5200", "Utilities", "500", False),
    ("5300", "Maintenance", "500", False),
    ("5400", "General Expenses", "500", False),
]

JOURNALS = [
    ("GEN", "General Journal", Journal.JournalType.GENERAL),
    ("CRJ", "Cash Receipts", Journal.JournalType.CASH_RECEIPT),
    ("CPJ", "Cash Payments", Journal.JournalType.CASH_PAYMENT),
    ("PAY", "Payroll", Journal.JournalType.PAYROLL),
    ("ADJ", "Adjustments", Journal.JournalType.ADJUSTMENT),
]


@transaction.atomic
def seed_account_types(organization):
    types = {}
    for code, name, nature, normal in ACCOUNT_TYPES:
        account_type, _created = AccountType.objects.get_or_create(
            organization=organization,
            code=code,
            defaults={"name": name, "nature": nature, "normal_balance": normal},
        )
        types[code] = account_type
    return types


@transaction.atomic
def seed_chart_of_accounts(branch):
    """Create the ledger accounts, journals and payment methods for a branch."""
    types = seed_account_types(branch.organization)

    accounts = {}
    for code, name, type_code, is_bank in ACCOUNTS:
        account, _created = Account.objects.get_or_create(
            branch=branch,
            code=code,
            defaults={
                "organization": branch.organization,
                "name": name,
                "account_type": types[type_code],
                "is_bank_account": is_bank,
                "opening_balance": Decimal("0.00"),
            },
        )
        accounts[code] = account

    for code, name, journal_type in JOURNALS:
        Journal.objects.get_or_create(
            branch=branch,
            code=code,
            defaults={
                "organization": branch.organization,
                "name": name,
                "journal_type": journal_type,
            },
        )

    PaymentMethod.objects.get_or_create(
        branch=branch,
        name=_("Cash"),
        defaults={
            "organization": branch.organization,
            "method_type": "cash",
            "account": accounts[CODE_CASH],
        },
    )
    PaymentMethod.objects.get_or_create(
        branch=branch,
        name=_("Bank Transfer"),
        defaults={
            "organization": branch.organization,
            "method_type": "bank",
            "account": accounts[CODE_BANK],
            "requires_reference": True,
        },
    )
    return accounts


@transaction.atomic
def seed_fiscal_period(branch, start_date, end_date, name=None):
    period, _created = FiscalPeriod.objects.get_or_create(
        branch=branch,
        name=name or f"FY {start_date.year}-{end_date.year}",
        defaults={
            "organization": branch.organization,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    return period
