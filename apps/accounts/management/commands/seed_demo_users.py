"""Create one demo login per role, for development and evaluation.

This is the only command in the project that invents business data, and it
says so: every record it creates is named "Demo …" so it is obvious in a
listing. It refuses to run against a non-DEBUG installation unless forced,
because the passwords it sets are published in the README.
"""

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.accounts.models import Role, User
from apps.accounts.rbac import assign_role, grant_branch_access
from apps.accounts.services import seed_roles
from apps.core.constants import (
    ROLE_ADMIN,
    ROLE_FEES_COLLECTOR,
    ROLE_FINANCE,
    ROLE_PARENT,
    ROLE_STUDENT,
    ROLE_TEACHER,
)
from apps.staff.models import Staff
from apps.students.models import Guardian, Student, StudentGuardian
from apps.students.services import admit_student
from apps.tenants.models import Branch, Organization

DEFAULT_PASSWORD = "Madrasah#2026"

#: username → (role name, first name, last name)
DEMO_USERS = [
    ("admin", ROLE_ADMIN, "Demo", "Administrator"),
    ("teacher", ROLE_TEACHER, "Demo", "Teacher"),
    ("feescollector", ROLE_FEES_COLLECTOR, "Demo", "Fees Collector"),
    ("finance", ROLE_FINANCE, "Demo", "Finance Officer"),
    ("student", ROLE_STUDENT, "Demo", "Student"),
    ("parent", ROLE_PARENT, "Demo", "Parent"),
]


class Command(BaseCommand):
    help = "Create a demo login for each role (development use only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization",
            default="",
            help="Organization name or slug. Defaults to the only one present.",
        )
        parser.add_argument(
            "--branch", default="", help="Branch name. Defaults to the first branch."
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for every demo account (default: {DEFAULT_PASSWORD}).",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset the password on accounts that already exist.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow this to run with DEBUG=False. Never do this in production.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to create demo accounts with DEBUG=False. "
                "These passwords are published; pass --force only if you are "
                "certain this is not a production installation."
            )

        organization = self._get_organization(options["organization"])
        branch = self._get_branch(organization, options["branch"])
        password = options["password"]

        seed_roles(organization)
        roles = {r.name: r for r in Role.objects.filter(organization=organization)}

        academic_year, school_class, section = self._ensure_academics(branch)

        created, existing = [], []
        users = {}
        for username, role_name, first_name, last_name in DEMO_USERS:
            user = User.objects.filter(
                organization=organization, username=username
            ).first()
            if user is None:
                user = User(
                    organization=organization,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{username}@demo.invalid",
                    is_staff=(role_name == ROLE_ADMIN),
                )
                user.set_password(password)
                user.save()
                created.append(username)
            else:
                if options["reset_passwords"]:
                    user.set_password(password)
                    user.save(update_fields=["password"])
                existing.append(username)

            grant_branch_access(user, branch, is_default=True)
            assign_role(user, roles[role_name])
            users[username] = user

        self._attach_teacher(branch, users["teacher"])
        demo_student = self._attach_student(
            branch, users["student"], academic_year, school_class, section
        )
        self._attach_parent(branch, users["parent"], demo_student)

        self.stdout.write(self.style.SUCCESS("Demo accounts ready."))
        self.stdout.write(f"  Organization: {organization.name}")
        self.stdout.write(f"  Branch:       {branch.name}")
        self.stdout.write(f"  Password:     {password}   (same for every account)")
        self.stdout.write("")
        self.stdout.write("  Username        Role")
        self.stdout.write("  --------------  ----------------")
        for username, role_name, *_ in DEMO_USERS:
            self.stdout.write(f"  {username:<15} {role_name}")
        if created:
            self.stdout.write("")
            self.stdout.write(f"  Created: {', '.join(created)}")
        if existing:
            note = "password reset" if options["reset_passwords"] else "left as-is"
            self.stdout.write(f"  Already existed ({note}): {', '.join(existing)}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "These are demo credentials. Delete or change them before the "
                "system holds real data."
            )
        )

    # ------------------------------------------------------------------
    def _get_organization(self, name):
        queryset = Organization.objects.all()
        if name:
            organization = queryset.filter(name=name).first() or queryset.filter(
                slug=name
            ).first()
            if organization is None:
                raise CommandError(f"No organization named “{name}”.")
            return organization

        if queryset.count() == 0:
            raise CommandError(
                "No organization exists. Run bootstrap_organization first."
            )
        if queryset.count() > 1:
            raise CommandError(
                "Several organizations exist; name one with --organization."
            )
        return queryset.first()

    def _get_branch(self, organization, name):
        queryset = Branch.objects.filter(organization=organization)
        if name:
            branch = queryset.filter(name=name).first()
            if branch is None:
                raise CommandError(f"No branch named “{name}”.")
            return branch
        branch = queryset.order_by("-is_central_administration", "name").first()
        if branch is None:
            raise CommandError("That organization has no branches.")
        return branch

    def _ensure_academics(self, branch):
        """A demo login is useless without a year and a class to sit in."""
        today = dt.date.today()
        academic_year = AcademicYear.objects.filter(
            branch=branch, is_current=True
        ).first()
        if academic_year is None:
            academic_year = AcademicYear.objects.create(
                branch=branch,
                organization=branch.organization,
                name=f"Demo {today.year}",
                start_date=dt.date(today.year, 1, 1),
                end_date=dt.date(today.year, 12, 31),
                is_current=True,
            )

        school_class = SchoolClass.objects.filter(branch=branch).order_by("level").first()
        if school_class is None:
            school_class = SchoolClass.objects.create(
                branch=branch,
                organization=branch.organization,
                name="Demo Class 1",
                code="DEMO-1",
                level=1,
            )

        section = Section.objects.filter(school_class=school_class).first()
        if section is None:
            section = Section.objects.create(
                branch=branch,
                organization=branch.organization,
                school_class=school_class,
                name="A",
            )
        return academic_year, school_class, section

    def _attach_teacher(self, branch, user):
        staff = Staff.all_objects.filter(user=user).first()
        if staff is not None:
            return staff
        return Staff.objects.create(
            branch=branch,
            organization=branch.organization,
            user=user,
            employee_no="DEMO-EMP-001",
            full_name="Demo Teacher",
            staff_type=Staff.StaffType.TEACHER,
            joining_date=dt.date.today(),
            basic_salary=Decimal("50000.00"),
            status=Staff.Status.ACTIVE,
        )

    def _attach_student(self, branch, user, academic_year, school_class, section):
        student = Student.all_objects.filter(user=user).first()
        if student is not None:
            return student
        student, _enrollment = admit_student(
            branch=branch,
            academic_year=academic_year,
            school_class=school_class,
            section=section,
            user=user,
            admission_no="DEMO-STU-001",
            full_name="Demo Student",
            father_name="Demo Parent",
            admission_date=dt.date.today(),
            status=Student.Status.ACTIVE,
        )
        return student

    def _attach_parent(self, branch, user, student):
        guardian = Guardian.objects.filter(user=user).first()
        if guardian is None:
            guardian = Guardian.objects.create(
                branch=branch,
                organization=branch.organization,
                user=user,
                full_name="Demo Parent",
                relation=Guardian.Relation.FATHER,
                phone="+920000000000",
            )
        StudentGuardian.objects.get_or_create(
            student=student,
            guardian=guardian,
            defaults={
                "branch": branch,
                "organization": branch.organization,
                "is_primary": True,
                "can_view_portal": True,
            },
        )
        return guardian
