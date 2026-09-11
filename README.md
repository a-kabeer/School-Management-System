# School Management System

A multi-organization, multi-branch school management system built with Django,
PostgreSQL and Django templates. There is deliberately **no library module**.

---

## What is here

| App | Responsibility |
| --- | --- |
| `core` | Base models, tenancy managers, permissions, generic CRUD views, shared components |
| `tenants` | Organizations, branches, branch switching |
| `accounts` | Custom user, roles, permissions, branch access |
| `academics` | Academic years, terms, classes, sections, subjects, teacher assignments, timetable |
| `students` | Admission, profiles, guardians, documents, enrollment and history |
| `staff` | Teachers and administrative staff, departments, designations, documents |
| `attendance` | Student and staff attendance, marking sessions |
| `hifz` | Quran memorization: Sabaq, Sabqi, Manzil, revisions, assessments |
| `fees` | Fee types, structures, invoices, payments, discounts, waivers, refunds |
| `finance` | Double-entry accounting: accounts, journals, entries, fiscal periods |
| `payroll` | Salary structures, payroll periods, runs, payslips, salary payments |
| `exams` | Exams, papers, schedules, marks, grades, results, report cards |
| `parents` | Parent portal restricted to a guardian's own children |
| `notifications` | Channel-agnostic notifications (in-app, email, SMS, WhatsApp, push) |
| `reports` | Report registry with shared filters and Excel export |
| `subscriptions` | Plans, organization subscriptions, usage against limits |
| `audit` | The single, append-only activity log |

---

## Architecture

### Tenancy

```
Organization
├── Branch (campus)
├── Branch (campus)
└── Branch (central administration)
```

`Organization` is the customer. `Branch` is the operational boundary almost
every business record is filed under. Operational models inherit
`BranchOwnedModel`, which carries `organization`, `branch`, a UUID primary key
and timestamps.

**Isolation is enforced server-side, in the queryset.** Every view obtains its
data through `Model.objects.for_user(request.user, branch)`
(`apps/core/managers.py`), which reads the user's `UserBranchAccess` rows. A
record outside the user's branches is not merely hidden from the template — it
is absent from the queryset, so `get_object()` raises 404. Changing an id in the
URL therefore cannot reach another branch's data.

Forms apply the same rule to their inputs: `TenantModelForm` narrows every
relation field to the caller's branch, so a POST carrying a foreign primary key
fails validation rather than writing.

### RBAC

```
User ──< UserRole >── Role ──< Permission
User ──< UserBranchAccess >── Branch
```

Authorization is expressed only as permission codenames, resolved through roles
by `apps/accounts/rbac.py` and checked by `apps/core/permissions.py`. **No view
asks "is this user a Teacher?"** — adding a role is a database row plus the
permissions attached to it, with no code change and no deployment.

A role assigned without a branch applies everywhere the user can reach; a
branch-scoped role counts only while working in that branch.

Roles seeded for a new organization: Admin, Teacher, Fees Collector, Finance,
Student, Parent (`apps/accounts/role_presets.py` — starting points, editable
afterwards).

Beyond Django's per-model permissions, `apps/core/permissions.py` declares
module and operation permissions: `core.access_fees`, `core.collect_fee_payment`,
`core.refund_fee_payment`, `core.post_journal_entry`, `core.run_payroll`,
`core.publish_exam_result`, `core.export_report`, `core.manage_roles`, and so on.

### Money

Every monetary column is a `DecimalField` (`apps/core/models.py:money_field`).
No float ever touches an amount. `apps/core/utils.py:money()` normalises input to
2dp Decimal, routing floats through `str` so `0.1` does not arrive as
`0.1000000000000000055`.

### Double-entry finance

Fees, payroll and manual entries all post through
`apps/finance/services.py:post_journal_entry`, which refuses an unbalanced
document before any row exists. A `CheckConstraint` on `JournalEntry` backs that
up at the database, and a second constraint on `Transaction` forbids a line that
is both a debit and a credit. A posted entry is never rewritten — correcting it
means posting its mirror image (`reverse_journal_entry`).

### Service layer

Operations that touch several tables live in `services.py`, inside a
transaction, and log to the audit trail themselves:

- `students.services` — `admit_student`, `enroll_student`, `transfer_student`, `change_student_status`
- `fees.services` — `generate_invoice`, `record_payment`, `refund_payment`, `void_payment`, `waive_invoice_amount`
- `finance.services` — `post_journal_entry`, `reverse_journal_entry`, `close_fiscal_period`
- `payroll.services` — `compute_payslip`, `process_payroll`, `approve_payroll_run`, `pay_salary`
- `exams.services` — `save_marks`, `generate_results`, `publish_results`
- `tenants.services` — `switch_branch`

`record_payment` locks the invoice with `select_for_update`, so two cashiers
taking payment for the same student cannot both read a stale balance.

### Audit

`apps/audit` is the only place activity log rows are written; every module calls
`log_activity()`. Rows are append-only — the model raises on `save()` of an
existing row and on `delete()`, the queryset refuses `update()`/`delete()`, and
`default_permissions = ("view",)` means no change permission exists to grant.
Passwords and tokens are redacted from snapshots.

