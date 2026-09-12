"""Shared browser-print document endpoint for Academics."""

from django.views.generic import TemplateView

from apps.core.mixins import ActiveBranchMixin, BreadcrumbMixin
from apps.core.permissions import PermissionRequiredMixin

from .documents import render_document


class AcademicDocumentView(PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView):
    template_name = "academics/documents/document.html"
    required_permission = "core.access_academics"
    page_title = "Academic Document"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(render_document(self.request, self.kwargs["document_type"]))
        context["page_title"] = context["definition"].title
        context["generated_at"] = __import__("django.utils.timezone", fromlist=["now"]).now()
        return context
