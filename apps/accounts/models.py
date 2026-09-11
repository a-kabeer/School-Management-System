"""Users, roles and branch access.

Roles are data. A new role is a row plus the permissions attached to it - no
code change, no deployment, and nothing in the views needs to learn its name.
"""

from django.contrib.auth.models import AbstractUser, Permission
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.managers import TenantManager
from apps.core.models import BaseModel, TimeStampedModel
from apps.core.validators import validate_phone
from apps.tenants.models import Branch, Organization

from .managers import UserManager


class User(AbstractUser):
    """Custom user, attached to exactly one organization.

    The organization on the user is the outer tenancy boundary; branch access
    is granted separately through :class:`UserBranchAccess`.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("organization"),
    )
    phone = models.CharField(
        _("phone"), max_length=40, blank=True, validators=[validate_phone]
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=5,
        choices=[("en", _("English")), ("ur", _("Urdu")), ("ar", _("Arabic"))],
        default="en",
    )
    avatar = models.ImageField(
        _("avatar"), upload_to="users/avatars/", blank=True, null=True
    )
    must_change_password = models.BooleanField(
        _("must change password"), default=False
    )
    last_login_ip = models.GenericIPAddressField(
        _("last login IP"), null=True, blank=True
    )

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]
        indexes = [
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def role_names(self):
        return list(
            self.role_assignments.filter(is_active=True)
            .values_list("role__name", flat=True)
            .distinct()
        )

    @property
    def is_parent_account(self):
        """Parent accounts are routed to the portal instead of the back office."""
        return hasattr(self, "guardian_profile")


class Role(BaseModel):
    """A named bundle of permissions, scoped to one organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="roles",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("name"), max_length=100)
    description = models.CharField(_("description"), max_length=255, blank=True)
    permissions = models.ManyToManyField(
        Permission, blank=True, related_name="sms_roles", verbose_name=_("permissions")
    )
    is_system = models.BooleanField(_("system role"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    # Role carries an organization but not a branch, so the tenant manager
    # scopes it by organization alone - which is what the roles screen needs.
    objects = TenantManager()

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_role_name"
            )
        ]
        indexes = [models.Index(fields=["organization", "is_active"])]

    def __str__(self):
        return self.name


class UserRole(TimeStampedModel):
    """Grants a role to a user, globally or within one branch."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="role_assignments",
        verbose_name=_("user"),
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("role"),
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name=_("branch"),
        help_text=_("Leave empty to grant the role in every accessible branch."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("user role")
        verbose_name_plural = _("user roles")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "branch"],
                name="uq_user_role_branch",
            ),
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=models.Q(branch__isnull=True),
                name="uq_user_role_global",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["branch", "is_active"]),
        ]

    def __str__(self):
        scope = self.branch.name if self.branch_id else _("all branches")
        return f"{self.user} — {self.role} ({scope})"


class UserBranchAccess(TimeStampedModel):
    """The list of branches a user may enter.

    This is the single source of truth for branch isolation; querysets and the
    branch switcher both read it.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="branch_accesses",
        verbose_name=_("user"),
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name="user_accesses",
        verbose_name=_("branch"),
    )
    is_active = models.BooleanField(_("active"), default=True)
    is_default = models.BooleanField(_("default branch"), default=False)

    class Meta:
        verbose_name = _("branch access")
        verbose_name_plural = _("branch access")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "branch"], name="uq_user_branch_access"
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="uq_user_single_default_branch",
            ),
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def __str__(self):
        return f"{self.user} → {self.branch}"

    def save(self, *args, **kwargs):
        if self.is_default:
            UserBranchAccess.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)
