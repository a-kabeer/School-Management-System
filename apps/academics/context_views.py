"""Context-aware wrappers for Academics update/delete workflows.

The existing CRUD views remain the source of truth. These wrappers only add
safe return-to-list behavior when a user arrived with explicit list context.
"""

from django.utils.http import url_has_allowed_host_and_scheme

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


class AcademicYearUpdateView(PreserveReturnContextMixin, views.AcademicYearUpdateView):
    pass
class AcademicYearDeleteView(PreserveReturnContextMixin, views.AcademicYearDeleteView):
    pass
class TermUpdateView(PreserveReturnContextMixin, views.TermUpdateView):
    pass
class TermDeleteView(PreserveReturnContextMixin, views.TermDeleteView):
    pass
class SchoolClassUpdateView(PreserveReturnContextMixin, views.SchoolClassUpdateView):
    pass
class SchoolClassDeleteView(PreserveReturnContextMixin, views.SchoolClassDeleteView):
    pass
class SectionUpdateView(PreserveReturnContextMixin, views.SectionUpdateView):
    pass
class SectionDeleteView(PreserveReturnContextMixin, views.SectionDeleteView):
    pass
class SubjectUpdateView(PreserveReturnContextMixin, views.SubjectUpdateView):
    pass
class SubjectDeleteView(PreserveReturnContextMixin, views.SubjectDeleteView):
    pass
class ClassSubjectUpdateView(PreserveReturnContextMixin, views.ClassSubjectUpdateView):
    pass
class ClassSubjectDeleteView(PreserveReturnContextMixin, views.ClassSubjectDeleteView):
    pass
class TeacherAssignmentUpdateView(PreserveReturnContextMixin, views.TeacherAssignmentUpdateView):
    pass
class TeacherAssignmentDeleteView(PreserveReturnContextMixin, views.TeacherAssignmentDeleteView):
    pass
class TimetableUpdateView(PreserveReturnContextMixin, views.TimetableUpdateView):
    pass
class TimetableDeleteView(PreserveReturnContextMixin, views.TimetableDeleteView):
    pass
