"""Queryset-level tenancy: the foundation every other guarantee rests on."""

from django.test import TestCase

from apps.core.tests.factories import (
    build_student,
    build_user,
    two_branches,
    two_organizations,
)
from apps.students.models import Student


class BranchIsolationQuerysetTests(TestCase):
    def setUp(self):
        self.branch_a, self.branch_b = two_branches()
        self.student_a = build_student(self.branch_a, "Student A", "A-001")
        self.student_b = build_student(self.branch_b, "Student B", "B-001")
        self.user_a = build_user(self.branch_a.branch, username="user_a")
        self.user_b = build_user(self.branch_b.branch, username="user_b")

    def test_user_sees_only_their_branch(self):
        visible = Student.objects.for_user(self.user_a, self.branch_a.branch)
        self.assertIn(self.student_a, visible)
        self.assertNotIn(self.student_b, visible)

    def test_asking_for_another_branch_returns_nothing(self):
        # Even naming Branch B explicitly, a Branch A user gets an empty set.
        visible = Student.objects.for_user(self.user_a, self.branch_b.branch)
        self.assertEqual(visible.count(), 0)

    def test_without_a_branch_user_sees_every_branch_they_can_enter(self):
        visible = Student.objects.for_user(self.user_a, None)
        self.assertIn(self.student_a, visible)
        self.assertNotIn(self.student_b, visible)

    def test_user_with_access_to_both_branches_sees_both(self):
        from apps.accounts.rbac import grant_branch_access

        grant_branch_access(self.user_a, self.branch_b.branch)
        self.user_a._accessible_branch_ids = None
        visible = Student.objects.for_user(self.user_a, None)
        self.assertIn(self.student_a, visible)
        self.assertIn(self.student_b, visible)

    def test_anonymous_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(Student.objects.for_user(AnonymousUser()).count(), 0)

    def test_superuser_sees_everything(self):
        superuser = build_user(
            self.branch_a.branch, username="root", is_superuser=True
        )
        visible = Student.objects.for_user(superuser, None)
        self.assertIn(self.student_a, visible)
        self.assertIn(self.student_b, visible)


class OrganizationIsolationTests(TestCase):
    def setUp(self):
        self.org_one, self.org_two = two_organizations()
        self.student_one = build_student(self.org_one, "One Student", "O-001")
        self.student_two = build_student(self.org_two, "Two Student", "T-001")

    def test_a_user_never_sees_another_organization(self):
        user = build_user(self.org_one.branch, username="org_one_user")
        visible = Student.objects.for_user(user, None)
        self.assertIn(self.student_one, visible)
        self.assertNotIn(self.student_two, visible)

    def test_branch_access_row_cannot_cross_organizations(self):
        from apps.accounts.rbac import user_can_access_branch

        user = build_user(self.org_one.branch, username="crosser")
        # Even with a row granting access, the organization check refuses.
        from apps.accounts.models import UserBranchAccess

        UserBranchAccess.objects.create(
            user=user, branch=self.org_two.branch, is_active=True
        )
        user._accessible_branch_ids = None
        self.assertFalse(user_can_access_branch(user, self.org_two.branch))


class BranchOwnedModelTests(TestCase):
    def test_organization_is_derived_from_the_branch(self):
        fixture = two_branches()[0]
        student = Student(
            branch=fixture.branch, admission_no="X-1", full_name="Derived Org"
        )
        student.save()
        self.assertEqual(student.organization_id, fixture.branch.organization_id)

    def test_mismatched_branch_and_organization_fails_validation(self):
        from django.core.exceptions import ValidationError

        a, b = two_branches()
        student = Student(
            branch=a.branch,
            organization=b.organization if b.organization != a.organization else None,
            admission_no="X-2",
            full_name="Mismatch",
        )
        # Same organization in this fixture, so build a genuine mismatch.
        other_org = two_organizations()[0].organization
        student.organization = other_org
        with self.assertRaises(ValidationError):
            student.clean()
