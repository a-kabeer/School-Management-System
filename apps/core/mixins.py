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
from .modals import ModalFormMixin
from .pagination import querystring_without_page
from .permissions import PermissionRequiredMixin, user_has_permission


class ActiveBranchMixin(LoginRequiredMixin):
    """Exposes the branch the request is scoped to."""

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
    """List view with shared filtering, sorting, pagination and rendering."""

    template_name = "components/object_list.html"
    context_object_name = "objects"
    filter_spec: FilterSpec | None = None
    table_columns = ()
    create_url_name = None
    detail_url_name = None
    update_url_name = None
    delete_url_name = None
    create_permission = None
    empty_message = _("Nothing here yet.")
    row_actions_template = None
    bulk_actions = ()
    exportable = False
    column_toggle_from = 6
    export_limit = 10000

    def get_paginate_by(self, queryset):
        from django.conf import settings

        default = getattr(self, "paginate_by", None) or settings.PAGE_SIZE
        return tables.page_size(self.request, default)

    def get_list_queryset(self):
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
    def _academics_bulk_safety_action(self):
        """Return the safe bulk action for Academics, if the model supports it.

        Academics records are historical/relational data. Their per-record
        delete workflow already prefers deactivation/closing, so the shared
        table must not provide a bulk-delete escape hatch for those same rows.
        Models without a safe archive field (for example Terms and Timetable
        slots) get no bulk destructive action at all.
        """
        if self.model._meta.app_label != "academics":
            return None

        field = None
        action_key = None
        label = None
        explanation = None
        if hasattr(self.model, "is_closed"):
            field = "is_closed"
            action_key = "close"
            label = _("Close / archive selected")
            explanation = _(
                "Close the selected Academic Years? Their history and related records will be preserved."
            )
        elif hasattr(self.model, "is_active"):
            field = "is_active"
            action_key = "deactivate"
            label = _("Deactivate selected")
            explanation = _(
                "Deactivate the selected records? Their history and relationships will be preserved, and they will no longer be used in new workflows."
            )

        if not field or not action_key:
            return None

        permission = f"{self.model._meta.app_label}.change_{self.model._meta.model_name}"
        if not user_has_permission(self.request.user, permission, self.active_branch):
            return None

        return {
            "key": action_key,
            "label": label,
            "icon": "bi-archive" if action_key == "close" else "bi-pause-circle",
            "variant": "outline-warning",
            "confirm": explanation,
        }

    def get_bulk_actions(self):
        """Bulk actions with Academics-safe destructive behavior."""
        actions = []
        academics_action = self._academics_bulk_safety_action()
        if self.model._meta.app_label == "academics":
            # Academics deliberately has no bulk Delete. Records with
            # historical value must use the same deactivate/close workflow as
            # their individual destructive action; records without a safe
            # archive state are not bulk-selectable.
            if academics_action:
                actions.append(academics_action)
            return actions + list(self.bulk_actions)

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
                    "confirm": _(
                        "Delete the selected records? An administrator can restore them."
                    )
                    if hasattr(self.model, "restore")
                    else _("Delete the selected records permanently?"),
                }
            )
        return actions + list(self.bulk_actions)

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect

        action = request.POST.get("action", "")
        if action not in {entry["key"] for entry in self.get_bulk_actions()}:
            raise PermissionDenied(_("That action is not available here."))

        selected = self.get_list_queryset().filter(
            pk__in=request.POST.getlist("selected")
        )
        self.handle_bulk_action(action, selected)
        return redirect(request.get_full_path())

    def handle_bulk_action(self, action, queryset):
        from apps.audit.services import log_activity, snapshot

        if action == "delete":
            from django.db.models import ProtectedError, RestrictedError

            count = 0
            blocked = 0
            for obj in queryset:
                previous = snapshot(obj)
                try:
                    obj.delete()
                except (ProtectedError, RestrictedError):
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
            return

        if action in {"deactivate", "close"} and self.model._meta.app_label == "academics":
            field = "is_closed" if action == "close" else "is_active"
            if not hasattr(self.model, field):
                raise PermissionDenied(_("That action is not available here."))

            changed = 0
            already = 0
            for obj in queryset:
                previous = snapshot(obj)
                if getattr(obj, field):
                    setattr(obj, field, False if field == "is_active" else True)
                    obj.save(update_fields=[field])
                    log_activity(
                        request=self.request,
                        action="update",
                        instance=obj,
                        previous_values=previous,
                        metadata={"event": f"bulk_{action}", "field": field},
                    )
                    changed += 1
                else:
                    already += 1

            if changed:
                messages.success(
                    self.request,
                    _("%(count)s records were updated safely; history was preserved.")
                    % {"count": changed},
                )
            if already:
                messages.info(
                    self.request,
                    _("%(count)s selected records were already in the requested state.")
                    % {"count": already},
                )
            if not changed and not already:
                messages.info(self.request, _("Nothing was selected."))
            return

        if action != "delete":
            return

    def export_response(self, queryset):
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
            }
        )
        return context


class TenantCreateView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, ModalFormMixin, CreateView
):
    template_name = "components/object_form.html"
    form_class = None
    required_permission = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["branch"] = self.active_branch
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return self.success_url


class TenantUpdateView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, ModalFormMixin, UpdateView
):
    template_name = "components/object_form.html"
    form_class = None
    required_permission = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["branch"] = self.active_branch
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return self.success_url


class TenantDeleteView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, DeleteView
):
    template_name = "components/object_confirm_delete.html"
    dependants = ()

    def get_dependants(self):
        found = []
        for name, label in self.dependants:
            manager = getattr(self.object, name, None)
            if manager is None or not hasattr(manager, "count"):
                continue
            count = manager.count()
            if count:
                found.append({"label": label, "count": count})
        return found

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dependants"] = self.get_dependants()
        return context

    def form_valid(self, form):
        from apps.audit.services import log_activity, snapshot

        previous = snapshot(self.object)
        response = super().form_valid(form)
        log_activity(
            request=self.request,
            action="delete",
            instance=self.object,
            previous_values=previous,
        )
        return response


class TenantRestoreView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, View
):
    """Restore a soft-deleted tenant record without weakening branch isolation."""

    required_permission = "core.restore_record"
    success_url_name = None

    def get_base_queryset(self):
        manager = getattr(self.model, "all_objects", None)
        if manager is None:
            raise Http404(_("This record type cannot be restored."))
        return manager.all()

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=True)
        return self.apply_select_related(queryset)

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect

        obj = self.get_object()
        previous = None
        try:
            from apps.audit.services import snapshot

            previous = snapshot(obj)
        except Exception:
            previous = None

        obj.restore()

        try:
            from apps.audit.services import log_activity

            log_activity(
                request=request,
                action="restore",
                instance=obj,
                previous_values=previous,
                metadata={"event": "restore"},
            )
        except Exception:
            # Audit logging must never make a successful restore look like a
            # failed data operation.
            pass

        messages.success(
            request,
            _("%(name)s was restored.") % {"name": str(obj)},
        )
        if self.success_url_name:
            return redirect(self.success_url_name)
        return redirect("/")


class TenantDetailView(
    PermissionRequiredMixin, TenantQuerysetMixin, BreadcrumbMixin, DetailView
):
    template_name = "components/object_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_update"] = user_has_permission(
            self.request.user,
            f"{self.model._meta.app_label}.change_{self.model._meta.model_name}",
            self.active_branch,
        )
        return context
