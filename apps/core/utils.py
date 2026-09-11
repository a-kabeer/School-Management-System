"""Small shared helpers: money, safe redirects, Excel export."""

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    """Coerce anything to a 2dp Decimal. Never returns a float."""
    if value in (None, ""):
        return ZERO
    if isinstance(value, float):
        # Route through str so 0.1 does not arrive as 0.1000000000000000055.
        value = str(value)
    try:
        return Decimal(value).quantize(TWO_PLACES)
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def safe_redirect_target(request, candidate, fallback="/"):
    """Return ``candidate`` only if it points back at this site."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host(), *settings.ALLOWED_HOSTS},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def parse_date(value, default=None):
    if not value:
        return default
    if isinstance(value, dt.date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return default


def month_start(date_value):
    return date_value.replace(day=1)


def _excel_value(value):
    """Coerce a cell value to something openpyxl will accept.

    ``get_FOO_display()`` returns a lazy translation proxy, and a spreadsheet
    writer cannot serialise one - so anything that is not a native type is
    rendered to text here rather than blowing up mid-export.
    """
    if value is None or isinstance(value, (str, bool, int, float, Decimal)):
        return value
    if isinstance(value, dt.datetime):
        # Excel has no concept of a timezone-aware datetime.
        return value.replace(tzinfo=None)
    if isinstance(value, (dt.date, dt.time)):
        return value
    return str(value)


def export_to_excel(filename, headers, rows, *, sheet_title="Report"):
    """Stream a list of rows as an .xlsx download.

    ``rows`` is any iterable of sequences; Decimals are written as numbers so
    the spreadsheet can total them.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title[:31] or "Report"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F3B57")
    for column_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=column_index, value=str(header))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    widths = [len(str(h)) + 2 for h in headers]
    for row_index, row in enumerate(rows, start=2):
        for column_index, value in enumerate(row, start=1):
            value = _excel_value(value)
            sheet.cell(row=row_index, column=column_index, value=value)
            length = len(str(value if value is not None else ""))
            if column_index <= len(widths):
                widths[column_index - 1] = max(widths[column_index - 1], min(length + 2, 60))

    for column_index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width
    sheet.freeze_panes = "A2"

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    )
    safe_name = slugify(filename) or "report"
    response["Content-Disposition"] = f'attachment; filename="{safe_name}.xlsx"'
    workbook.save(response)
    return response


def next_sequence_number(queryset, field, prefix="", width=5):
    """Build the next ``PREFIX-00042`` style code for a branch-scoped model."""
    latest = (
        queryset.filter(**{f"{field}__startswith": prefix})
        .order_by(f"-{field}")
        .values_list(field, flat=True)
        .first()
    )
    counter = 0
    if latest:
        tail = latest[len(prefix):].lstrip("-")
        if tail.isdigit():
            counter = int(tail)
    return f"{prefix}{str(counter + 1).zfill(width)}"
