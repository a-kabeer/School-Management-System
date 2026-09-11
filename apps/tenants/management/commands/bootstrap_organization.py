"""Create a new tenant: organization, head-office branch, roles and an admin.

Everything this writes is configuration — roles, permissions, a chart of
accounts, a fiscal period. No students, staff or invoices are invented.
"""

import datetime as dt
import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import Role, User
from apps.accounts.services import create_user, seed_roles
from apps.core.constants import ROLE_ADMIN
from apps.finance.seeds import seed_chart_of_accounts, seed_fiscal_period
from apps.subscriptions.models import Plan, Subscription
from apps.tenants.models import Branch, Organization


class Command(BaseCommand):
    help = "Create an organization with a head-office branch, roles and an admin user."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Organization name")
        parser.add_argument("--branch", default="Main Campus", help="First branch name")
        parser.add_argument("--branch-code", default="MAIN", help="First branch code")
        parser.add_argument("--admin-username", required=True)
        parser.add_argument("--admin-email", default="")
        parser.add_argument(
            "--admin-password",
            default="",
            help="Omit to be prompted (the password is never echoed).",
        )
        parser.add_argument("--plan", default="starter", help="Subscription plan code")
        parser.add_argument(
            "--fiscal-start",
            default="",
            help="Fiscal year start, YYYY-MM-DD. Defaults to 1 January this year.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["name"].strip()
        slug = slugify(name)

        if Organization.objects.filter(slug=slug).exists():
            raise CommandError(f"An organization named “{name}” already exists.")
        if User.objects.filter(username=options["admin_username"]).exists():
            raise CommandError("That admin username is already taken.")

        password = options["admin_password"] or getpass.getpass("Admin password: ")
        if not password:
            raise CommandError("A password is required.")

        organization = Organization.objects.create(
            name=name, slug=slug, status=Organization.Status.TRIAL
        )
        branch = Branch.objects.create(
            organization=organization,
            name=options["branch"],
            code=options["branch_code"].upper(),
            is_central_administration=True,
        )

        seed_roles(organization)
        admin_role = Role.objects.get(organization=organization, name=ROLE_ADMIN)

        admin = create_user(
            organization=organization,
            username=options["admin_username"],
            password=password,
            email=options["admin_email"],
            is_staff=True,
            roles=[admin_role],
            branches=[branch],
            default_branch=branch,
        )

        seed_chart_of_accounts(branch)

        if options["fiscal_start"]:
            start = dt.date.fromisoformat(options["fiscal_start"])
        else:
            start = dt.date(dt.date.today().year, 1, 1)
        seed_fiscal_period(branch, start, start.replace(year=start.year + 1) - dt.timedelta(days=1))

        plan = Plan.objects.filter(code=options["plan"]).first()
        if plan is not None:
            today = dt.date.today()
            Subscription.objects.create(
                organization=organization,
                plan=plan,
                start_date=today,
                end_date=today + dt.timedelta(days=30),
                trial_ends_on=today + dt.timedelta(days=30),
                status=Subscription.Status.TRIAL,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created “{organization.name}” with branch “{branch.name}” "
                f"and admin “{admin.username}”."
            )
        )
        self.stdout.write(
            "Next: add an academic year, classes and fee types before admitting students."
        )
