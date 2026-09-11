from django.contrib.auth.models import UserManager as DjangoUserManager


class UserManager(DjangoUserManager):
    def for_organization(self, organization):
        if organization is None:
            return self.none()
        return self.filter(organization=organization)

    def for_user(self, user, branch=None):
        """Users visible to ``user``: their own organization only."""
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_superuser:
            return self.all()
        if user.organization_id is None:
            return self.none()
        queryset = self.filter(organization_id=user.organization_id)
        if branch is not None:
            queryset = queryset.filter(
                branch_accesses__branch=branch, branch_accesses__is_active=True
            ).distinct()
        return queryset
