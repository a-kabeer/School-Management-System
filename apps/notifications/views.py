from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import FormView, ListView

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.pagination import paginate, querystring_without_page
from apps.core.permissions import PermissionRequiredMixin

from .forms import AnnouncementForm, NotificationTemplateForm
from .models import Channel, NotificationRecipient, NotificationTemplate
from .services import EVENT_ANNOUNCEMENT, guardians_of, mark_read, notify

NOTIFICATIONS = "core.access_notifications"


class InboxView(ActiveBranchMixin, BreadcrumbMixin, ListView):
    """The signed-in user's own notifications - never anybody else's."""

    template_name = "notifications/inbox.html"
    context_object_name = "recipients"
    requires_branch = False
    page_title = _("Notifications")

    def get_queryset(self):
        queryset = NotificationRecipient.objects.filter(
            user=self.request.user, channel=Channel.IN_APP
        ).select_related("notification")
        if self.request.GET.get("unread") == "1":
            queryset = queryset.exclude(status=NotificationRecipient.Status.READ)
        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page, paginator = paginate(self.request, self.get_queryset())
        context.update(
            {
                "page_obj": page,
                "paginator": paginator,
                "recipients": page.object_list,
                "is_paginated": page.has_other_pages(),
                "querystring": querystring_without_page(self.request),
            }
        )
        return context


@require_POST
@login_required
def mark_read_view(request):
    ids = request.POST.getlist("recipient")
    count = mark_read(request.user, ids or None)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        from django.http import JsonResponse

        return JsonResponse({"marked": count})
    messages.success(request, _("%(count)s notifications marked read.") % {"count": count})
    return redirect("notifications:list")


class TemplateListView(TenantListView):
    model = NotificationTemplate
    required_permission = "core.access_settings"
    create_permission = "notifications.add_notificationtemplate"
    requires_branch = False
    across_branches = True
    page_title = _("Notification Templates")
    ordering = ["event", "channel"]
    create_url_name = "notifications:template_create"
    update_url_name = "notifications:template_update"
    filter_spec = FilterSpec(search_fields=("event", "title"))
    table_columns = (
        {"label": _("Event"), "field": "event"},
        {"label": _("Channel"), "field": "channel", "type": "choice"},
        {"label": _("Language"), "field": "language"},
        {"label": _("Title"), "field": "title"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class TemplateCreateView(TenantCreateView):
    model = NotificationTemplate
    form_class = NotificationTemplateForm
    required_permission = "notifications.add_notificationtemplate"
    requires_branch = False
    success_url = reverse_lazy("notifications:template_list")
    page_title = _("New Template")


class TemplateUpdateView(TenantUpdateView):
    model = NotificationTemplate
    form_class = NotificationTemplateForm
    required_permission = "notifications.change_notificationtemplate"
    requires_branch = False
    success_url = reverse_lazy("notifications:template_list")
    page_title = _("Edit Template")


class AnnouncementView(
    PermissionRequiredMixin, ActiveBranchMixin, BreadcrumbMixin, FormView
):
    form_class = AnnouncementForm
    template_name = "components/object_form.html"
    required_permission = "notifications.add_notification"
    page_title = _("Send Announcement")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user, "branch": self.active_branch})
        return kwargs

    def get_audience(self, data):
        from apps.accounts.models import User
        from apps.students.models import Student

        audience = data["audience"]
        branch = self.active_branch

        if audience == "all_staff":
            return User.objects.filter(
                staff_profile__branch=branch, is_active=True
            ).distinct()

        if audience == "all_parents":
            return User.objects.filter(
                guardian_profile__branch=branch,
                guardian_profile__student_links__can_view_portal=True,
                is_active=True,
            ).distinct()

        students = Student.objects.filter(
            branch=branch,
            enrollments__school_class=data["school_class"],
            enrollments__is_current=True,
        )
        return User.objects.filter(
            guardian_profile__student_links__student__in=students,
            guardian_profile__student_links__can_view_portal=True,
            is_active=True,
        ).distinct()

    def form_valid(self, form):
        users = list(self.get_audience(form.cleaned_data))
        if not users:
            messages.warning(self.request, _("Nobody matched that audience."))
            return self.form_invalid(form)

        notify(
            branch=self.active_branch,
            event=EVENT_ANNOUNCEMENT,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            users=users,
            channels=form.cleaned_data["channels"],
            actor=self.request.user,
        )
        messages.success(
            self.request,
            _("Announcement sent to %(count)s people.") % {"count": len(users)},
        )
        return redirect("notifications:list")
