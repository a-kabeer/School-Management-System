"""The central activity log.

One table records what happened across every module. Rows are append-only: the
model refuses updates and deletes, so the trail cannot be quietly edited by
ordinary application code.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ActivityLogQuerySet(models.QuerySet):
    def for_user(self, user, branch=None):
        """Restrict the log to what this user is allowed to review."""
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            queryset = self
            return queryset.filter(branch=branch) if branch else queryset
        if user.organization_id is None:
            return self.none()

        from apps.accounts.rbac import accessible_branch_ids

        queryset = self.filter(organization_id=user.organization_id)
        if branch is not None:
            return queryset.filter(branch=branch)
        return queryset.filter(
            models.Q(branch_id__in=accessible_branch_ids(user))
            | models.Q(branch__isnull=True)
        )

    def delete(self):
        raise NotImplementedError(
            "Activity logs are append-only and cannot be deleted."
        )

    def update(self, **kwargs):
        raise NotImplementedError(
            "Activity logs are append-only and cannot be modified."
        )


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        LOGIN_FAILED = "login_failed", _("Failed Login")
        CREATE = "create", _("Create")
        UPDATE = "update", _("Update")
        DELETE = "delete", _("Delete")
        RESTORE = "restore", _("Restore")
        EXPORT = "export", _("Export")
        IMPORT = "import", _("Import")
        PERMISSION_CHANGE = "permission_change", _("Permission Change")
        ROLE_CHANGE = "role_change", _("Role Change")
        BRANCH_CHANGE = "branch_change", _("Branch Change")
        SETTINGS_CHANGE = "settings_change", _("Settings Change")
        PAYMENT = "payment", _("Payment")
        REFUND = "refund", _("Refund")
        PAYROLL = "payroll", _("Payroll")
        PUBLISH = "publish", _("Publish")
        ACCESS_DENIED = "access_denied", _("Access Denied")
        OTHER = "other", _("Other")

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(_("timestamp"), auto_now_add=True, db_index=True)

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name=_("user"),
    )
    username = models.CharField(
        _("username"),
        max_length=150,
        blank=True,
        help_text=_("Kept verbatim so the trail survives a deleted account."),
    )
    role_name = models.CharField(_("role"), max_length=150, blank=True)
    organization = models.ForeignKey(
        "tenants.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name=_("organization"),
    )
    branch = models.ForeignKey(
        "tenants.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        verbose_name=_("branch"),
    )

    action = models.CharField(_("action"), max_length=40, choices=Action.choices)
    app_label = models.CharField(_("module"), max_length=100, blank=True)
    model_name = models.CharField(_("resource"), max_length=100, blank=True)
    object_id = models.CharField(_("object id"), max_length=100, blank=True)
    object_repr = models.CharField(_("object"), max_length=500, blank=True)

    previous_values = models.JSONField(_("previous values"), null=True, blank=True)
    new_values = models.JSONField(_("new values"), null=True, blank=True)

    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)
    request_path = models.CharField(_("path"), max_length=500, blank=True)
    request_method = models.CharField(_("method"), max_length=10, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    objects = ActivityLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("activity log")
        verbose_name_plural = _("activity log")
        ordering = ["-created_at"]
        # No add/change/delete permissions: the log is written by services and
        # read by administrators, never edited through a screen.
        default_permissions = ("view",)
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["branch", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["app_label", "model_name"]),
            models.Index(fields=["object_id"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.object_repr or self.app_label}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Activity logs are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Activity logs are append-only and cannot be deleted.")
