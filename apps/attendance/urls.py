from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.SessionListView.as_view(), name="session_list"),
    path("sessions/<uuid:pk>/", views.SessionDetailView.as_view(), name="session_detail"),
    path("mark/", views.MarkAttendanceView.as_view(), name="mark"),
    path("records/", views.StudentAttendanceListView.as_view(), name="record_list"),
    path("staff/", views.StaffAttendanceListView.as_view(), name="staff_list"),
]
