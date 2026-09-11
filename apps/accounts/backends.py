"""Authentication backend that resolves permissions through roles."""

from django.contrib.auth.backends import ModelBackend

from .rbac import permissions_for_user


class RoleAwareModelBackend(ModelBackend):
    """Standard password authentication; permissions come from roles.

    ``has_perm`` is wired to the same resolver the views use, so Django's own
    helpers (``PermissionRequiredMixin``, admin, template ``perms``) agree with
    :mod:`apps.core.permissions`.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None and user.organization_id is not None:
            if not user.organization.is_operational:
                # A suspended tenant cannot sign in, however valid the password.
                return None
        return user

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        from apps.tenants.middleware import get_current_branch

        return permissions_for_user(user_obj, get_current_branch())

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active:
            return False
        if user_obj.is_superuser:
            return True
        return perm in self.get_all_permissions(user_obj, obj)

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_active:
            return False
        if user_obj.is_superuser:
            return True
        return any(
            perm.startswith(f"{app_label}.")
            for perm in self.get_all_permissions(user_obj)
        )
