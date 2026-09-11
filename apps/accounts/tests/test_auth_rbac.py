"""Authentication and role-based access control."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, UserRole
from apps.accounts.rbac import permissions_for_user, user_has_role
from apps.core.permissions import user_has_permission
from apps.core.tests.factories import build_admin, build_branch, build_user, two_branches

PASSWORD = "Str0ngPassphrase!42"


class AuthenticationTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.user = build_admin(self.fixture.branch, username="office")

    def test_login_succeeds_with_correct_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "office", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_fails_with_a_wrong_password(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "office", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_suspended_organization_cannot_sign_in(self):
        from apps.tenants.models import Organization

        self.fixture.organization.status = Organization.Status.SUSPENDED
        self.fixture.organization.save(update_fields=["status"])

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "office", "password": PASSWORD},
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_passwords_are_hashed(self):
        self.assertNotEqual(self.user.password, PASSWORD)
        self.assertTrue(self.user.check_password(PASSWORD))


class PermissionResolutionTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()

    def test_a_user_without_a_role_holds_no_permissions(self):
        user = build_user(self.fixture.branch, username="nobody")
        self.assertEqual(permissions_for_user(user, self.fixture.branch), set())
        self.assertFalse(
            user_has_permission(user, "core.access_students", self.fixture.branch)
        )

    def test_role_permissions_reach_the_user(self):
        user = build_user(
            self.fixture.branch,
            username="teacher",
            permissions=["core.access_students", "students.view_student"],
        )
        self.assertTrue(
            user_has_permission(user, "core.access_students", self.fixture.branch)
        )
        self.assertFalse(
            user_has_permission(user, "core.access_finance", self.fixture.branch)
        )

    def test_branch_scoped_role_does_not_apply_in_another_branch(self):
        branch_a, branch_b = two_branches()
        user = build_user(branch_a.branch, username="scoped")
        from apps.accounts.rbac import grant_branch_access

        grant_branch_access(user, branch_b.branch)

        role = Role.objects.create(
            organization=branch_a.organization, name="Branch A Only"
        )
        from django.contrib.auth.models import Permission

        role.permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="access_fees"
            )
        )
        UserRole.objects.create(user=user, role=role, branch=branch_a.branch)

        user._permission_cache = None
        self.assertTrue(user_has_permission(user, "core.access_fees", branch_a.branch))
        self.assertFalse(user_has_permission(user, "core.access_fees", branch_b.branch))

    def test_adding_a_role_needs_no_code_change(self):
        from django.contrib.auth.models import Permission

        user = build_user(self.fixture.branch, username="newrole")
        role = Role.objects.create(
            organization=self.fixture.organization, name="Librarian Emeritus"
        )
        role.permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="access_reports"
            )
        )
        UserRole.objects.create(user=user, role=role)
        user._permission_cache = None

        self.assertTrue(
            user_has_permission(user, "core.access_reports", self.fixture.branch)
        )
        self.assertTrue(user_has_role(user, "Librarian Emeritus"))

    def test_seeded_admin_role_grants_module_access(self):
        admin = build_admin(self.fixture.branch, username="boss")
        for permission in (
            "core.access_students",
            "core.access_fees",
            "core.access_finance",
            "core.manage_roles",
        ):
            self.assertTrue(
                user_has_permission(admin, permission, self.fixture.branch),
                msg=f"Admin should hold {permission}",
            )


class ModuleAccessViewTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()

    def test_a_user_without_module_permission_is_refused(self):
        build_user(self.fixture.branch, username="limited")
        self.client.login(username="limited", password=PASSWORD)
        response = self.client.get(reverse("students:student_list"))
        self.assertEqual(response.status_code, 403)

    def test_a_user_with_module_permission_is_allowed(self):
        build_user(
            self.fixture.branch,
            username="allowed",
            permissions=["core.access_students", "students.view_student"],
        )
        self.client.login(username="allowed", password=PASSWORD)
        response = self.client.get(reverse("students:student_list"))
        self.assertEqual(response.status_code, 200)

    def test_financial_operations_need_their_own_permission(self):
        user = build_user(
            self.fixture.branch,
            username="viewer",
            permissions=["core.access_fees", "fees.view_feepayment"],
        )
        self.client.login(username="viewer", password=PASSWORD)
        self.assertFalse(
            user_has_permission(user, "core.collect_fee_payment", self.fixture.branch)
        )
        response = self.client.get(reverse("fees:payment_create"))
        self.assertEqual(response.status_code, 403)
