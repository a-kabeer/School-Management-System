"""Shared pagination helpers used by every list view and template."""

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator


def paginate(request, queryset, per_page=None):
    """Return ``(page, paginator)`` for the requested page, clamped to range."""
    per_page = per_page or getattr(settings, "PAGE_SIZE", 25)
    try:
        per_page = min(max(int(request.GET.get("per_page", per_page)), 5), 200)
    except (TypeError, ValueError):
        per_page = getattr(settings, "PAGE_SIZE", 25)

    paginator = Paginator(queryset, per_page)
    try:
        page = paginator.page(request.GET.get("page", 1))
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    return page, paginator


def querystring_without_page(request):
    """Current query string minus ``page``, for building pagination links."""
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"{encoded}&" if encoded else ""
