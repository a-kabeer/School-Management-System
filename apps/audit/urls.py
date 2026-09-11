from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.ActivityLogListView.as_view(), name="list"),
    path("<int:pk>/", views.ActivityLogDetailView.as_view(), name="detail"),
]
