"""Django admin, kept deliberately narrow.

The admin does not apply branch isolation, so only the tenancy and account
models a superuser needs for recovery are registered here. All day-to-day work
happens in the application, where the queryset scoping lives.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Role, User, UserBranchAccess, UserRole
from apps.audit.models import ActivityLog
from apps.core.models import SystemSetting
from apps.subscriptions.models import Plan, Subscription
from apps.tenants.models import Branch, Organization

admin.site.site_header = _("School Management System")
admin.site.site_title = _("School Management System")
admin.site.index_title = _("Platform administration")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "city", "created_at")
    list_filter = ("status", "country")
    search_fields = ("name", "slug", "email")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_active", "is_central_administration")
    list_filter = ("organization", "is_active", "is_central_administration")
    search_fields = ("name", "code")
    autocomplete_fields = ("organization",)


class UserBranchAccessInline(admin.TabularInline):
    model = UserBranchAccess
    extra = 0
    autocomplete_fields = ("branch",)


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 0
    autocomplete_fields = ("role", "branch")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "display_name", "organization", "is_active", "is_superuser")
    list_filter = ("organization", "is_active", "is_superuser", "preferred_language")
    search_fields = ("username", "first_name", "last_name", "email")
    inlines = (UserBranchAccessInline, UserRoleInline)
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            _("School Management System"),
            {
                "fields": (
                    "organization",
                    "phone",
                    "preferred_language",
                    "avatar",
                    "must_change_password",
                )
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_system", "is_active")
    list_filter = ("organization", "is_system", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("permissions",)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "organization", "description", "is_editable")
    list_filter = ("organization",)
    search_fields = ("key", "description")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "monthly_price", "max_branches", "max_students", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "start_date", "end_date")
    list_filter = ("status", "plan")
    autocomplete_fields = ("organization",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Read-only: the trail is append-only everywhere, including here."""

    list_display = ("created_at", "username", "action", "app_label", "model_name", "branch")
    list_filter = ("action", "app_label", "organization")
    search_fields = ("username", "object_repr", "request_path")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
