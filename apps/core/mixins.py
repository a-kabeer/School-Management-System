"""Generic tenant-scoped CRUD views.

Every module's list/create/update/delete screens inherit from these, so branch
isolation is enforced in one place rather than re-argued per view.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from .filters import FilterSpec
from .pagination import querystring_without_page
from .permissions import PermissionRequiredMixin, user_has_permission


class ActiveBranchMixin(LoginRequiredMixin):
    """Exposes the branch the request is scoped to."""

    #: Views over organization-wide data set this to False.
    requires_branch = True

    @property
    def active_branch(self):
        return getattr(self.request, "active_branch", None)

    @property
    def organization(self):
        return getattr(self.request.user, "organization", None)

    def dispatch(self, request, *args, **kwargs):
        if (
            self.requires_branch
            and request.user.is_authenticated
            and getattr(request, "active_branch", None) is None
            and not request.user.is_superuser
        ):
            raise PermissionDenied(
                _("Select a branch you have access to before continuing.")
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_branch"] = self.active_branch
        return context


class TenantQuerysetMixin(ActiveBranchMixin):
    """Restricts the view's queryset to rows the user may see.

    Detail/update/delete inherit the same restriction, which is what makes a
    hand-edited id in the URL resolve to nothing.
    """

    #: When True the view shows every branch the user can reach, not just the
    #: active one. Used by organization-level reports.
    across_branches = False

    def get_base_queryset(self):
        return self.model._default_manager.all()

    def get_queryset(self):
        branch = None if self.across_branches else self.active_branch
        queryset = self.get_base_queryset().for_user(self.request.user, branch)
        return self.apply_select_related(queryset)

    def apply_select_related(self, queryset):
        select_related = getattr(self, "select_related", None)
        prefetch_related = getattr(self, "prefetch_related", None)
        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        return queryset

    def get_object(self, queryset=None):
        queryset = queryset or self.get_queryset()
        try:
            return super().get_object(queryset)
        except (Http404, ValueError, TypeError):
            # A row outside the user's branches is indistinguishable from one
            # that does not exist. That is deliberate - it denies access
            # without confirming the record is real.
            raise Http404(_("Record not found."))


class ObjectLevelPermissionMixin:
    """Extra object check for views whose queryset cannot express the rule."""

    def check_object_permission(self, obj):
        return True

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not self.check_object_permission(obj):
            raise PermissionDenied(_("You are not allowed to access this record."))
        return obj


class BreadcrumbMixin:
    breadcrumbs = ()
    page_title = ""

    def get_breadcrumbs(self):
        return list(self.breadcrumbs)

    def get_page_title(self):
        return self.page_title

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumbs"] = self.get_breadcrumbs()
        context["page_title"] = self.get_page_title()
        return context


class TenantListView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, ListView
):
    """List view with shared filtering, pagination and table rendering."""

    template_name = "components/object_list.html"
    context_object_name = "objects"
    filter_spec: FilterSpec | None = None
    #: ``[{"label": _("Name"), "field": "name"}, ...]``
    table_columns = ()
    create_url_name = None
    detail_url_name = None
    update_url_name = None
    delete_url_name = None
    create_permission = None
    empty_message = _("Nothing here yet.")

    def get_paginate_by(self, queryset):
        from django.conf import settings

        return getattr(self, "paginate_by", None) or settings.PAGE_SIZE

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        ordering = getattr(self, "ordering", None)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.filter_spec:
            context.update(self.filter_spec.as_context(self.request))
        context.update(
            {
                "table_columns": self.table_columns,
                "create_url_name": self.create_url_name,
                "detail_url_name": self.detail_url_name,
                "update_url_name": self.update_url_name,
                "delete_url_name": self.delete_url_name,
                "can_create": self.create_permission is None
                or user_has_permission(
                    self.request.user, self.create_permission, self.active_branch
                ),
                "empty_message": self.empty_message,
                "querystring": querystring_without_page(self.request),
            }
        )
        return context


class TenantDetailView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, DetailView
):
    context_object_name = "object"


class AuditedFormMixin:
    """Records a create/update in the central activity log."""

    audit_action_create = "create"
    audit_action_update = "update"

    def form_valid(self, form):
        from apps.audit.services import log_activity, snapshot

        is_create = form.instance.pk is None
        previous = None
        if not is_create:
            previous = snapshot(self.model._default_manager.filter(pk=form.instance.pk).first())

        response = super().form_valid(form)

        log_activity(
            request=self.request,
            action=self.audit_action_create if is_create else self.audit_action_update,
            instance=self.object,
            previous_values=previous,
            new_values=snapshot(self.object),
        )
        messages.success(self.request, self.get_success_message())
        return response

    def get_success_message(self):
        return _("Saved successfully.")


class TenantFormViewMixin(AuditedFormMixin, ActiveBranchMixin, BreadcrumbMixin):
    template_name = "components/object_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            {
                "user": self.request.user,
                "branch": self.active_branch,
                "organization": self.organization,
            }
        )
        return kwargs


class TenantCreateView(
    PermissionRequiredMixin, TenantFormViewMixin, TenantQuerysetMixin, CreateView
):
    def get_success_message(self):
        return _("%(name)s created.") % {"name": self.model._meta.verbose_name.title()}


class TenantUpdateView(
    PermissionRequiredMixin, TenantFormViewMixin, TenantQuerysetMixin, UpdateView
):
    def get_success_message(self):
        return _("%(name)s updated.") % {"name": self.model._meta.verbose_name.title()}


class TenantDeleteView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, DeleteView
):
    template_name = "components/object_confirm_delete.html"

    def form_valid(self, form):
        from apps.audit.services import log_activity, snapshot

        self.object = self.get_object()
        previous = snapshot(self.object)
        response = super().form_valid(form)
        log_activity(
            request=self.request,
            action="delete",
            instance=self.object,
            previous_values=previous,
        )
        messages.success(self.request, _("Deleted successfully."))
        return response


class TenantRestoreView(PermissionRequiredMixin, TenantQuerysetMixin, View):
    """Undo a soft delete. Requires the dedicated restore permission."""

    required_permission = "core.restore_record"
    success_url_name = None

    def get_base_queryset(self):
        return self.model.all_objects.filter(is_deleted=True)

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect, get_object_or_404

        from apps.audit.services import log_activity, snapshot

        obj = get_object_or_404(self.get_queryset(), pk=kwargs["pk"])
        obj.restore()
        log_activity(
            request=request, action="restore", instance=obj, new_values=snapshot(obj)
        )
        messages.success(request, _("Record restored."))
        return redirect(self.success_url_name)
