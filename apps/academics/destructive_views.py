"""Safer destructive workflows for the Academics module.

Academics records are often historical or referenced by other records. The
confirmation screen therefore explains dependencies and prefers deactivation
or closing instead of destructive deletion.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import TenantDeleteView
from apps.core.permissions import user_has_permission


class AcademicsSafeDeleteView(TenantDeleteView):
    template_name = "academics/safe_delete.html"
    dependants = ()
    prefer_deactivation = False
    archive_field = "is_active"
    archive_action_label = _("Deactivate instead")
    archive_explanation = _(
        "Deactivation keeps the record and its history while preventing it "
        "from being used in new workflows."
    )
    success_url_name = None
    _update_url_name = None

    def get_dependants(self):
        found = []
        for name, label in self.dependants:
            manager = getattr(self.object, name, None)
            if manager is None or not hasattr(manager, "count"):
                continue
            count = manager.count()
            if count:
                found.append({"label": label, "count": count})
        return found

    def deletion_blocked(self):
        return bool(self.get_dependants()) or self.prefer_deactivation

    def get_return_url(self):
        target = self.request.POST.get("return_to") or self.request.GET.get("return_to")
        if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return target
        return None

    def get_success_url(self):
        return self.get_return_url() or reverse(self.success_url_name)

    def get_archive_url(self):
        if not self.archive_field or not self._update_url_name or not hasattr(self.object, self.archive_field):
            return None
        permission = f"{self.model._meta.app_label}.change_{self.model._meta.model_name}"
        if not user_has_permission(self.request.user, permission, self.active_branch):
            return None
        return reverse(self._update_url_name, args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dependencies = self.get_dependants()
        context.update({
            "dependants": dependencies,
            "deletion_blocked": bool(dependencies) or self.prefer_deactivation,
            "archive_url": self.get_archive_url(),
            "archive_action_label": self.archive_action_label,
            "archive_explanation": self.archive_explanation,
            "has_dependencies": bool(dependencies),
            "return_to": self.get_return_url(),
        })
        return context

    def form_valid(self, form):
        if self.deletion_blocked():
            messages.error(
                self.request,
                _(
                    "Deletion is blocked because this record is historical or "
                    "still used by other Academics records. Deactivate or close it instead."
                ),
            )
            return HttpResponseRedirect(self.get_success_url())
        response = super().form_valid(form)
        messages.success(self.request, _("Record deleted permanently."))
        return response


class AcademicYearSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("terms", _("Terms")), ("class_subjects", _("Class Subjects")), ("teacher_assignments", _("Teacher Assignments")), ("timetable_slots", _("Timetable Slots")), ("enrollments", _("Enrollments")))
    prefer_deactivation = True
    archive_field = "is_closed"
    archive_action_label = _("Close / archive instead")
    archive_explanation = _("Closing an Academic Year preserves its classes, assignments, timetable records and enrollment history.")
    success_url_name = "academics:year_list"
    _update_url_name = "academics:year_update"


class TermSafeDeleteView(AcademicsSafeDeleteView):
    success_url_name = "academics:term_list"
    _update_url_name = "academics:term_update"
    archive_field = None


class SchoolClassSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("sections", _("Sections")), ("class_subjects", _("Class Subjects")), ("enrollments", _("Enrollments")))
    prefer_deactivation = True
    success_url_name = "academics:class_list"
    _update_url_name = "academics:class_update"


class SectionSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("enrollments", _("Enrollments")), ("teacher_assignments", _("Teacher Assignments")), ("timetable_slots", _("Timetable Slots")))
    prefer_deactivation = True
    success_url_name = "academics:section_list"
    _update_url_name = "academics:section_update"


class SubjectSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("class_subjects", _("Class Subjects")),)
    prefer_deactivation = True
    success_url_name = "academics:subject_list"
    _update_url_name = "academics:subject_update"


class ClassSubjectSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("teacher_assignments", _("Teacher Assignments")), ("timetable_slots", _("Timetable Slots")))
    prefer_deactivation = True
    success_url_name = "academics:classsubject_list"
    _update_url_name = "academics:classsubject_update"


class TeacherAssignmentSafeDeleteView(AcademicsSafeDeleteView):
    prefer_deactivation = True
    success_url_name = "academics:assignment_list"
    _update_url_name = "academics:assignment_update"


class TimetableSafeDeleteView(AcademicsSafeDeleteView):
    # Timetable slots have no child records in the current schema, so deletion
    # remains available for correcting an erroneous schedule entry. The UI
    # explicitly warns that deletion is permanent.
    archive_field = None
    success_url_name = "academics:timetable"
    _update_url_name = "academics:timetable_update"
