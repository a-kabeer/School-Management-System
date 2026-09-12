"""Context-aware wrappers for Academics create/update/delete workflows.

The existing CRUD views remain the source of truth. These wrappers only add
safe return-to-origin behavior, contextual defaults, and consistent feedback.
"""

from urllib.parse import parse_qs, urlparse

from django.contrib import messages
from django.urls import resolve
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


class AcademicsCreateContextMixin(PreserveReturnContextMixin):
    """Carry the parent record into a create form when launched contextually.

    Explicit query-string values win; otherwise the originating Academics
    detail page supplies the relevant parent IDs. This keeps contextual Add
    actions out of generic-list navigation without duplicating create views.
    """

    contextual_fields = {
        "year_detail": {"academic_year": "pk"},
        "class_detail": {"school_class": "pk"},
        "section_detail": {"school_class": "school_class_id", "section": "pk"},
        "subject_detail": {"subject": "pk"},
        "classsubject_detail": {
            "academic_year": "academic_year_id",
            "school_class": "school_class_id",
            "subject": "subject_id",
            "class_subject": "pk",
        },
        "assignment_detail": {
            "academic_year": "academic_year_id",
            "teacher": "teacher_id",
            "class_subject": "class_subject_id",
            "section": "section_id",
        },
        "timetable_detail": {
            "academic_year": "academic_year_id",
            "section": "section_id",
            "class_subject": "class_subject_id",
            "teacher": "teacher_id",
        },
    }

    def get_initial(self):
        initial = super().get_initial()

        # Explicit GET context is the highest-priority contextual input.
        for field_name in self.form_class.base_fields:
            value = self.request.GET.get(field_name)
            if value:
                initial[field_name] = value

        return_to = self.get_return_url()
        if not return_to:
            return initial

        parsed = urlparse(return_to)
        try:
            match = resolve(parsed.path)
        except Exception:
            return initial

        mapping = self.contextual_fields.get(match.url_name, {})
        query = parse_qs(parsed.query)
        for field_name, source in mapping.items():
            if field_name in initial and initial[field_name]:
                continue
            if source == "pk":
                value = match.kwargs.get("pk")
            else:
                value = query.get(source, [None])[0]
            if value:
                initial[field_name] = value
        return initial


class AcademicsCreateFeedbackMixin:
    """Show one consistent success message after a valid Academics create."""

    success_message = _("Created successfully.")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class AcademicYearCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.AcademicYearCreateView):
    pass
class TermCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.TermCreateView):
    pass
class SchoolClassCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.SchoolClassCreateView):
    pass
class SectionCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.SectionCreateView):
    pass
class SubjectCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.SubjectCreateView):
    pass
class ClassSubjectCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.ClassSubjectCreateView):
    pass
class TeacherAssignmentCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.TeacherAssignmentCreateView):
    pass
class TimetableCreateView(AcademicsCreateFeedbackMixin, AcademicsCreateContextMixin, views.TimetableCreateView):
    pass


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
