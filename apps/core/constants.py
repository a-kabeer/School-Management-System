"""Constants shared across every module.

Keeping these here means role names, action verbs and status vocabularies are
declared once. Business code refers to the constant, never to a literal string
scattered through views.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

# --------------------------------------------------------------------------
# Roles seeded for every organization. Roles live in the database, so more can
# be added at runtime without touching application code.
# --------------------------------------------------------------------------
ROLE_ADMIN = "Admin"
ROLE_TEACHER = "Teacher"
ROLE_FEES_COLLECTOR = "Fees Collector"
ROLE_FINANCE = "Finance"
ROLE_STUDENT = "Student"
ROLE_PARENT = "Parent"

SYSTEM_ROLES = (
    ROLE_ADMIN,
    ROLE_TEACHER,
    ROLE_FEES_COLLECTOR,
    ROLE_FINANCE,
    ROLE_STUDENT,
    ROLE_PARENT,
)


class Gender(models.TextChoices):
    MALE = "male", _("Male")
    FEMALE = "female", _("Female")


class RecordStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    ARCHIVED = "archived", _("Archived")


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", _("Present")
    ABSENT = "absent", _("Absent")
    LATE = "late", _("Late")
    LEAVE = "leave", _("Leave")
    EXCUSED = "excused", _("Excused")


class PaymentMethodType(models.TextChoices):
    CASH = "cash", _("Cash")
    BANK = "bank", _("Bank Transfer")
    CHEQUE = "cheque", _("Cheque")
    CARD = "card", _("Card")
    MOBILE_WALLET = "mobile_wallet", _("Mobile Wallet")
    OTHER = "other", _("Other")


#: Languages that render right-to-left.
RTL_LANGUAGES = {"ur", "ar"}

#: Session key holding the branch the user is currently working in.
ACTIVE_BRANCH_SESSION_KEY = "active_branch_id"

#: Two decimal places everywhere money is stored or computed.
MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2
