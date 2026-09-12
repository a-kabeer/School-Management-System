"""Single Academics creation entry point.

The chooser and all resource forms share this one modal endpoint. Existing
resource-specific create views remain available for direct/bookmarked URLs and
for backwards compatibility, but the UI enters creation here.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.core.modals import modal_success
from apps.core.permissions import PermissionRequiredMixin, user_has_permission

from .forms import (
    AcademicYearForm, ClassSubjectForm, SchoolClassForm, SectionForm,
    SubjectForm, TeacherAssignmentForm, TermForm, TimetableForm,
)
from .models import (
    AcademicYear, ClassSubject, SchoolClass, Section, Subject,
    TeacherAssignment, Term, Timetable,
)

RESOURCES = {
    "academic_year": (_("Academic Year"), AcademicYear, AcademicYearForm),
    "term": (_("Term"), Term, TermForm),
    "class": (_("Class"), SchoolClass, SchoolClassForm),
    "section": (_("Section"), Section, SectionForm),
    "subject": (_("Subject"), Subject, SubjectForm),
    "class_subject": (_("Class Subject"), ClassSubject, ClassSubjectForm),
    "teacher_assignment": (_("Teacher Assignment"), TeacherAssignment, TeacherAssignmentForm),
    "timetable": (_("Timetable"), Timetable, TimetableForm),
}


class AcademicsCreateView(PermissionRequiredMixin, View):
    """Render the chooser or one of the existing Academics forms."""

    required_permission = "core.access_academics"
    template_name = "academics/central_create.html"

    def get_resource(self):
        key = self.request.GET.get("resource") or self.request.POST.get("resource")
        if not key:
            return None, None, None
        try:
            return key, *RESOURCES[key]
        except KeyError:
            raise Http404(_("Unknown academic resource."))

    def allowed(self, model):
        return user_has_permission(
            self.request.user,
            f"academics.add_{model._meta.model_name}",
            getattr(self.request, "active_branch", None),
        )

    def get_form(self, form_class):
        model = form_class.Meta.model
        field_names = set(model._meta.get_field(name).name for name in model._meta.fields)
        initial = {
            key: value for key, value in self.request.GET.items()
            if key in field_names and value
        }
        return form_class(
            branch=getattr(self.request, "active_branch", None),
            user=self.request.user,
            data=self.request.POST or None,
            files=self.request.FILES or None,
            initial=initial,
        )

    def context(self, **extra):
        available = {
            key: value for key, value in RESOURCES.items() if self.allowed(value[1])
        }
        return {"resources": available, **extra}

    def get(self, request, *args, **kwargs):
        key, label, form_class = self.get_resource()
        if not key:
            return TemplateResponse(request, self.template_name, self.context())
        model = RESOURCES[key][1]
        if not self.allowed(model):
            raise PermissionDenied
        return TemplateResponse(request, self.template_name, self.context(
            resource_key=key,
            resource_label=label,
            form=self.get_form(form_class),
        ))

    def post(self, request, *args, **kwargs):
        key, label, form_class = self.get_resource()
        if not key:
            raise Http404(_("Choose an academic resource first."))
        model = RESOURCES[key][1]
        if not self.allowed(model):
            raise PermissionDenied
        form = self.get_form(form_class)
        if not form.is_valid():
            return TemplateResponse(request, self.template_name, self.context(
                resource_key=key,
                resource_label=label,
                form=form,
            ), status=422)
        obj = form.save()
        return modal_success(obj)
