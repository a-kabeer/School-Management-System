from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("", views.StaffListView.as_view(), name="staff_list"),
    path("new/", views.StaffCreateView.as_view(), name="staff_create"),
    path("<uuid:pk>/", views.StaffDetailView.as_view(), name="staff_detail"),
    path("<uuid:pk>/edit/", views.StaffUpdateView.as_view(), name="staff_update"),
    path("<uuid:pk>/delete/", views.StaffDeleteView.as_view(), name="staff_delete"),
    path("<uuid:pk>/status/", views.StaffStatusView.as_view(), name="staff_status"),

    path("departments/", views.DepartmentListView.as_view(), name="department_list"),
    path("departments/new/", views.DepartmentCreateView.as_view(), name="department_create"),
    path("departments/<uuid:pk>/edit/", views.DepartmentUpdateView.as_view(), name="department_update"),

    path("designations/", views.DesignationListView.as_view(), name="designation_list"),
    path("designations/new/", views.DesignationCreateView.as_view(), name="designation_create"),
    path("designations/<uuid:pk>/edit/", views.DesignationUpdateView.as_view(), name="designation_update"),

    path("documents/new/", views.StaffDocumentCreateView.as_view(), name="document_create"),
    path("assignments/new/", views.StaffAssignmentCreateView.as_view(), name="assignment_create"),
]
