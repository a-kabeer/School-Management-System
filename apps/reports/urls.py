from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportIndexView.as_view(), name="index"),
    path("saved/", views.SavedReportListView.as_view(), name="saved_list"),
    path("<slug:key>/", views.ReportDetailView.as_view(), name="detail"),
]
