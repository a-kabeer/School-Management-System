"""Validators shared by forms and models."""

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

PHONE_RE = re.compile(r"^[+]?[0-9][0-9\s\-()]{6,30}$")


def validate_phone(value):
    if value and not PHONE_RE.match(value):
        raise ValidationError(_("Enter a valid phone number."))


def validate_non_negative(value):
    if value is not None and Decimal(value) < 0:
        raise ValidationError(_("This value cannot be negative."))


def validate_positive_amount(value):
    if value is None or Decimal(value) <= 0:
        raise ValidationError(_("Amount must be greater than zero."))


def validate_upload(uploaded_file):
    """Size and extension gate for every user-supplied file.

    Extension checking is deliberate: the storage layer serves these files
    back, so an unexpected type is a real risk, not a cosmetic one.
    """
    if not uploaded_file:
        return uploaded_file

    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    size = getattr(uploaded_file, "size", 0)
    if size > max_bytes:
        raise ValidationError(
            _("File is larger than the %(limit)s MB limit.")
            % {"limit": settings.UPLOAD_MAX_SIZE_MB}
        )

    name = getattr(uploaded_file, "name", "") or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    allowed = {e.lower().lstrip(".") for e in settings.UPLOAD_ALLOWED_EXTENSIONS}
    if extension not in allowed:
        raise ValidationError(
            _("Files of type .%(ext)s are not allowed.") % {"ext": extension or "?"}
        )
    return uploaded_file


def validate_date_range(start, end, field_name="end_date"):
    if start and end and end < start:
        raise ValidationError({field_name: _("End date cannot be before start date.")})
