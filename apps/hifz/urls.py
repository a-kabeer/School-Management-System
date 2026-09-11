from django.urls import path

from . import views

app_name = "hifz"

urlpatterns = [
    path("", views.HifzProfileListView.as_view(), name="profile_list"),
    path("new/", views.HifzProfileCreateView.as_view(), name="profile_create"),
    path("<uuid:pk>/", views.HifzProfileDetailView.as_view(), name="profile_detail"),
    path("<uuid:pk>/edit/", views.HifzProfileUpdateView.as_view(), name="profile_update"),

    path("progress/", views.ProgressListView.as_view(), name="progress_list"),
    path("progress/new/", views.ProgressCreateView.as_view(), name="progress_create"),
    path("progress/<uuid:pk>/edit/", views.ProgressUpdateView.as_view(), name="progress_update"),
    path("progress/<uuid:pk>/delete/", views.ProgressDeleteView.as_view(), name="progress_delete"),

    path("revisions/", views.RevisionListView.as_view(), name="revision_list"),
    path("revisions/new/", views.RevisionCreateView.as_view(), name="revision_create"),
    path("revisions/<uuid:pk>/edit/", views.RevisionUpdateView.as_view(), name="revision_update"),

    path("assessments/", views.AssessmentListView.as_view(), name="assessment_list"),
    path("assessments/new/", views.AssessmentCreateView.as_view(), name="assessment_create"),
    path("assessments/<uuid:pk>/edit/", views.AssessmentUpdateView.as_view(), name="assessment_update"),

    path("teachers/", views.TeacherAssignmentListView.as_view(), name="teacher_list"),
    path("teachers/new/", views.TeacherAssignmentCreateView.as_view(), name="teacher_create"),
    path("teachers/<uuid:pk>/edit/", views.TeacherAssignmentUpdateView.as_view(), name="teacher_update"),
]
