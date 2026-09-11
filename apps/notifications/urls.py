from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.InboxView.as_view(), name="list"),
    path("mark-read/", views.mark_read_view, name="mark_read"),
    path("announce/", views.AnnouncementView.as_view(), name="announce"),
    path("templates/", views.TemplateListView.as_view(), name="template_list"),
    path("templates/new/", views.TemplateCreateView.as_view(), name="template_create"),
    path("templates/<uuid:pk>/edit/", views.TemplateUpdateView.as_view(), name="template_update"),
]
