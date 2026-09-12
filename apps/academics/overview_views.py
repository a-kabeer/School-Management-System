from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from .models import AcademicYear, ClassSubject, SchoolClass, Section, Subject, TeacherAssignment, Term, Timetable


class AcademicsOverviewView(LoginRequiredMixin, TemplateView):
    template_name = "academics/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        branch = getattr(self.request, "active_branch", None)
        user = self.request.user

        records = [
            (_("Academic Years"), AcademicYear.objects.for_user(user, branch), "academics:year_list", "bi-calendar3"),
            (_("Terms"), Term.objects.for_user(user, branch), "academics:term_list", "bi-calendar2-week"),
            (_("Classes & Sections"), SchoolClass.objects.for_user(user, branch), "academics:class_list", "bi-diagram-3"),
            (_("Subjects"), Subject.objects.for_user(user, branch), "academics:subject_list", "bi-book"),
            (_("Class Subjects"), ClassSubject.objects.for_user(user, branch), "academics:classsubject_list", "bi-journal-check"),
            (_("Teacher Assignments"), TeacherAssignment.objects.for_user(user, branch), "academics:assignment_list", "bi-person-workspace"),
            (_("Timetable"), Timetable.objects.for_user(user, branch), "academics:timetable", "bi-calendar-week"),
        ]
        context["academic_cards"] = [
            {"label": label, "count": queryset.count(), "url": reverse(url_name), "icon": icon}
            for label, queryset, url_name, icon in records
        ]
        context["current_year"] = AcademicYear.objects.for_user(user, branch).filter(is_current=True).first()
        return context
