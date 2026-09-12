"""Contextual detail views for the Class → Section workflow."""

from django.utils.translation import gettext_lazy as _

from .detail_views import SectionDetailView as BaseSectionDetailView


class SectionDetailView(BaseSectionDetailView):
    """Treat a section as part of its parent class, not a separate workflow."""

    back_url_name = "academics:class_detail"
    back_label = _("Back to class")