---

## Setup

Requires **PostgreSQL** (SQLite is not used, including for tests) and Python 3.12+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

cp .env.example .env          # then set DB_NAME/DB_USER/DB_PASSWORD

python manage.py setup_database
python manage.py bootstrap_organization \
    --name "Your Academy" \
    --branch "Main Campus" --branch-code MAIN \
    --admin-username admin
python manage.py runserver
```

`setup_database` connects to the server's `postgres` maintenance database,
creates the one named in your `.env` if it is missing, applies all migrations,
and seeds the plans and system settings. It is idempotent — running it again
only applies whatever is outstanding. To get a working installation with demo
data in a single step:

```bash
python manage.py setup_database --demo
```

Django can connect to a database but cannot create one, which is why the
database is created through a separate connection rather than by `migrate`.

`bootstrap_organization` creates the organization, a central-administration
branch, the seeded roles, a chart of accounts, a fiscal period and an admin
user. It writes configuration only — no invented students, staff or invoices.

Then, in the application: add an academic year, classes and sections, fee types
and fee structures, before admitting students.

### Demo accounts

`bootstrap_organization` creates exactly one login — the admin you name. To get
a login per role for evaluation:

```bash
python manage.py seed_demo_users
```

| Username | Role | Can reach |
| --- | --- | --- |
| `admin` | Admin | everything |
| `teacher` | Teacher | students, attendance, hifz, marks |
| `feescollector` | Fees Collector | students, invoices, collect payment |
| `finance` | Finance | fees, ledger, payroll, refunds |
| `student` | Student | own dashboard and notifications |
| `parent` | Parent | the portal, own children only |

All six share the password **`Madrasah#2026`** (override with `--password`).
The command also creates the staff, student and guardian records those logins
need, all named "Demo …".

It refuses to run with `DEBUG=False` unless you pass `--force` — the password
above is published, so these accounts must never exist on an installation
holding real data. Delete them, or change the password, before going live.

### Demo dataset

To fill the system at a realistic size — two campuses, 1,000 students each:

```bash
python manage.py seed_demo_data
```

Roughly 82,000 rows across every table: students, enrollments, guardians,
staff, timetables, attendance registers, Hifz progress, invoices, payments,
waivers, refunds, payroll runs, exams with marks and results, notifications and
subscription history.

High-volume rows are written with `bulk_create`, but money is not: fee
payments, refunds, waivers and payroll all go through the real services, so
both branches end up with a **balanced double-entry ledger** rather than merely
populated tables.

Useful flags: `--students`, `--staff`, `--classes`, `--attendance-days`,
`--pay-ratio`, `--seed` (reproducible), `--flush` (clear business data first).
Like the demo logins, it refuses to run with `DEBUG=False`.

### Environment

All configuration is read through `python-decouple`. See `.env.example`.
`DATABASE_URL` takes precedence over the discrete `DB_*` settings when set.
**Never commit a real `.env`.**

---

## Internationalization

English (LTR), Urdu (RTL) and Arabic (RTL) are supported from the start.
URLs carry the active language (`/en/students/`, `/ur/students/`), and the
`<html>` element's `dir` follows it automatically via
`apps/core/context_processors.py`.

The stylesheet is written with logical properties (`inset-inline-start`,
`padding-inline`, `text-align: start`), so RTL works from the same rules — there
is no mirrored stylesheet to keep in step.

```bash
python manage.py makemessages -l ur -l ar --ignore=.venv
python manage.py compilemessages
```

The shipped catalogues translate the core interface; the remainder falls back to
English and is intended to be filled in by native speakers over time.

---

## Testing

```bash
python manage.py test apps
```

Covered: authentication, RBAC resolution, branch isolation, organization
isolation, student record access, parent portal access, fee payments and
refunds, finance transactions, payroll, exam results, audit logging and
immutability, language switching and RTL.

The security scenario in `apps/students/tests/test_branch_isolation.py`:

```
User from Branch A → requests a Branch B record id → ACCESS DENIED
```

is exercised through detail, edit, POST, delete, status change, the list view,
the JSON search endpoint and the branch switcher.

---

## Deployment

```
Gunicorn + WhiteNoise + PostgreSQL
```

`Procfile`, `render.yaml` and `build.sh` are included for Render and
similar platforms. `/health/` is an unauthenticated liveness probe.

For production set, at minimum:

```
DEBUG=False
SECRET_KEY=<long random value>
ALLOWED_HOSTS=your-domain
CSRF_TRUSTED_ORIGINS=https://your-domain
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Run `python manage.py check --deploy` before going live.

---

## Conventions

- `models` → `managers`/`selectors` → `services` → `forms` → `views` → `templates`
- Business logic lives in services, never in templates and never in large views
- List and form screens inherit the generic views in `apps/core/mixins.py`
- User-facing strings go through `gettext`; none are hard-coded in templates
- JavaScript is vanilla and optional — every page works without it, and nothing
  resets the user's scroll position
