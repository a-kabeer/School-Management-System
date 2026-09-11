"""Create the PostgreSQL database, build its tables, and seed configuration.

Django can connect to a database but cannot create one, so this connects to
the server's ``postgres`` maintenance database first, creates the target if it
is missing, and then runs the normal migrate/seed path. Everything it does is
idempotent: running it against an existing installation only applies whatever
migrations are outstanding.
"""

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Create the project database if missing, then migrate and seed it."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Entry in settings.DATABASES to set up (default: default).",
        )
        parser.add_argument(
            "--no-seed",
            action="store_true",
            help="Create and migrate, but do not seed plans and settings.",
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Also create a demo organization and a login per role.",
        )

    def handle(self, *args, **options):
        alias = options["database"]
        try:
            config = settings.DATABASES[alias]
        except KeyError:
            raise CommandError(f"No database named “{alias}” in settings.DATABASES.")

        if "postgresql" not in config["ENGINE"]:
            raise CommandError(
                f"This project requires PostgreSQL; settings say {config['ENGINE']}."
            )

        name = config["NAME"]
        self.stdout.write(
            f"Target: {config['USER']}@{config['HOST']}:{config['PORT']}/{name}"
        )

        self._create_database(config, name)

        self.stdout.write("Applying migrations…")
        call_command("migrate", database=alias, verbosity=1)

        if not options["no_seed"]:
            self.stdout.write("Seeding plans and system settings…")
            call_command("seed_system", verbosity=0)
            self.stdout.write(self.style.SUCCESS("  seeded"))

        if options["demo"]:
            self._seed_demo()

        self._report(alias, seeded_demo=options["demo"])

    # ------------------------------------------------------------------
    def _create_database(self, config, name):
        """Create the database, connecting to ``postgres`` to do it."""
        try:
            with psycopg.connect(
                host=config["HOST"],
                port=config["PORT"],
                user=config["USER"],
                password=config["PASSWORD"],
                dbname="postgres",
                autocommit=True,
                connect_timeout=10,
            ) as admin:
                exists = admin.execute(
                    "select 1 from pg_database where datname = %s", (name,)
                ).fetchone()
                if exists:
                    self.stdout.write(f"Database “{name}” already exists.")
                    return
                # The name comes from settings, not from user input, but it is
                # still an identifier rather than a value - so quote it.
                admin.execute(f'CREATE DATABASE "{name}"')
                self.stdout.write(self.style.SUCCESS(f"Created database “{name}”."))
        except psycopg.OperationalError as error:
            raise CommandError(
                "Could not reach the PostgreSQL server.\n"
                f"  {error}\n"
                "Check that PostgreSQL is running and that DB_HOST, DB_PORT, "
                "DB_USER and DB_PASSWORD in your .env are correct."
            )

    def _seed_demo(self):
        from apps.tenants.models import Organization

        if not Organization.objects.exists():
            self.stdout.write("Creating a demo organization…")
            call_command(
                "bootstrap_organization",
                name="Demo Academy",
                branch="Main Campus",
                branch_code="MAIN",
                admin_username="admin",
                admin_password="Madrasah#2026",
                verbosity=0,
            )
        self.stdout.write("Creating demo logins…")
        call_command("seed_demo_users", reset_passwords=True)

    def _report(self, alias, *, seeded_demo=False):
        connection = connections[alias]
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from information_schema.tables "
                "where table_schema = 'public'"
            )
            tables = cursor.fetchone()[0]

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Database ready: {tables} tables in "
                f"{connection.settings_dict['NAME']}."
            )
        )
        if seeded_demo:
            self.stdout.write("Next: python manage.py runserver, then sign in.")
        else:
            self.stdout.write(
                'Next: python manage.py bootstrap_organization '
                '--name "Your Academy" --admin-username admin'
            )
