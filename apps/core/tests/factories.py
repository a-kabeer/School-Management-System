"""Test fixtures shared by every app's tests.

:func:`build_branch` produces a fully usable branch — roles, chart of
accounts, fiscal period, academic year, a class — so a test can get to the
behaviour it cares about in two or three lines.
"""

import datetime as dt
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.utils.text import slugify

from apps.academics.models import AcademicYear, ClassSubject, SchoolClass, Section, Subject
from apps.accounts.models import Role, User, UserBranchAccess, UserRole
from apps.accounts.services import seed_roles
from apps.fees.models import FeeStructure, FeeType
from apps.finance.seeds import seed_chart_of_accounts, seed_fiscal_period
from apps.staff.models import Staff
from apps.students.models import Guardian, Student, StudentGuardian
from apps.students.services import admit_student
from apps.tenants.models import Branch, Organization

TODAY = dt.date(2026, 6, 1)
YEAR_START = dt.date(2026, 1, 1)
YEAR_END = dt.date(2026, 12, 31)


class TenantFixture:
    """A ready-to-use organization/branch with the objects most tests need."""

    def __init__(self, organization, branch, academic_year, school_class, section):
        self.organization = organization
        self.branch = branch
        self.academic_year = academic_year
        self.school_class = school_class
        self.section = section


def build_organization(name="Test Academy"):
    """Create an organization, keeping the slug unique.

    Slugs are globally unique, so a test that builds two fixtures with the
    default name would otherwise collide on the second one.
    """
    base = slugify(name)
    slug = base
    suffix = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return Organization.objects.create(
        name=name if slug == base else f"{name} {suffix - 1}",
        slug=slug,
        status=Organization.Status.ACTIVE,
    )


def build_branch(organization=None, name="Main Campus", code="MAIN"):
    organization = organization or build_organization()
    branch = Branch.objects.create(
        organization=organization, name=name, code=code, is_central_administration=True
    )
    seed_chart_of_accounts(branch)
    seed_fiscal_period(branch, YEAR_START, YEAR_END, name=f"FY2026-{code}")

    academic_year = AcademicYear.objects.create(
        branch=branch,
        organization=organization,
        name=f"2026 {code}",
        start_date=YEAR_START,
        end_date=YEAR_END,
        is_current=True,
    )
    school_class = SchoolClass.objects.create(
        branch=branch, organization=organization, name=f"Grade 1 {code}", code=f"G1-{code}", level=1
    )
    section = Section.objects.create(
        branch=branch, organization=organization, school_class=school_class, name="A"
    )
    return TenantFixture(organization, branch, academic_year, school_class, section)


def build_user(
    branch,
    username="user",
    password="Str0ngPassphrase!42",
    permissions=(),
    role_name="Tester",
    is_superuser=False,
):
    """A user with branch access and a role carrying ``permissions``."""
    user = User.objects.create_user(
        username=username,
        password=password,
        organization=branch.organization,
        is_superuser=is_superuser,
    )
    UserBranchAccess.objects.create(
        user=user, branch=branch, is_active=True, is_default=True
    )

    if permissions:
        role, _created = Role.objects.get_or_create(
            organization=branch.organization, name=role_name
        )
        for dotted in permissions:
            app_label, codename = dotted.split(".", 1)
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is not None:
                role.permissions.add(permission)
        UserRole.objects.create(user=user, role=role, is_active=True)
    return user


def build_admin(branch, username="admin"):
    """A user holding the seeded Admin role for the organization."""
    seed_roles(branch.organization)
    user = User.objects.create_user(
        username=username,
        password="Str0ngPassphrase!42",
        organization=branch.organization,
    )
    UserBranchAccess.objects.create(
        user=user, branch=branch, is_active=True, is_default=True
    )
    role = Role.objects.get(organization=branch.organization, name="Admin")
    UserRole.objects.create(user=user, role=role, is_active=True)
    return user


def build_student(fixture, name="Ayesha Khan", admission_no=None):
    student, _enrollment = admit_student(
        branch=fixture.branch,
        academic_year=fixture.academic_year,
        school_class=fixture.school_class,
        section=fixture.section,
        full_name=name,
        admission_no=admission_no,
        admission_date=YEAR_START,
        status=Student.Status.ACTIVE,
    )
    return student


def build_guardian_with_portal(fixture, student, username="parent"):
    """A guardian linked to ``student`` and to a portal login."""
    user = User.objects.create_user(
        username=username,
        password="Str0ngPassphrase!42",
        organization=fixture.organization,
    )
    guardian = Guardian.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        user=user,
        full_name=f"{student.full_name} Parent",
        phone="+923001234567",
    )
    StudentGuardian.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        student=student,
        guardian=guardian,
        is_primary=True,
        can_view_portal=True,
    )
    return user, guardian


def build_staff(fixture, name="Yusuf Ali", employee_no="EMP-001", salary=Decimal("50000.00")):
    return Staff.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        employee_no=employee_no,
        full_name=name,
        staff_type=Staff.StaffType.TEACHER,
        joining_date=YEAR_START,
        basic_salary=salary,
        status=Staff.Status.ACTIVE,
    )


def build_fee_type(fixture, name="Tuition", amount=Decimal("5000.00")):
    fee_type = FeeType.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        name=name,
        frequency=FeeType.Frequency.MONTHLY,
    )
    FeeStructure.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        academic_year=fixture.academic_year,
        school_class=fixture.school_class,
        fee_type=fee_type,
        amount=amount,
    )
    return fee_type


def build_subject(fixture, name="Mathematics"):
    subject = Subject.objects.create(
        branch=fixture.branch, organization=fixture.organization, name=name
    )
    return ClassSubject.objects.create(
        branch=fixture.branch,
        organization=fixture.organization,
        academic_year=fixture.academic_year,
        school_class=fixture.school_class,
        subject=subject,
        weekly_periods=5,
    )


def two_branches():
    """Branch A and Branch B in the *same* organization.

    This is the shape most isolation tests need: same tenant, different
    operational boundary.
    """
    organization = build_organization("Two Branch Academy")
    a = build_branch(organization, name="Branch A", code="BRA")
    b = build_branch(organization, name="Branch B", code="BRB")
    return a, b


def two_organizations():
    a = build_branch(build_organization("Org One"), name="One Main", code="ONE")
    b = build_branch(build_organization("Org Two"), name="Two Main", code="TWO")
    return a, b
