from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView, LogoutView
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, UpdateView

from apps.core.filters import FilterSpec
from apps.core.mixins import (
    ActiveBranchMixin,
    BreadcrumbMixin,
    TenantCreateView,
    TenantListView,
    TenantUpdateView,
)
from apps.core.permissions import PermissionRequiredMixin

from .forms import ChangePasswordForm, LoginForm, ProfileForm, RoleForm, UserForm
from .models import Role, User


class SmsLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        from apps.audit.services import log_activity

        user = form.get_user()
        user.last_login_ip = getattr(self.request, "audit_ip", None)
        user.save(update_fields=["last_login_ip"])
        log_activity(request=self.request, action="login", user=user)
        return response

    def form_invalid(self, form):
        from apps.audit.services import log_activity

        log_activity(
            request=self.request,
            action="login_failed",
            metadata={"username": form.data.get("username", "")[:150]},
        )
        return super().form_invalid(form)


class SmsLogoutView(LogoutView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            from apps.audit.services import log_activity

            log_activity(request=request, action="logout", user=request.user)
        return super().dispatch(request, *args, **kwargs)


class UserListView(TenantListView):
    model = User
    required_permission = "core.manage_roles"
    create_permission = "core.manage_roles"
    requires_branch = False
    across_branches = True
    page_title = _("Users")
    ordering = ["username"]
    create_url_name = "accounts:user_create"
    update_url_name = "accounts:user_update"
    filter_spec = FilterSpec(
        search_fields=("username", "first_name", "last_name", "email")
    )
    table_columns = (
        {"label": _("Username"), "field": "username"},
        {"label": _("Name"), "field": "display_name"},
        {"label": _("Email"), "field": "email"},
        {"label": _("Roles"), "field": "role_names", "type": "list"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )

    def get_base_queryset(self):
        return User.objects.all()

    def get_queryset(self):
        queryset = User.objects.for_user(self.request.user)
        if self.filter_spec:
            queryset = self.filter_spec.apply(queryset, self.request)
        return queryset.prefetch_related("role_assignments__role").order_by("username")


class UserCreateView(TenantCreateView):
    model = User
    form_class = UserForm
    required_permission = "core.manage_roles"
    requires_branch = False
    success_url = reverse_lazy("accounts:user_list")
    page_title = _("New User")

    def get_queryset(self):
        return User.objects.for_user(self.request.user)


class UserUpdateView(TenantUpdateView):
    model = User
    form_class = UserForm
    required_permission = "core.manage_roles"
    requires_branch = False
    success_url = reverse_lazy("accounts:user_list")
    page_title = _("Edit User")

    def get_queryset(self):
        return User.objects.for_user(self.request.user)


class RoleListView(TenantListView):
    model = Role
    required_permission = "core.manage_roles"
    create_permission = "core.manage_roles"
    requires_branch = False
    across_branches = True
    page_title = _("Roles")
    ordering = ["name"]
    create_url_name = "accounts:role_create"
    update_url_name = "accounts:role_update"
    filter_spec = FilterSpec(search_fields=("name", "description"))
    table_columns = (
        {"label": _("Role"), "field": "name"},
        {"label": _("Description"), "field": "description"},
        {"label": _("System"), "field": "is_system", "type": "bool"},
        {"label": _("Active"), "field": "is_active", "type": "bool"},
    )


class RoleCreateView(TenantCreateView):
    model = Role
    form_class = RoleForm
    required_permission = "core.manage_roles"
    requires_branch = False
    success_url = reverse_lazy("accounts:role_list")
    page_title = _("New Role")


class RoleUpdateView(TenantUpdateView):
    model = Role
    form_class = RoleForm
    required_permission = "core.manage_roles"
    requires_branch = False
    success_url = reverse_lazy("accounts:role_list")
    page_title = _("Edit Role")


class ProfileView(ActiveBranchMixin, BreadcrumbMixin, UpdateView):
    form_class = ProfileForm
    template_name = "components/object_form.html"
    success_url = reverse_lazy("accounts:profile")
    requires_branch = False
    page_title = _("My Profile")

    def get_object(self, queryset=None):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Profile updated."))
        return response


class ChangePasswordView(ActiveBranchMixin, BreadcrumbMixin, FormView):
    form_class = ChangePasswordForm
    template_name = "components/object_form.html"
    success_url = reverse_lazy("core:dashboard")
    requires_branch = False
    page_title = _("Change Password")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        from apps.audit.services import log_activity

        form.save()
        self.request.user.must_change_password = False
        self.request.user.save(update_fields=["must_change_password"])
        update_session_auth_hash(self.request, form.user)
        log_activity(request=self.request, action="settings_change",
                     instance=self.request.user, metadata={"event": "password_change"})
        messages.success(self.request, _("Password changed."))
        return super().form_valid(form)
