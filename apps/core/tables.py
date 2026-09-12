"""The shared table's server-side behaviour: sorting, paging and export.

Sorting, filtering and paging all happen in the database. A branch with nine
thousand students never loads nine thousand rows to show twenty-five of them,
and a sort is an ``ORDER BY`` rather than a JavaScript comparison — which is
the only arrangement that stays correct once a list is longer than one page.

Nothing here trusts the query string. A ``?sort=`` the user hand-edits is
matched against the columns the view actually declared, and anything else
falls back to the view's own ordering.
"""

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist

#: Rows-per-page choices offered by every table.
PAGE_SIZES = (25, 50, 100, 200, 500)


def page_size(request, default=None):
    """The requested rows per page, restricted to the offered choices."""
    fallback = default or getattr(settings, "PAGE_SIZE", 25)
    try:
        requested = int(request.GET.get("per_page", ""))
    except (TypeError, ValueError):
        return fallback
    return requested if requested in PAGE_SIZES else fallback


def database_lookup(model, dotted):
    """Turn a column's dotted path into an ORM lookup, or ``None``.

    ``"session.school_class.name"`` becomes ``"session__school_class__name"``
    only if every step is a real database field. Properties and display
    helpers — ``worked_hours_display``, ``current_class_display`` — return
    ``None``, because the database cannot order by something it has never
    stored.
    """
    if not dotted or model is None:
        return None

    meta = model._meta
    parts = str(dotted).split(".")
    for index, part in enumerate(parts):
        try:
            field = meta.get_field(part)
        except (FieldDoesNotExist, AttributeError):
            return None

        if field.many_to_many or field.one_to_many:
            # Ordering across a to-many join multiplies rows, which silently
            # corrupts both the page and the count.
            return None

        if index < len(parts) - 1:
            if not field.is_relation or field.related_model is None:
                return None
            meta = field.related_model._meta

    return "__".join(parts)


def column_lookup(model, column):
    """The lookup a column sorts by.

    A column may name its own lookup with ``"sort"``, or opt out with
    ``"sort": False``; otherwise the field path decides.
    """
    declared = column.get("sort")
    if declared is False:
        return None
    if isinstance(declared, str) and declared:
        return declared
    return database_lookup(model, column.get("field", ""))


def sortable_columns(model, columns):
    """``{column field: orm lookup}`` for every column that can be sorted."""
    resolved = {}
    for column in columns:
        lookup = column_lookup(model, column)
        if lookup:
            resolved[str(column.get("field", ""))] = lookup
    return resolved


def sort_state(request, model, columns, default_ordering=()):
    """Resolve ``?sort=…&dir=…`` against the columns the view declared."""
    allowed = sortable_columns(model, columns)
    requested = (request.GET.get("sort") or "").strip()
    direction = "desc" if request.GET.get("dir") == "desc" else "asc"

    active = requested if requested in allowed else ""
    if active:
        ordering = [("-" if direction == "desc" else "") + allowed[active]]
    else:
        ordering = list(default_ordering)

    # A non-unique sort column leaves rows in an arbitrary order within ties,
    # so page 2 can repeat a row from page 1. A primary-key tiebreaker makes
    # the paging deterministic.
    if not any(str(term).lstrip("-") in ("pk", "id") for term in ordering):
        ordering.append("pk")

    return {
        "sortable": allowed,
        "active": active,
        "direction": direction,
        "ordering": ordering,
    }


def column_headers(model, columns, sort):
    """Columns annotated with what the header needs to draw itself."""
    headers = []
    for column in columns:
        field = str(column.get("field", ""))
        sortable = field in sort["sortable"]
        is_sorted = sortable and field == sort["active"]
        headers.append(
            {
                **column,
                "sortable": sortable,
                "is_sorted": is_sorted,
                "sort_dir": sort["direction"] if is_sorted else "",
                # Clicking a sorted column reverses it; clicking a new one
                # starts ascending, which is what people expect.
                "next_dir": "desc" if (is_sorted and sort["direction"] == "asc") else "asc",
            }
        )
    return headers


def relation_prefixes(model, columns):
    """Relation paths a column list reads, for checking ``select_related``.

    ``"session.school_class.name"`` needs ``session__school_class`` joined;
    without it every row costs an extra query. Used by the test that keeps
    list views free of N+1s.
    """
    needed = set()
    for column in columns:
        parts = str(column.get("field", "")).split(".")
        if len(parts) < 2:
            continue
        meta = model._meta
        walked = []
        for part in parts[:-1]:
            try:
                field = meta.get_field(part)
            except (FieldDoesNotExist, AttributeError):
                break
            if not field.is_relation or field.related_model is None:
                break
            walked.append(part)
            meta = field.related_model._meta
        if walked:
            needed.add("__".join(walked))
    return needed
