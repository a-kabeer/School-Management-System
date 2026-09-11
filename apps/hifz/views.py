from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    TenantCreateView,
    TenantDeleteView,
    TenantDetailView,
    TenantListView,
    TenantUpdateView,
)

from .forms import (
    DailyProgressForm,
    HifzAssessmentForm,
    HifzStudentProfileForm,
    HifzTeacherAssignmentForm,
    RevisionForm,
)
from .models import (
    DailyProgress,
    HifzAssessment,
    HifzStudentProfile,
    HifzTeacherAssignment,
    LessonType,
    Revision,
)
from .services import progress_summary

HIFZ = "core.access_hifz"


class HifzProfileListView(TenantListView):
    model = HifzStudentProfile
    required_permission = HIFZ
    create_permission = "hifz.add_hifzstudentprofile"
    page_title = _("Hifz Students")
    select_related = ("student",)
    ordering = ["student__full_name"]
    create_url_name = "hifz:profile_create"
    detail_url_name = "hifz:profile_detail"
    update_url_name = "hifz:profile_update"
    filter_spec = FilterSpec(
        search_fields=("student__full_name", "student__admission_no"),
        choices={"stage": "stage"},
        selects={
            "stage": {"label": _("Stage"), "options": HifzStudentProfile.Stage.choices}
        },
    )
    table_columns = (
        {"label": _("Student"), "field": "student.full_name"},
        {"label": _("Stage"), "field": "stage", "type": "choice"},
        {"label": _("Current Para"), "field": "current_para"},
        {"label": _("Paras Memorized"), "field": "paras_memorized"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class HifzProfileDetailView(TenantDetailView):
    model = HifzStudentProfile
    required_permission = HIFZ
    template_name = "hifz/profile_detail.html"
    select_related = ("student",)

    def get_page_title(self):
        return str(self.object.student)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["progress"] = (
            self.object.daily_progress.select_related("teacher").order_by("-date")[:30]
        )
        context["revisions"] = self.object.revisions.select_related("teacher")[:10]
        context["assessments"] = self.object.assessments.select_related("examiner")[:10]
        context["summary"] = progress_summary(
            self.request.user, self.active_branch, hifz_profile=self.object
        )
        context["lesson_types"] = LessonType.choices
        return context


class HifzProfileCreateView(TenantCreateView):
    model = HifzStudentProfile
    form_class = HifzStudentProfileForm
    required_permission = "hifz.add_hifzstudentprofile"
    page_title = _("New Hifz Student")

    def get_success_url(self):
        return reverse("hifz:profile_detail", args=[self.object.pk])


class HifzProfileUpdateView(TenantUpdateView):
    model = HifzStudentProfile
    form_class = HifzStudentProfileForm
    required_permission = "hifz.change_hifzstudentprofile"
    page_title = _("Edit Hifz Student")

    def get_success_url(self):
        return reverse("hifz:profile_detail", args=[self.object.pk])


class ProgressListView(TenantListView):
    model = DailyProgress
    required_permission = HIFZ
    create_permission = "hifz.add_dailyprogress"
    page_title = _("Daily Progress")
    select_related = ("hifz_profile__student", "teacher")
    ordering = ["-date"]
    create_url_name = "hifz:progress_create"
    update_url_name = "hifz:progress_update"
    delete_url_name = "hifz:progress_delete"
    filter_spec = FilterSpec(
        search_fields=("hifz_profile__student__full_name",),
        choices={"lesson_type": "lesson_type"},
        date_field="date",
        selects={
            "lesson_type": {"label": _("Lesson"), "options": LessonType.choices}
        },
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Student"), "field": "hifz_profile.student.full_name"},
        {"label": _("Lesson"), "field": "lesson_type", "type": "choice"},
        {"label": _("Para"), "field": "to_para"},
        {"label": _("Pages"), "field": "pages"},
        {"label": _("Mistakes"), "field": "mistakes"},
        {"label": _("Teacher"), "field": "teacher.full_name"},
    )


class ProgressCreateView(TenantCreateView):
    model = DailyProgress
    form_class = DailyProgressForm
    required_permission = "hifz.add_dailyprogress"
    success_url = reverse_lazy("hifz:progress_list")
    page_title = _("Record Progress")


class ProgressUpdateView(TenantUpdateView):
    model = DailyProgress
    form_class = DailyProgressForm
    required_permission = "hifz.change_dailyprogress"
    success_url = reverse_lazy("hifz:progress_list")
    page_title = _("Edit Progress")


class ProgressDeleteView(TenantDeleteView):
    model = DailyProgress
    required_permission = "hifz.delete_dailyprogress"
    success_url = reverse_lazy("hifz:progress_list")
    page_title = _("Delete Progress")


class RevisionListView(TenantListView):
    model = Revision
    required_permission = HIFZ
    create_permission = "hifz.add_revision"
    page_title = _("Revisions")
    select_related = ("hifz_profile__student", "teacher")
    ordering = ["-scheduled_date"]
    create_url_name = "hifz:revision_create"
    update_url_name = "hifz:revision_update"
    filter_spec = FilterSpec(
        search_fields=("hifz_profile__student__full_name",),
        choices={"status": "status"},
        date_field="scheduled_date",
        selects={"status": {"label": _("Status"), "options": Revision.Status.choices}},
    )
    table_columns = (
        {"label": _("Scheduled"), "field": "scheduled_date", "type": "date"},
        {"label": _("Student"), "field": "hifz_profile.student.full_name"},
        {"label": _("Range"), "field": "from_para"},
        {"label": _("To"), "field": "to_para"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class RevisionCreateView(TenantCreateView):
    model = Revision
    form_class = RevisionForm
    required_permission = "hifz.add_revision"
    success_url = reverse_lazy("hifz:revision_list")
    page_title = _("Schedule Revision")


class RevisionUpdateView(TenantUpdateView):
    model = Revision
    form_class = RevisionForm
    required_permission = "hifz.change_revision"
    success_url = reverse_lazy("hifz:revision_list")
    page_title = _("Edit Revision")


class AssessmentListView(TenantListView):
    model = HifzAssessment
    required_permission = HIFZ
    create_permission = "hifz.add_hifzassessment"
    page_title = _("Hifz Assessments")
    select_related = ("hifz_profile__student", "examiner")
    ordering = ["-date"]
    create_url_name = "hifz:assessment_create"
    update_url_name = "hifz:assessment_update"
    filter_spec = FilterSpec(
        search_fields=("hifz_profile__student__full_name", "title"),
        choices={"result": "result"},
        date_field="date",
        selects={
            "result": {"label": _("Result"), "options": HifzAssessment.Result.choices}
        },
    )
    table_columns = (
        {"label": _("Date"), "field": "date", "type": "date"},
        {"label": _("Student"), "field": "hifz_profile.student.full_name"},
        {"label": _("Title"), "field": "title"},
        {"label": _("Marks"), "field": "obtained_marks"},
        {"label": _("Result"), "field": "result", "type": "choice"},
    )


class AssessmentCreateView(TenantCreateView):
    model = HifzAssessment
    form_class = HifzAssessmentForm
    required_permission = "hifz.add_hifzassessment"
    success_url = reverse_lazy("hifz:assessment_list")
    page_title = _("New Assessment")


class AssessmentUpdateView(TenantUpdateView):
    model = HifzAssessment
    form_class = HifzAssessmentForm
    required_permission = "hifz.change_hifzassessment"
    success_url = reverse_lazy("hifz:assessment_list")
    page_title = _("Edit Assessment")


class TeacherAssignmentListView(TenantListView):
    model = HifzTeacherAssignment
    required_permission = HIFZ
    create_permission = "hifz.add_hifzteacherassignment"
    page_title = _("Hifz Teacher Assignments")
    select_related = ("hifz_profile__student", "teacher")
    ordering = ["-start_date"]
    create_url_name = "hifz:teacher_create"
    update_url_name = "hifz:teacher_update"
    filter_spec = FilterSpec(
        search_fields=("teacher__full_name", "hifz_profile__student__full_name")
    )
    table_columns = (
        {"label": _("Student"), "field": "hifz_profile.student.full_name"},
        {"label": _("Teacher"), "field": "teacher.full_name"},
        {"label": _("From"), "field": "start_date", "type": "date"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class TeacherAssignmentCreateView(TenantCreateView):
    model = HifzTeacherAssignment
    form_class = HifzTeacherAssignmentForm
    required_permission = "hifz.add_hifzteacherassignment"
    success_url = reverse_lazy("hifz:teacher_list")
    page_title = _("Assign Hifz Teacher")


class TeacherAssignmentUpdateView(TenantUpdateView):
    model = HifzTeacherAssignment
    form_class = HifzTeacherAssignmentForm
    required_permission = "hifz.change_hifzteacherassignment"
    success_url = reverse_lazy("hifz:teacher_list")
    page_title = _("Edit Hifz Teacher Assignment")
