"""Template helpers shared by the reusable components."""

from decimal import Decimal

from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe

from apps.core.permissions import user_has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, permission):
    """``{% has_perm "core.collect_fee_payment" as can_collect %}``"""
    request = context.get("request")
    if request is None:
        return False
    return user_has_permission(
        request.user, permission, getattr(request, "active_branch", None)
    )


@register.filter
def attr(obj, path):
    """Follow a dotted path, calling anything callable along the way."""
    value = obj
    for part in str(path).split("."):
        if value is None:
            return ""
        if isinstance(value, dict):
            value = value.get(part)
            continue
        value = getattr(value, part, None)
        if callable(value):
            value = value()
    return "" if value is None else value


@register.filter
def display(obj, field):
    """Prefer ``get_<field>_display`` so choices render their labels."""
    getter = getattr(obj, f"get_{field}_display", None)
    if callable(getter):
        return getter()
    return attr(obj, field)


@register.simple_tag
def url_or_blank(url_name, *args):
    if not url_name:
        return ""
    try:
        return reverse(url_name, args=args)
    except NoReverseMatch:
        return ""


@register.filter
def money(value):
    """Render a Decimal with grouping and exactly two decimals."""
    if value in (None, ""):
        value = Decimal("0")
    try:
        value = Decimal(value)
    except Exception:
        return value
    return f"{value:,.2f}"


@register.filter
def field_class(bound_field, css):
    widget = bound_field.field.widget
    existing = widget.attrs.get("class", "")
    widget.attrs["class"] = f"{existing} {css}".strip()
    return bound_field


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Rebuild the query string with the given parameters replaced."""
    request = context.get("request")
    params = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return mark_safe(f"?{encoded}" if encoded else "")


@register.filter
def percentage(part, whole):
    try:
        part, whole = Decimal(part or 0), Decimal(whole or 0)
    except Exception:
        return "0.0"
    if whole == 0:
        return "0.0"
    return f"{(part / whole * 100):.1f}"


@register.filter
def page_window(paginator, number):
    """Page numbers around the current one, elided at both ends.

    A list two hundred pages long must not print two hundred links; this
    returns the handful either side plus the first and last, with Django's
    ellipsis marker between them.
    """
    from django.core.paginator import EmptyPage, PageNotAnInteger

    try:
        return list(paginator.get_elided_page_range(number, on_each_side=2, on_ends=1))
    except (EmptyPage, PageNotAnInteger, AttributeError):
        return []
