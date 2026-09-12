"""Contextual detail view for the Class → Section workflow."""

from django.urls import reverse

from .detail_views import SectionDetailView as BaseSectionDetailView


class SectionDetailView(BaseSectionDetailView):
    """Treat a section as part of its parent class, not a separate workflow."""

    back_label = "Back to class"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_url"] = reverse(
            "academics:class_detail", args=[self.object.school_class_id]
        )
        return context
