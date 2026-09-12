"""Class structure list presentation.

Keeps the existing SchoolClass CRUD/list screen and shared table architecture,
but exposes the related structure counts administrators need at a glance.
"""

from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from .models import ClassSubject, SchoolClass, Section, TeacherAssignment
from .views import SchoolClassListView as BaseSchoolClassListView


class SchoolClassListView(BaseSchoolClassListView):
    """Show each class together with its related academic structure counts."""

    page_subtitle = _("Classes and their sections form one academic structure.")

    table_columns = (
        {"label": _("Class"), "field": "name"},
        {"label": _("Sections"), "field": "section_count"},
        {"label": _("Subjects"), "field": "subject_count"},
        {"label": _("Teachers"), "field": "teacher_count"},
        {"label": _("Students"), "field": "student_count"},
        {"label": _("Status"), "field": "is_active", "type": "bool"},
    )

    def get_list_queryset(self):
        queryset = super().get_list_queryset()
        return queryset.prefetch_related(
            Prefetch("sections", queryset=Section.objects.for_user(self.request.user, self.active_branch)),
            Prefetch(
                "class_subjects",
                queryset=ClassSubject.objects.for_user(self.request.user, self.active_branch).prefetch_related(
                    Prefetch(
                        "teacher_assignments",
                        queryset=TeacherAssignment.objects.for_user(
                            self.request.user, self.active_branch
                        ),
                    )
                ),
            ),
            "enrollments",
        )
