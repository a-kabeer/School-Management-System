"""Tenant-aware querysets and managers.

Every scoping decision goes through ``for_user``. Views never filter tenancy by
hand, so there is one place to audit when asking "can this user see this row?".
"""

from django.db import models


class TenantQuerySet(models.QuerySet):
    """Queryset for models carrying ``organization`` (and usually ``branch``)."""

    def for_organization(self, organization):
        if organization is None:
            return self.none()
        return self.filter(organization=organization)

    def for_branch(self, branch):
        if branch is None:
            return self.none()
        return self.filter(branch=branch)

    def for_branches(self, branches):
        branch_ids = [getattr(b, "pk", b) for b in branches]
        if not branch_ids:
            return self.none()
        return self.filter(branch_id__in=branch_ids)

    def for_user(self, user, branch=None):
        """Restrict to rows the user is allowed to see.

        ``branch`` narrows further to the branch the user is currently working
        in. Without it the user sees every branch they have access to, which is
        what organization-wide reports need.
        """
        from apps.accounts.rbac import accessible_branch_ids

        if user is None or not getattr(user, "is_authenticated", False):
            return self.none()

        branch_field = next(
            (f for f in self.model._meta.fields if f.name == "branch"), None
        )

        if user.is_superuser:
            qs = self
            if branch is not None and branch_field is not None:
                qs = qs.filter(branch=branch)
            return qs

        if user.organization_id is None:
            return self.none()

        qs = self.filter(organization_id=user.organization_id)
        if branch_field is None:
            return qs

        if branch is not None:
            # Asking for one branch still has to prove the user may enter it.
            if branch.pk in accessible_branch_ids(user):
                clause = models.Q(branch=branch)
            elif not branch_field.null:
                return self.none()
            else:
                clause = models.Q(pk__isnull=True)  # matches nothing
        else:
            clause = models.Q(branch_id__in=accessible_branch_ids(user))

        # A nullable branch means "belongs to the whole organization" - a
        # shared report definition, say - so those rows stay visible either way.
        if branch_field.null:
            clause |= models.Q(branch__isnull=True)
        return qs.filter(clause)

    def active(self):
        if any(f.name == "is_active" for f in self.model._meta.fields):
            return self.filter(is_active=True)
        return self

    def alive(self):
        if any(f.name == "is_deleted" for f in self.model._meta.fields):
            return self.filter(is_deleted=False)
        return self


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Default manager for tenant-owned models."""

    use_in_migrations = False


class SoftDeleteQuerySet(TenantQuerySet):
    def delete(self):
        """Soft-delete in bulk so nothing silently disappears from audit."""
        from django.utils import timezone

        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Hides soft-deleted rows by default; ``all_with_deleted`` sees them."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted(self):
        return self.all_with_deleted().filter(is_deleted=True)
