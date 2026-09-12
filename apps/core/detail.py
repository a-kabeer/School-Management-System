"""Building blocks for the View screens.

A View is not a dump of columns. It says what the record is, what state it is
in, what hangs off it, and where the reader can go next. These small factories
build the dictionaries the shared `detail.html`, `detail_header.html` and
`related_card.html` templates render, so every module describes its screens
the same way instead of hand-rolling markup.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def badge(label, variant="secondary", icon=None):
    """A status pill for the header: Current, Closed, Active, Inactive."""
    return {"label": label, "variant": variant, "icon": icon}


def meta(label, value, icon=None, url=None):
    """One identifying fact in the header, optionally a link to its record."""
    return {"label": label, "value": value, "icon": icon, "url": url}


def cell(label, value, badge=None):
    """One value in a related row, carrying its column label.

    The label travels with the value because a table that reflows into cards
    on a phone has no header row left to read it from.
    """
    return {"label": label, "value": value, "badge": badge}


def row(url, *cells):
    """One related record: where it lives, and the values to show for it."""
    return {"url": url, "cells": list(cells)}


def tab(identifier, label, icon=None, count=None):
    return {"id": identifier, "label": label, "icon": icon, "count": count}


def _inherit_create_context(add_url, all_url):
    """Carry a related-card's known filter context into its Create action.

    Detail pages already build ``all_url`` with the exact relationship that
    the reader is looking at. Reusing that query string keeps contextual Add
    actions consistent without requiring every detail view to duplicate URL
    construction logic.
    """
    if not add_url or not all_url:
        return add_url
    source = urlsplit(str(all_url))
    target = urlsplit(str(add_url))
    source_params = parse_qsl(source.query, keep_blank_values=False)
    if not source_params:
        return add_url
    target_params = parse_qsl(target.query, keep_blank_values=True)
    existing = {key for key, _ in target_params}
    target_params.extend((key, value) for key, value in source_params if key not in existing)
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(target_params), target.fragment))


def related_card(
    *,
    title,
    columns,
    rows,
    icon=None,
    total=None,
    all_url=None,
    all_label=None,
    add_url=None,
    add_label=None,
    add_modal=True,
    empty=None,
    empty_hint=None,
):
    """A block of related records, with its way in and its way onward.

    ``total`` is the real number of related records; ``rows`` may be a shorter
    preview, and the difference is reported rather than silently dropped.

    When both list and Create URLs are supplied, known list context is carried
    into Create automatically. This makes contextual Add actions reusable by
    every module instead of implementing the same URL logic repeatedly.
    """
    rows = list(rows)
    total = len(rows) if total is None else total
    add_url = _inherit_create_context(add_url, all_url)
    return {
        "title": title,
        "icon": icon,
        "columns": list(columns),
        "rows": rows,
        "total": total,
        "more": max(total - len(rows), 0),
        "all_url": all_url,
        "all_label": all_label,
        "add_url": add_url,
        "add_label": add_label,
        "add_modal": add_modal,
        "empty": empty,
        "empty_hint": empty_hint,
    }


def active_badge(is_active, active_label, inactive_label):
    """The Active/Inactive pill almost every academic record carries."""
    return (
        badge(active_label, "success", "bi-check-circle")
        if is_active
        else badge(inactive_label, "secondary", "bi-slash-circle")
    )
