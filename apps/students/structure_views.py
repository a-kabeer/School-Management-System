"""Contextual student list filtering used by academic structure pages."""

from django.utils.translation import gettext_lazy as _

from apps.academics.models import Section

from .views import StudentListView as BaseStudentListView


class StudentListView(BaseStudentListView):
    """Keep the existing student list while adding section context."""

    def get_list_queryset(self):
        queryset = super().get_list_queryset()
        section_id = self.request.GET.get("section")
        if section_id:
            queryset = queryset.filter(
                enrollments__section_id=section_id,
                enrollments__is_current=True,
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = Section.objects.for_user(
            self.request.user, self.active_branch
        ).select_related("school_class").order_by("school_class__level", "name")
        context["filter_selects"] = context.get("filter_selects", []) + [
            {
                "param": "section",
                "label": _("Section"),
                "options": [(str(section.pk), str(section)) for section in sections],
                "value": self.request.GET.get("section", ""),
            }
        ]
        return context
