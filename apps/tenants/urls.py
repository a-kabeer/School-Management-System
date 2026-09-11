from django.urls import path

from . import views

app_name = "tenants"

urlpatterns = [
    path("switch-branch/", views.switch_branch_view, name="switch_branch"),
    path("branches/", views.BranchListView.as_view(), name="branch_list"),
    path("branches/new/", views.BranchCreateView.as_view(), name="branch_create"),
    path("branches/<uuid:pk>/edit/", views.BranchUpdateView.as_view(), name="branch_update"),
    path("organization/", views.OrganizationUpdateView.as_view(), name="organization"),
]
