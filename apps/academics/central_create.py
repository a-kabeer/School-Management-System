"""Single Academics creation entry point.

The chooser and all resource forms share one modal endpoint. Existing
resource-specific create views remain available for direct/bookmarked URLs
and backwards compatibility; the UI enters creation here.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import resolve
from django.utils.http import url_has_allowed_host_and_scheme
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

CONTEXT_FIELDS = {
    "year_detail": {"academic_year": "pk"},
    "class_detail": {"school_class": "pk"},
    "section_detail": {"school_class": "school_class_id", "section": "pk"},
    "subject_detail": {"subject": "pk"},
    "classsubject_detail": {
        "academic_year": "academic_year_id", "school_class": "school_class_id",
        "subject": "subject_id", "class_subject": "pk",
    },
    "assignment_detail": {
        "academic_year": "academic_year_id", "teacher": "teacher_id",
        "class_subject": "class_subject_id", "section": "section_id",
    },
    "timetable_detail": {
        "academic_year": "academic_year_id", "section": "section_id",
        "class_subject": "class_subject_id", "teacher": "teacher_id",
    },
}

FORM_TABS = {
    "teacher_assignment": [
        (_("Assignment"), ["assignment_type", "academic_year", "teacher"]),
        (_("Class & Subject"), ["class_subject", "section"]),
        (_("Status"), ["is_active"]),
    ],
    "timetable": [
        (_("Lesson"), ["academic_year", "section", "class_subject", "teacher"]),
        (_("Schedule"), ["weekday", "period", "start_time", "end_time"]),
        (_("Room & Review"), ["room"]),
    ],
    "class": [
        (_("Basic Details"), ["name", "code", "level", "description"]),
        (_("Settings"), ["is_active"]),
    ],
}


class AcademicsCreateView(PermissionRequiredMixin, View):
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

    def get_return_to(self):
        value = self.request.GET.get("return_to") or self.request.POST.get("return_to")
        if value and url_has_allowed_host_and_scheme(
            value, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return value
        return None

    def get_form(self, form_class):
        model = form_class.Meta.model
        field_names = {field.name for field in model._meta.fields}
        initial = {
            key: value for key, value in self.request.GET.items()
            if key in field_names and value
        }

        return_to = self.get_return_to()
        if return_to:
            try:
                match = resolve(return_to.split("?", 1)[0])
                mapping = CONTEXT_FIELDS.get(match.url_name, {})
                parent = model.objects.none()
                parent_model = None
                # Resolve the originating object from the detail URL without
                # trusting arbitrary ids across tenant boundaries. The form's
                # own scoped querysets remain the final security boundary.
                if mapping and match.kwargs.get("pk"):
                    for candidate_key in RESOURCES:
                        candidate_model = RESOURCES[candidate_key][1]
                        if candidate_model.__name__.lower().replace("school", "") in match.url_name.replace("_", ""):
                            parent_model = candidate_model
                            break
                if parent_model is not None:
                    parent = parent_model.objects.filter(pk=match.kwargs["pk"]).first()
                    if parent:
                        for field_name, source in mapping.items():
                            if field_name not in initial:
                                value = getattr(parent, source, None)
                                if value is not None:
                                    initial[field_name] = value
            except Exception:
                pass

        return form_class(
            branch=getattr(self.request, "active_branch", None),
            user=self.request.user,
            data=self.request.POST or None,
            files=self.request.FILES or None,
            initial=initial,
        )

    def form_sections(self, key, form):
        spec = FORM_TABS.get(key)
        if not spec:
            return []
        used = set()
        sections = []
        for label, names in spec:
            fields = [form[name] for name in names if name in form.fields]
            used.update(names)
            if fields:
                sections.append({"label": label, "fields": fields})
        remaining = [form[name] for name in form.fields if name not in used]
        if remaining:
            sections.append({"label": _("Additional"), "fields": remaining})
        return sections

    def context(self, **extra):
        available = {
            key: value for key, value in RESOURCES.items() if self.allowed(value[1])
        }
        return {"resources": available, **extra}

    def render_form(self, request, key, label, form, status=None):
        return TemplateResponse(
            request, self.template_name,
            self.context(
                resource_key=key,
                resource_label=label,
                form=form,
                form_sections=self.form_sections(key, form),
                return_to=self.get_return_to(),
            ), status=status,
        )

    def get(self, request, *args, **kwargs):
        key, label, form_class = self.get_resource()
        if not key:
            return TemplateResponse(request, self.template_name, self.context())
        model = RESOURCES[key][1]
        if not self.allowed(model):
            raise PermissionDenied
        return self.render_form(request, key, label, self.get_form(form_class))

    def post(self, request, *args, **kwargs):
        key, label, form_class = self.get_resource()
        if not key:
            raise Http404(_("Choose an academic resource first."))
        model = RESOURCES[key][1]
        if not self.allowed(model):
            raise PermissionDenied
        form = self.get_form(form_class)
        if not form.is_valid():
            return self.render_form(request, key, label, form, status=422)
        return modal_success(form.save())
