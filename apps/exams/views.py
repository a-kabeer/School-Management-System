from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantDetailView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin, require_permission

from .forms import ExamForm, ExamScheduleForm, ExamSubjectForm, ExamTermForm, GradeForm
from .models import (
    Exam,
    ExamSchedule,
    ExamSubject,
    ExamTerm,
    Grade,
    ResultSummary,
    StudentExam,
)
from .services import (
    generate_results,
    publish_results,
    register_students,
    report_card,
    save_marks,
    unpublish_results,
)

EXAMS = "core.access_exams"


class GradeListView(TenantListView):
    model = Grade
    required_permission = EXAMS
    create_permission = "exams.add_grade"
    page_title = _("Grading Scale")
    select_related = ("academic_year",)
    ordering = ["-min_percentage"]
    create_url_name = "exams:grade_create"
    update_url_name = "exams:grade_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Grade"), "field": "name"},
        {"label": _("From %"), "field": "min_percentage"},
        {"label": _("To %"), "field": "max_percentage"},
        {"label": _("Grade Point"), "field": "grade_point"},
        {"label": _("Pass"), "field": "is_pass", "type": "bool"},
    )


class GradeCreateView(TenantCreateView):
    model = Grade
    form_class = GradeForm
    required_permission = "exams.add_grade"
    success_url = reverse_lazy("exams:grade_list")
    page_title = _("New Grade")


class GradeUpdateView(TenantUpdateView):
    model = Grade
    form_class = GradeForm
    required_permission = "exams.change_grade"
    success_url = reverse_lazy("exams:grade_list")
    page_title = _("Edit Grade")


class ExamTermListView(TenantListView):
    model = ExamTerm
    required_permission = EXAMS
    create_permission = "exams.add_examterm"
    page_title = _("Exam Terms")
    select_related = ("academic_year", "term")
    ordering = ["academic_year", "sequence"]
    create_url_name = "exams:term_create"
    update_url_name = "exams:term_update"
    filter_spec = FilterSpec(search_fields=("name",))
    table_columns = (
        {"label": _("Academic Year"), "field": "academic_year.name"},
        {"label": _("Name"), "field": "name"},
        {"label": _("Sequence"), "field": "sequence"},
        {"label": _("Weight %"), "field": "weight_percentage"},
    )


class ExamTermCreateView(TenantCreateView):
    model = ExamTerm
    form_class = ExamTermForm
    required_permission = "exams.add_examterm"
    success_url = reverse_lazy("exams:term_list")
    page_title = _("New Exam Term")


class ExamTermUpdateView(TenantUpdateView):
    model = ExamTerm
    form_class = ExamTermForm
    required_permission = "exams.change_examterm"
    success_url = reverse_lazy("exams:term_list")
    page_title = _("Edit Exam Term")


class ExamListView(TenantListView):
    model = Exam
    required_permission = EXAMS
    create_permission = "exams.add_exam"
    page_title = _("Exams")
    select_related = ("exam_term", "school_class", "academic_year")
    ordering = ["-start_date"]
    create_url_name = "exams:exam_create"
    detail_url_name = "exams:exam_detail"
    update_url_name = "exams:exam_update"
    filter_spec = FilterSpec(
        search_fields=("name", "school_class__name"),
        choices={"status": "status"},
        date_field="start_date",
        selects={"status": {"label": _("Status"), "options": Exam.Status.choices}},
    )
    table_columns = (
        {"label": _("Name"), "field": "name"},
        {"label": _("Class"), "field": "school_class.name"},
        {"label": _("Term"), "field": "exam_term.name"},
        {"label": _("Start"), "field": "start_date", "type": "date"},
        {"label": _("Status"), "field": "status", "type": "choice"},
    )


class ExamDetailView(TenantDetailView):
    model = Exam
    required_permission = EXAMS
    template_name = "exams/exam_detail.html"
    select_related = ("exam_term", "school_class", "academic_year", "published_by")

    def get_page_title(self):
        return self.object.name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subjects"] = self.object.exam_subjects.select_related(
            "class_subject__subject"
        )
        context["registered"] = self.object.student_exams.count()
        context["summaries"] = (
            ResultSummary.objects.filter(student_exam__exam=self.object)
            .select_related("student_exam__student", "grade")
            .order_by("position")[:50]
        )
        return context


class ExamCreateView(TenantCreateView):
    model = Exam
    form_class = ExamForm
    required_permission = "exams.add_exam"
    success_url = reverse_lazy("exams:exam_list")
    page_title = _("New Exam")


class ExamUpdateView(TenantUpdateView):
    model = Exam
    form_class = ExamForm
    required_permission = "exams.change_exam"
    success_url = reverse_lazy("exams:exam_list")
    page_title = _("Edit Exam")


class ExamSubjectCreateView(TenantCreateView):
    model = ExamSubject
    form_class = ExamSubjectForm
    required_permission = "exams.add_examsubject"
    success_url = reverse_lazy("exams:exam_list")
    page_title = _("Add Exam Subject")


class ExamScheduleCreateView(TenantCreateView):
    model = ExamSchedule
    form_class = ExamScheduleForm
    required_permission = "exams.add_examschedule"
    success_url = reverse_lazy("exams:exam_list")
    page_title = _("Schedule Paper")


