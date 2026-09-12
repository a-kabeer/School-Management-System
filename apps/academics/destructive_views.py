"""Safer destructive workflows for the Academics module.

Academics records are often historical or referenced by other records. The
confirmation screen therefore explains dependencies and prefers deactivation
or closing instead of destructive deletion.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import TenantDeleteView
from apps.core.permissions import user_has_permission


class AcademicsSafeDeleteView(TenantDeleteView):
    """Dependency-aware delete confirmation used by Academics records."""

    template_name = "academics/safe_delete.html"
    dependants = ()
    prefer_deactivation = False
    archive_field = "is_active"
    archive_action_label = _("Deactivate instead")
    archive_explanation = _(
        "Deactivation keeps the record and its history while preventing it "
        "from being used in new workflows."
    )

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

    def get_archive_url(self):
        if not self.archive_field:
            return None
        if not hasattr(self.object, self.archive_field):
            return None
        permission = f"{self.model._meta.app_label}.change_{self.model._meta.model_name}"
        if not user_has_permission(self.request.user, permission, self.active_branch):
            return None
        update_name = self.update_url_name
        if not update_name:
            return None
        return reverse(update_name, args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dependencies = self.get_dependants()
        blocked = bool(dependencies) or self.prefer_deactivation
        context.update(
            {
                "dependants": dependencies,
                "deletion_blocked": blocked,
                "archive_url": self.get_archive_url(),
                "archive_action_label": self.archive_action_label,
                "archive_explanation": self.archive_explanation,
                "has_dependencies": bool(dependencies),
            }
        )
        return context

    def form_valid(self, form):
        # Never let a crafted POST bypass the confirmation policy. The normal
        # Django FK protection remains the final integrity boundary as well.
        if self.deletion_blocked():
            messages.error(
                self.request,
                _(
                    "Deletion is blocked because this record is historical or "
                    "still used by other Academics records. Deactivate or close "
                    "it instead."
                ),
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)

    @property
    def update_url_name(self):
        return getattr(self, "_update_url_name", None)


class AcademicYearSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (
        ("terms", _("Terms")),
        ("class_subjects", _("Class Subjects")),
        ("teacher_assignments", _("Teacher Assignments")),
        ("timetable_slots", _("Timetable Slots")),
        ("enrollments", _("Enrollments")),
    )
    prefer_deactivation = True
    archive_field = "is_closed"
    archive_action_label = _("Close / archive instead")
    archive_explanation = _(
        "Closing an Academic Year preserves all of its classes, assignments, "
        "timetable records and enrollment history."
    )
    _update_url_name = "academics:year_update"


class SchoolClassSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (
        ("sections", _("Sections")),
        ("class_subjects", _("Class Subjects")),
        ("enrollments", _("Enrollments")),
    )
    prefer_deactivation = True
    _update_url_name = "academics:class_update"


class SubjectSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (("class_subjects", _("Class Subjects")),)
    prefer_deactivation = True
    _update_url_name = "academics:subject_update"


class ClassSubjectSafeDeleteView(AcademicsSafeDeleteView):
    dependants = (
        ("teacher_assignments", _("Teacher Assignments")),
        ("timetable_slots", _("Timetable Slots")),
    )
    prefer_deactivation = True
    _update_url_name = "academics:classsubject_update"


class TeacherAssignmentSafeDeleteView(AcademicsSafeDeleteView):
    prefer_deactivation = True
    _update_url_name = "academics:assignment_update"


class TimetableSafeDeleteView(AcademicsSafeDeleteView):
    # Timetable slots have no child records in the current schema, so deletion
    # remains available for correcting an erroneous schedule entry. The UI
    # explicitly warns that deletion is permanent and should not replace
    # retaining a useful historical schedule.
    prefer_deactivation = False
    archive_field = None
    _update_url_name = "academics:timetable_update"
