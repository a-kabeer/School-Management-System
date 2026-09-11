from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    path("grades/", views.GradeListView.as_view(), name="grade_list"),
    path("grades/new/", views.GradeCreateView.as_view(), name="grade_create"),
    path("grades/<uuid:pk>/edit/", views.GradeUpdateView.as_view(), name="grade_update"),

    path("terms/", views.ExamTermListView.as_view(), name="term_list"),
    path("terms/new/", views.ExamTermCreateView.as_view(), name="term_create"),
    path("terms/<uuid:pk>/edit/", views.ExamTermUpdateView.as_view(), name="term_update"),

    path("", views.ExamListView.as_view(), name="exam_list"),
    path("new/", views.ExamCreateView.as_view(), name="exam_create"),
    path("<uuid:pk>/", views.ExamDetailView.as_view(), name="exam_detail"),
    path("<uuid:pk>/edit/", views.ExamUpdateView.as_view(), name="exam_update"),
    path("<uuid:pk>/register/", views.ExamRegisterView.as_view(), name="exam_register"),
    path("<uuid:pk>/generate/", views.GenerateResultsView.as_view(), name="exam_generate"),
    path("<uuid:pk>/publish/", views.PublishResultsView.as_view(), name="exam_publish"),

    path("subjects/new/", views.ExamSubjectCreateView.as_view(), name="subject_create"),
    path("subjects/<uuid:pk>/marks/", views.MarkEntryView.as_view(), name="mark_entry"),
    path("schedules/new/", views.ExamScheduleCreateView.as_view(), name="schedule_create"),

    path("results/", views.ResultListView.as_view(), name="result_list"),
    path("results/<uuid:pk>/", views.ReportCardView.as_view(), name="report_card"),
]