class ExamRegisterView(ActiveBranchMixin, View):
    def post(self, request, pk, *args, **kwargs):
        require_permission(request.user, "exams.add_studentexam", self.active_branch)
        exam = get_object_or_404(
            Exam.objects.for_user(request.user, self.active_branch), pk=pk
        )
        created = register_students(exam=exam, actor=request.user, request=request)
        messages.success(
            request, _("%(count)s students registered.") % {"count": len(created)}
        )
        return redirect("exams:exam_detail", pk=exam.pk)


class MarkEntryView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    """Enter a whole paper's marks on one screen."""

    template_name = "exams/mark_entry.html"
    required_permission = "exams.add_mark"
    page_title = _("Enter Marks")

    def get_exam_subject(self):
        return get_object_or_404(
            ExamSubject.objects.for_user(self.request.user, self.active_branch)
            .select_related("exam", "class_subject__subject"),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exam_subject = self.get_exam_subject()
        student_exams = (
            exam_subject.exam.student_exams.select_related("student")
            .prefetch_related("marks")
            .order_by("roll_number", "student__full_name")
        )
        existing = {
            mark.student_exam_id: mark
            for mark in exam_subject.marks.all()
        }
        context["exam_subject"] = exam_subject
        context["rows"] = [
            {"student_exam": se, "mark": existing.get(se.pk)} for se in student_exams
        ]
        return context

    def post(self, request, *args, **kwargs):
        exam_subject = self.get_exam_subject()
        student_exams = {
            str(se.pk): se for se in exam_subject.exam.student_exams.all()
        }

        entries = {}
        for key, value in request.POST.items():
            if not key.startswith("marks-"):
                continue
            student_exam = student_exams.get(key.removeprefix("marks-"))
            if student_exam is None:
                continue
            entries[student_exam] = {
                "obtained_marks": value or 0,
                "is_absent": request.POST.get(f"absent-{student_exam.pk}") == "on",
            }

        try:
            saved = save_marks(
                exam_subject=exam_subject,
                entries=entries,
                actor=request.user,
                request=request,
            )
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request, _("Marks saved for %(count)s students.") % {"count": saved}
            )
        return redirect("exams:mark_entry", pk=exam_subject.pk)


class GenerateResultsView(ActiveBranchMixin, View):
    def post(self, request, pk, *args, **kwargs):
        require_permission(request.user, "exams.change_exam", self.active_branch)
        exam = get_object_or_404(
            Exam.objects.for_user(request.user, self.active_branch), pk=pk
        )
        try:
            summaries = generate_results(exam=exam, actor=request.user, request=request)
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        else:
            messages.success(
                request,
                _("Results generated for %(count)s students.")
                % {"count": len(summaries)},
            )
        return redirect("exams:exam_detail", pk=exam.pk)


class PublishResultsView(ActiveBranchMixin, View):
    def post(self, request, pk, *args, **kwargs):
        require_permission(request.user, "core.publish_exam_result", self.active_branch)
        exam = get_object_or_404(
            Exam.objects.for_user(request.user, self.active_branch), pk=pk
        )
        action = request.POST.get("action", "publish")
        try:
            if action == "unpublish":
                unpublish_results(exam=exam, actor=request.user, request=request)
                messages.success(request, _("Results unpublished."))
            else:
                publish_results(exam=exam, actor=request.user, request=request)
                messages.success(request, _("Results published."))
        except ValidationError as error:
            messages.error(request, "; ".join(error.messages))
        return redirect("exams:exam_detail", pk=exam.pk)


class ResultListView(TenantListView):
    model = ResultSummary
    required_permission = EXAMS
    page_title = _("Results")
    select_related = ("student_exam__student", "student_exam__exam", "grade")
    ordering = ["-created_at"]
    detail_url_name = "exams:report_card"
    filter_spec = FilterSpec(
        search_fields=(
            "student_exam__student__full_name",
            "student_exam__exam__name",
        ),
        choices={"outcome": "outcome"},
        selects={
            "outcome": {"label": _("Outcome"), "options": ResultSummary.Outcome.choices}
        },
    )
    table_columns = (
        {"label": _("Student"), "field": "student_exam.student.full_name"},
        {"label": _("Exam"), "field": "student_exam.exam.name"},
        {"label": _("Obtained"), "field": "obtained_marks"},
        {"label": _("Total"), "field": "total_marks"},
        {"label": _("Percentage"), "field": "percentage"},
        {"label": _("Grade"), "field": "grade.name"},
        {"label": _("Position"), "field": "position"},
        {"label": _("Outcome"), "field": "outcome", "type": "choice"},
    )


class ReportCardView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, TemplateView
):
    template_name = "exams/report_card.html"
    required_permission = EXAMS
    page_title = _("Report Card")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = (
            ResultSummary.objects.for_user(self.request.user, self.active_branch)
            .select_related("student_exam__student", "student_exam__exam", "grade")
            .filter(pk=self.kwargs["pk"])
            .first()
        )
        if summary is None:
            raise Http404(_("Record not found."))
        context.update(report_card(summary.student_exam))
        return context
