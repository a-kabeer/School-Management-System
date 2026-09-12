"""Context-aware wrappers for Academics update/delete workflows.

The existing CRUD views remain the source of truth. These wrappers only add
safe return-to-list behavior and consistent success feedback.
"""

from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from . import views


class PreserveReturnContextMixin:
    """Return to the exact in-app URL supplied by the originating workflow."""

    return_param = "return_to"

    def get_return_url(self):
        target = self.request.POST.get(self.return_param) or self.request.GET.get(
            self.return_param
        )
        if target and url_has_allowed_host_and_scheme(
            target,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return target
        return None

    def get_success_url(self):
        return self.get_return_url() or super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["return_to"] = self.get_return_url()
        return context


class AcademicsUpdateFeedbackMixin:
    """Show one consistent success message after a valid Academics edit."""

    success_message = _("Changes saved successfully.")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class AcademicYearUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.AcademicYearUpdateView):
    pass
class AcademicYearDeleteView(PreserveReturnContextMixin, views.AcademicYearDeleteView):
    pass
class TermUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.TermUpdateView):
    pass
class TermDeleteView(PreserveReturnContextMixin, views.TermDeleteView):
    pass
class SchoolClassUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.SchoolClassUpdateView):
    pass
class SchoolClassDeleteView(PreserveReturnContextMixin, views.SchoolClassDeleteView):
    pass
class SectionUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.SectionUpdateView):
    pass
class SectionDeleteView(PreserveReturnContextMixin, views.SectionDeleteView):
    pass
class SubjectUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.SubjectUpdateView):
    pass
class SubjectDeleteView(PreserveReturnContextMixin, views.SubjectDeleteView):
    pass
class ClassSubjectUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.ClassSubjectUpdateView):
    pass
class ClassSubjectDeleteView(PreserveReturnContextMixin, views.ClassSubjectDeleteView):
    pass
class TeacherAssignmentUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.TeacherAssignmentUpdateView):
    pass
class TeacherAssignmentDeleteView(PreserveReturnContextMixin, views.TeacherAssignmentDeleteView):
    pass
class TimetableUpdateView(AcademicsUpdateFeedbackMixin, PreserveReturnContextMixin, views.TimetableUpdateView):
    pass
class TimetableDeleteView(PreserveReturnContextMixin, views.TimetableDeleteView):
    pass
