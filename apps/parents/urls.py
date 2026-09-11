from django.urls import path

from . import views

app_name = "parents"

urlpatterns = [
    path("portal/", views.PortalHomeView.as_view(), name="portal_home"),
    path("portal/child/<uuid:pk>/", views.ChildDetailView.as_view(), name="child_detail"),
    path("portal/requests/new/", views.ParentRequestCreateView.as_view(), name="request_create"),

    path("accounts/", views.GuardianAccountListView.as_view(), name="guardian_list"),
    path("requests/", views.ParentRequestListView.as_view(), name="request_list"),
    path("requests/<uuid:pk>/respond/", views.ParentRequestRespondView.as_view(), name="request_respond"),
]
