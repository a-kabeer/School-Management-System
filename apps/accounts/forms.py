from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.rbac import accessible_branches
from apps.tenants.models import Branch

from .models import Role, User


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autofocus": True, "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "current-password"}
        )


class UserForm(forms.ModelForm):
    """Create/edit a user together with their roles and branch access."""

    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.none(),
        required=False,
        label=_("Roles"),
        widget=forms.CheckboxSelectMultiple,
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        label=_("Branch access"),
        widget=forms.CheckboxSelectMultiple,
    )
    default_branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(), required=False, label=_("Default branch")
    )
    password = forms.CharField(
        label=_("Password"),
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("Leave blank to keep the current password."),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "preferred_language",
            "is_active",
        ]

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = user
        self.organization = organization or getattr(user, "organization", None)

        branch_queryset = accessible_branches(user) if user else Branch.objects.none()
        self.fields["branches"].queryset = branch_queryset
        self.fields["default_branch"].queryset = branch_queryset
        self.fields["roles"].queryset = Role.objects.filter(
            organization=self.organization, is_active=True
        )

        for name, field in self.fields.items():
            if name in {"roles", "branches"}:
                continue
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            widget.attrs.setdefault(
                "class", "form-select" if isinstance(widget, forms.Select) else "form-control"
            )

        if self.instance.pk:
            self.fields["roles"].initial = Role.objects.filter(
                assignments__user=self.instance, assignments__branch__isnull=True
            ).distinct()
            self.fields["branches"].initial = branch_queryset.filter(
                user_accesses__user=self.instance, user_accesses__is_active=True
            )
            default_access = self.instance.branch_accesses.filter(
                is_default=True
            ).first()
            if default_access:
                self.fields["default_branch"].initial = default_access.branch_id
        else:
            self.fields["password"].required = True

    def clean(self):
        cleaned = super().clean()
        branches = cleaned.get("branches")
        default_branch = cleaned.get("default_branch")
        if default_branch and branches and default_branch not in branches:
            self.add_error(
                "default_branch", _("The default branch must be one of the selected branches.")
            )
        return cleaned

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        from .services import set_branch_access, set_user_roles

        user = super().save(commit=False)
        user.organization = self.organization
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            set_branch_access(
                user,
                list(self.cleaned_data.get("branches") or []),
                actor=self.actor,
                default_branch=self.cleaned_data.get("default_branch"),
            )
            set_user_roles(
                user, list(self.cleaned_data.get("roles") or []), actor=self.actor
            )
        return user


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "description", "permissions", "is_active"]
        widgets = {"permissions": forms.SelectMultiple(attrs={"size": 18})}

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = user
        self.organization = organization or getattr(user, "organization", None)

        from django.contrib.auth.models import Permission

        self.fields["permissions"].queryset = (
            Permission.objects.filter(
                content_type__app_label__in=[
                    "core", "tenants", "accounts", "academics", "students", "staff",
                    "attendance", "hifz", "fees", "finance", "payroll", "exams",
                    "parents", "notifications", "reports", "subscriptions", "audit",
                ]
            )
            .select_related("content_type")
            .order_by("content_type__app_label", "codename")
        )
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            widget.attrs.setdefault(
                "class", "form-select" if isinstance(widget, forms.Select) else "form-control"
            )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.instance.pk and self.instance.is_system and name != self.instance.name:
            raise forms.ValidationError(_("System roles cannot be renamed."))
        return name

    def save(self, commit=True):
        role = super().save(commit=False)
        role.organization = self.organization
        if commit:
            role.save()
            from .services import set_role_permissions

            set_role_permissions(
                role, list(self.cleaned_data.get("permissions") or []), actor=self.actor
            )
        return role


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "preferred_language", "avatar"]

    def __init__(self, *args, user=None, branch=None, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            widget.attrs.setdefault(
                "class", "form-select" if isinstance(widget, forms.Select) else "form-control"
            )

    def clean_avatar(self):
        from apps.core.validators import validate_upload

        return validate_upload(self.cleaned_data.get("avatar"))


class ChangePasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
