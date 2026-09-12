from django.urls import path

from . import structure_views, views

app_name = "students"

urlpatterns = [
    path("", structure_views.StudentListView.as_view(), name="student_list"),
    path("new/", views.StudentCreateView.as_view(), name="student_create"),
    path("search/", views.student_search_api, name="student_search"),
    path("archive/", views.StudentArchiveListView.as_view(), name="student_archive"),
    path("archive/<uuid:pk>/restore/", views.StudentRestoreView.as_view(), name="student_restore"),
    path("<uuid:pk>/", views.StudentDetailView.as_view(), name="student_detail"),
    path("<uuid:pk>/edit/", views.StudentUpdateView.as_view(), name="student_update"),
    path("<uuid:pk>/delete/", views.StudentDeleteView.as_view(), name="student_delete"),
    path("<uuid:pk>/status/", views.StudentStatusView.as_view(), name="student_status"),
    path("<uuid:pk>/transfer/", views.StudentTransferView.as_view(), name="student_transfer"),

    path("guardians/", views.GuardianListView.as_view(), name="guardian_list"),
    path("guardians/new/", views.GuardianCreateView.as_view(), name="guardian_create"),
    path("guardians/<uuid:pk>/edit/", views.GuardianUpdateView.as_view(), name="guardian_update"),
    path("guardians/link/", views.StudentGuardianCreateView.as_view(), name="guardian_link"),

    path("documents/new/", views.DocumentCreateView.as_view(), name="document_create"),

    path("enrollments/", views.EnrollmentListView.as_view(), name="enrollment_list"),
    path("enrollments/new/", views.EnrollmentCreateView.as_view(), name="enrollment_create"),
    path("enrollments/<uuid:pk>/edit/", views.EnrollmentUpdateView.as_view(), name="enrollment_update"),
]
