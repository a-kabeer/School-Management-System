"""Reusable query/filter helpers for list views and reports."""

import operator
from functools import reduce

from django.db.models import Q

from .utils import parse_date


def apply_search(queryset, term, fields):
    """Case-insensitive OR search across ``fields``."""
    term = (term or "").strip()
    if not term or not fields:
        return queryset
    clauses = [Q(**{f"{field}__icontains": term}) for field in fields]
    return queryset.filter(reduce(operator.or_, clauses))


def apply_choice_filters(queryset, request, mapping):
    """Apply ``?param=value`` filters described by ``{param: orm_lookup}``."""
    for param, lookup in mapping.items():
        value = (request.GET.get(param) or "").strip()
        if value:
            queryset = queryset.filter(**{lookup: value})
    return queryset


def apply_date_range(queryset, request, field, start_param="date_from", end_param="date_to"):
    start = parse_date(request.GET.get(start_param))
    end = parse_date(request.GET.get(end_param))
    if start:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


class FilterSpec:
    """Declarative description of a list view's filters.

    Views declare one of these instead of repeating ``request.GET`` plumbing;
    ``as_context`` feeds the shared ``components/filters.html`` template.
    """

    def __init__(self, *, search_fields=(), choices=None, date_field=None, selects=None):
        self.search_fields = search_fields
        self.choices = choices or {}
        self.date_field = date_field
        #: ``{param: {"label": ..., "options": [(value, label), ...]}}``
        self.selects = selects or {}

    def apply(self, queryset, request):
        queryset = apply_search(queryset, request.GET.get("q"), self.search_fields)
        queryset = apply_choice_filters(queryset, request, self.choices)
        if self.date_field:
            queryset = apply_date_range(queryset, request, self.date_field)
        return queryset

    def params(self):
        """Every query parameter this spec reads."""
        names = {"q"} | set(self.choices) | set(self.selects)
        if self.date_field:
            names |= {"date_from", "date_to"}
        return names

    def is_active(self, request):
        """Whether the reader has narrowed the list at all.

        The empty state needs to tell "nobody has added one yet" apart from
        "your search matched nothing", and only the spec knows which
        parameters count as a filter here.
        """
        return any(request.GET.get(name) for name in self.params())

    def as_context(self, request):
        selects = []
        for param, spec in self.selects.items():
            selects.append(
                {
                    "param": param,
                    "label": spec.get("label", param),
                    "options": spec.get("options", []),
                    "value": request.GET.get(param, ""),
                }
            )
        return {
            "filter_search": request.GET.get("q", ""),
            "filter_has_search": bool(self.search_fields),
            "filter_selects": selects,
            "filter_has_dates": bool(self.date_field),
            "filter_date_from": request.GET.get("date_from", ""),
            "filter_date_to": request.GET.get("date_to", ""),
            "filter_active": self.is_active(request),
        }
