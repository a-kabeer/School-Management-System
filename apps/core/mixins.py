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

from . import tables
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
    """List view with shared filtering, sorting, pagination and rendering.

    Subclasses needing a different starting queryset override
    :meth:`get_list_queryset`, not ``get_queryset``: ordering is applied after
    it, so a subclass that ordered its own rows would otherwise quietly
    override the column the reader clicked.
    """

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
    #: Template rendered in each row's action cell, for a verb only this
    #: module has. It is given the row as ``object``.
    row_actions_template = None
    #: Extra bulk actions beyond the ones derived from the user's permissions.
    bulk_actions = ()
    #: Offer the filtered rows as a spreadsheet.
    exportable = False
    #: A wide table gets a column chooser; a narrow one does not need one.
    column_toggle_from = 6
    #: Rows an export may write, so one click cannot stream a whole database.
    export_limit = 10000

    # ------------------------------------------------------------------ data
    def get_paginate_by(self, queryset):
        from django.conf import settings

        default = getattr(self, "paginate_by", None) or settings.PAGE_SIZE
        return tables.page_size(self.request, default)

    def get_list_queryset(self):
        """The rows this view is about: filtered, but not yet ordered."""
        queryset = super().get_queryset()
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        return queryset

    def get_sort(self):
        if not hasattr(self, "_sort_state"):
            self._sort_state = tables.sort_state(
                self.request,
                self.model,
                self.table_columns,
                getattr(self, "ordering", None) or (),
            )
        return self._sort_state

    def get_queryset(self):
        return self.get_list_queryset().order_by(*self.get_sort()["ordering"])

    def paginate_queryset(self, queryset, page_size):
        """Clamp a bad page number rather than raising 404.

        Growing the page size while deep in a list, or a hand-edited ``?page``,
        would otherwise land the reader on an error page instead of on their
        data. A number past the end means the last page; anything that is not
        a page number at all means the first.
        """
        try:
            return super().paginate_queryset(queryset, page_size)
        except Http404:
            paginator = self.get_paginator(
                queryset,
                page_size,
                orphans=self.get_paginate_orphans(),
                allow_empty_first_page=self.get_allow_empty(),
            )
            requested = self.kwargs.get(self.page_kwarg) or self.request.GET.get(
                self.page_kwarg
            )
            try:
                number = int(requested)
            except (TypeError, ValueError):
                number = 1
            page = paginator.page(min(max(number, 1), paginator.num_pages))
            return paginator, page, page.object_list, page.has_other_pages()

    # --------------------------------------------------------------- actions
    def get_bulk_actions(self):
        """Bulk actions this user may run on this list.

        Deleting several rows is the same authority as deleting one, so the
        action appears exactly when the row menu's Delete does.
        """
        actions = []
        if self.delete_url_name and user_has_permission(
            self.request.user,
            f"{self.model._meta.app_label}.delete_{self.model._meta.model_name}",
            self.active_branch,
        ):
            actions.append(
                {
                    "key": "delete",
                    "label": _("Delete selected"),
                    "icon": "bi-trash",
                    "variant": "outline-danger",
                    # Some models retire a row and some erase it. The wording
                    # has to say which, because only one of them is undoable.
                    "confirm": _(
                        "Delete the selected records? An administrator can restore them."
                    )
                    if hasattr(self.model, "restore")
                    else _("Delete the selected records permanently?"),
                }
            )
        return actions + list(self.bulk_actions)

    def post(self, request, *args, **kwargs):
        """Run a bulk action over the rows the reader ticked."""
        from django.shortcuts import redirect

        action = request.POST.get("action", "")
        if action not in {entry["key"] for entry in self.get_bulk_actions()}:
            raise PermissionDenied(_("That action is not available here."))

        # The selection is re-read through this view own queryset, so an id
        # posted from outside the user branches simply is not in it.
        selected = self.get_list_queryset().filter(
            pk__in=request.POST.getlist("selected")
        )
        self.handle_bulk_action(action, selected)
        return redirect(request.get_full_path())

    def handle_bulk_action(self, action, queryset):
        from apps.audit.services import log_activity, snapshot

        if action != "delete":
            return

        from django.db.models import ProtectedError, RestrictedError

        count = 0
        blocked = 0
        for obj in queryset:
            previous = snapshot(obj)
            try:
                obj.delete()
            except (ProtectedError, RestrictedError):
                # A row other records depend on stays; deleting the rest of
                # the selection is still the right outcome.
                blocked += 1
                continue
            log_activity(
                request=self.request,
                action="delete",
                instance=obj,
                previous_values=previous,
                metadata={"event": "bulk_delete"},
            )
            count += 1

        if count:
            messages.success(
                self.request, _("%(count)s records deleted.") % {"count": count}
            )
        elif not blocked:
            messages.info(self.request, _("Nothing was selected."))

        if blocked:
            messages.warning(
                self.request,
                _("%(count)s records are still in use and were kept.")
                % {"count": blocked},
            )

    def export_response(self, queryset):
        """The current search, filters and sort, as a spreadsheet."""
        from apps.audit.services import log_activity
        from apps.core.templatetags.core_extras import attr, display
        from apps.core.utils import export_to_excel

        columns = list(self.table_columns)
        rows = [
            [
                display(obj, column["field"])
                if column.get("type") == "choice"
                else attr(obj, column["field"])
                for column in columns
            ]
            for obj in queryset[: self.export_limit]
        ]

        title = str(self.get_page_title() or self.model._meta.verbose_name_plural)
        log_activity(
            action="export",
            request=self.request,
            metadata={
                "table": self.model._meta.label,
                "rows": len(rows),
                "filters": self.request.GET.dict(),
            },
        )
        return export_to_excel(
            title, [str(column["label"]) for column in columns], rows, sheet_title=title
        )

    def get(self, request, *args, **kwargs):
        if self.exportable and request.GET.get("export") == "xlsx":
            if not user_has_permission(
                request.user, "core.export_report", self.active_branch
            ):
                raise PermissionDenied(_("You are not allowed to export."))
            return self.export_response(self.get_queryset())
        return super().get(request, *args, **kwargs)

    # --------------------------------------------------------------- context
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.filter_spec:
            context.update(self.filter_spec.as_context(self.request))

        sort = self.get_sort()
        bulk_actions = self.get_bulk_actions()
        context.update(
            {
                "table_columns": tables.column_headers(
                    self.model, self.table_columns, sort
                ),
                "table_sort": sort["active"],
                "table_dir": sort["direction"],
                # Identifies this table saved column choices in the browser.
                "table_key": getattr(self.request.resolver_match, "view_name", ""),
                "page_sizes": tables.PAGE_SIZES,
                "per_page": self.get_paginate_by(None),
                "show_column_toggle": len(self.table_columns) >= self.column_toggle_from,
                "bulk_actions": bulk_actions,
                "selectable": bool(bulk_actions),
                "exportable": self.exportable
                and user_has_permission(
                    self.request.user, "core.export_report", self.active_branch
                ),
                "row_actions_template": self.row_actions_template,
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
