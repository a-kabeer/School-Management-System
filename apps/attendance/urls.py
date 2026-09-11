from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.SessionListView.as_view(), name="session_list"),
    path("today/", views.TodayPeriodsView.as_view(), name="today"),
    path("sessions/<uuid:pk>/", views.SessionDetailView.as_view(), name="session_detail"),
    path("mark/", views.MarkAttendanceView.as_view(), name="mark"),
    path("slot/<uuid:pk>/", views.SubjectRegisterView.as_view(), name="slot_register"),
    path("records/", views.StudentAttendanceListView.as_view(), name="record_list"),

    path("staff/", views.StaffAttendanceListView.as_view(), name="staff_list"),
    path("staff/clock/", views.StaffClockView.as_view(), name="clock"),
    path("staff/month/", views.StaffMonthlyReportView.as_view(), name="staff_month"),
    path("staff/<uuid:pk>/correct/", views.StaffCorrectionView.as_view(), name="staff_correct"),
]
