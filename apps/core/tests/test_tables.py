"""The shared table: sorting, paging, selection and export.

These tests treat the query string as hostile — it is the one part of a list
view a reader can hand-edit — and they hold the whole application's list views
to the same rules rather than checking one screen.
"""

from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver, reverse
from django.utils import translation

from apps.core import tables
from apps.core.mixins import TenantListView
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_student,
    build_user,
)
from apps.students.models import Student

PASSWORD = "Str0ngPassphrase!42"


def list_views():
    """Every list view the application routes to, found through the URLconf."""
    found = {}

    def walk(patterns, namespace=""):
        for entry in patterns:
            nested = getattr(entry, "url_patterns", None)
            if nested is not None:
                walk(nested, entry.namespace or namespace)
                continue
            view_class = getattr(entry.callback, "view_class", None)
            if view_class and issubclass(view_class, TenantListView):
                name = f"{view_class.__module__}.{view_class.__name__}"
                route = f"{namespace}:{entry.name}" if namespace else entry.name
                found[name] = (
                    view_class,
                    route if entry.pattern.regex.groups == 0 else None,
                )

    walk(get_resolver().url_patterns)
    return found


class EnglishLabelMixin:
    """Pin the language for assertions on translated text."""

    def setUp(self):
        super().setUp()
        translation.activate("en")
        self.addCleanup(translation.activate, settings.LANGUAGE_CODE)


class ColumnSortingTests(TestCase):
    def test_a_stored_field_sorts_and_a_computed_one_does_not(self):
        self.assertEqual(
            tables.database_lookup(Student, "full_name"), "full_name"
        )
        # A property has nothing in the database to order by.
        self.assertIsNone(tables.database_lookup(Student, "current_class_display"))

    def test_a_relation_path_becomes_a_join(self):
        from apps.attendance.models import StudentAttendance

        self.assertEqual(
            tables.database_lookup(StudentAttendance, "session.school_class.name"),
            "session__school_class__name",
        )

    def test_a_to_many_relation_is_refused(self):
        # Ordering across a to-many join multiplies rows, which corrupts both
        # the page and the count.
        self.assertIsNone(tables.database_lookup(Student, "enrollments.school_class"))

    def test_a_column_can_name_its_own_lookup_or_opt_out(self):
        self.assertEqual(
            tables.column_lookup(Student, {"field": "x", "sort": "full_name"}),
            "full_name",
        )
        self.assertIsNone(
            tables.column_lookup(Student, {"field": "full_name", "sort": False})
        )


class SortStateTests(TestCase):
    def _state(self, query, columns=None, default=("full_name",)):
        from django.test import RequestFactory

        columns = columns or [
            {"label": "Name", "field": "full_name"},
            {"label": "Class", "field": "current_class_display"},
        ]
        request = RequestFactory().get("/", query)
        return tables.sort_state(request, Student, columns, default)

    def test_a_declared_column_sorts_both_ways(self):
        self.assertEqual(self._state({"sort": "full_name"})["ordering"][0], "full_name")
        self.assertEqual(
            self._state({"sort": "full_name", "dir": "desc"})["ordering"][0],
            "-full_name",
        )

    def test_a_hand_edited_sort_falls_back_to_the_views_own_ordering(self):
        # Never trust the query string: an unknown or non-database column is
        # ignored rather than reaching the ORM.
        for value in ("password", "current_class_display", "full_name; drop"):
            with self.subTest(sort=value):
                state = self._state({"sort": value})
                self.assertEqual(state["active"], "")
                self.assertEqual(state["ordering"][0], "full_name")

    def test_every_sort_ends_with_a_stable_tiebreaker(self):
        # Without it, rows that tie can swap between pages and a reader sees
        # the same record twice.
        self.assertEqual(self._state({"sort": "full_name"})["ordering"][-1], "pk")


class PageSizeTests(TestCase):
    def _size(self, query):
        from django.test import RequestFactory

        return tables.page_size(RequestFactory().get("/", query), 25)

    def test_the_offered_sizes_are_accepted(self):
        for size in tables.PAGE_SIZES:
            with self.subTest(size=size):
                self.assertEqual(self._size({"per_page": str(size)}), size)

    def test_anything_else_falls_back(self):
        for value in ("7", "100000", "", "abc", "-50"):
            with self.subTest(value=value):
                self.assertEqual(self._size({"per_page": value}), 25)


class ListPageTests(EnglishLabelMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="table_admin")
        for index in range(30):
            build_student(cls.fixture, f"Student {index:02d}", f"T-{index:03d}")

    def setUp(self):
        super().setUp()
        self.client.login(username="table_admin", password=PASSWORD)

    def _names(self, response):
        return [obj.full_name for obj in response.context["objects"]]

    def test_the_default_page_shows_the_first_rows_in_order(self):
        response = self.client.get(reverse("students:student_list"))
        self.assertEqual(self._names(response)[0], "Student 00")
        self.assertContains(response, "Showing 1–25 of 30")

    def test_sorting_descending_reverses_the_page(self):
        response = self.client.get(
            reverse("students:student_list"), {"sort": "full_name", "dir": "desc"}
        )
        self.assertEqual(self._names(response)[0], "Student 29")
        self.assertContains(response, 'aria-sort="descending"')

    def test_the_page_size_changes_how_many_rows_come_back(self):
        response = self.client.get(reverse("students:student_list"), {"per_page": "50"})
        self.assertEqual(len(self._names(response)), 30)
        self.assertContains(response, "Showing 1–30 of 30")

    def test_a_page_beyond_the_end_lands_on_the_last_page(self):
        # Growing the page size while deep in a list must not 404.
        response = self.client.get(reverse("students:student_list"), {"page": "99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_a_page_number_that_is_not_a_number_lands_on_the_first_page(self):
        for value in ("abc", "0", "-3", ""):
            with self.subTest(page=value):
                response = self.client.get(
                    reverse("students:student_list"), {"page": value}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_obj"].number, 1)

    def test_search_sort_and_page_size_survive_each_other(self):
        response = self.client.get(
            reverse("students:student_list"),
            {"q": "Student 1", "sort": "admission_no", "dir": "desc", "per_page": "50"},
        )
        names = self._names(response)
        self.assertEqual(len(names), 10)
        self.assertEqual(names[0], "Student 19")
        # The filter bar carries the sort forward, so filtering again keeps it.
        self.assertContains(response, 'name="sort" value="admission_no"')
        self.assertContains(response, 'name="per_page" value="50"')

    def test_a_search_that_matches_nothing_offers_a_way_out(self):
        response = self.client.get(
            reverse("students:student_list"), {"q": "nobody-by-that-name"}
        )
        self.assertContains(response, "No matching records")
        self.assertContains(response, "Reset filters")

    def test_an_empty_list_invites_the_first_record(self):
        from apps.core.tests.factories import build_branch as new_branch

        empty = new_branch(self.fixture.organization, name="Empty", code="EMP")
        user = build_admin(empty.branch, username="empty_admin")
        self.client.force_login(user)
        response = self.client.get(reverse("academics:subject_list"))
        # The view's own wording, and the action that fills the gap.
        self.assertContains(response, "No subjects yet")
        self.assertContains(response, "Add the first one")

    def test_sorting_is_done_by_the_database(self):
        # The ordering has to reach SQL; sorting a page in the browser would
        # only ever sort the twenty-five rows it can see.
        response = self.client.get(
            reverse("students:student_list"), {"sort": "admission_no", "dir": "desc"}
        )
        query = str(response.context["objects"].query)
        self.assertIn("ORDER BY", query)
        self.assertIn("DESC", query)


class BulkActionTests(EnglishLabelMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="bulk_admin")

    def setUp(self):
        super().setUp()
        self.client.login(username="bulk_admin", password=PASSWORD)
        from apps.academics.models import Subject

        self.subjects = [
            Subject.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                name=f"Subject {index}",
            )
            for index in range(3)
        ]

    def test_deleting_a_selection_retires_those_rows_and_audits_it(self):
        from apps.academics.models import Subject
        from apps.audit.models import ActivityLog

        response = self.client.post(
            reverse("academics:subject_list"),
            {"action": "delete", "selected": [str(s.pk) for s in self.subjects[:2]]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(
            ActivityLog.objects.filter(metadata__event="bulk_delete").count(), 2
        )

    def test_an_unknown_action_is_refused(self):
        response = self.client.post(
            reverse("academics:subject_list"),
            {"action": "shred", "selected": [str(self.subjects[0].pk)]},
        )
        self.assertEqual(response.status_code, 403)

    def test_a_row_from_another_branch_cannot_be_deleted(self):
        from apps.academics.models import Subject

        elsewhere = build_branch(self.fixture.organization, name="Elsewhere", code="ELS")
        foreign = Subject.objects.create(
            branch=elsewhere.branch,
            organization=elsewhere.organization,
            name="Foreign Subject",
        )

        self.client.post(
            reverse("academics:subject_list"),
            {"action": "delete", "selected": [str(foreign.pk)]},
        )
        self.assertTrue(Subject.objects.filter(pk=foreign.pk).exists())

    def test_a_user_without_the_delete_permission_gets_no_bulk_delete(self):
        reader = build_user(
            self.fixture.branch,
            username="reader",
            permissions=("core.access_academics",),
        )
        self.client.force_login(reader)

        response = self.client.get(reverse("academics:subject_list"))
        self.assertEqual(response.context["bulk_actions"], [])
        self.assertFalse(response.context["selectable"])

        refused = self.client.post(
            reverse("academics:subject_list"),
            {"action": "delete", "selected": [str(self.subjects[0].pk)]},
        )
        self.assertEqual(refused.status_code, 403)


class ExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="export_admin")
        build_student(cls.fixture, "Exported Student", "X-001")
        build_student(cls.fixture, "Other Student", "X-002")

    def setUp(self):
        self.client.login(username="export_admin", password=PASSWORD)

    def test_an_export_returns_a_spreadsheet_of_the_filtered_rows(self):
        from apps.audit.models import ActivityLog

        response = self.client.get(
            reverse("students:student_list"), {"export": "xlsx", "q": "Exported"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheet", response["Content-Type"])

        logged = ActivityLog.objects.filter(action="export").last()
        self.assertEqual(logged.metadata["rows"], 1)
        self.assertEqual(logged.metadata["filters"]["q"], "Exported")

    def test_a_user_without_the_export_permission_is_refused(self):
        reader = build_user(
            self.fixture.branch,
            username="no_export",
            permissions=("core.access_students",),
        )
        self.client.force_login(reader)
        response = self.client.get(
            reverse("students:student_list"), {"export": "xlsx"}
        )
        self.assertEqual(response.status_code, 403)


class EveryListViewTests(TestCase):
    """Rules the whole application's list views are held to at once."""

    def test_a_relation_column_is_joined_rather_than_queried_per_row(self):
        # A column reading through a relation without select_related costs one
        # query per row - the classic N+1, invisible until the table is long.
        problems = []
        for name, (view, _route) in list_views().items():
            if view.model is None:
                continue
            joined = set(getattr(view, "select_related", ()) or ())
            joined |= set(getattr(view, "prefetch_related", ()) or ())
            for needed in tables.relation_prefixes(view.model, view.table_columns):
                if not any(
                    entry == needed or entry.startswith(needed + "__")
                    for entry in joined
                ):
                    problems.append(f"{name}: {needed}")
        self.assertEqual(problems, [], "columns reading an unjoined relation")

    def test_every_list_view_offers_at_least_one_sortable_column(self):
        problems = []
        for name, (view, _route) in list_views().items():
            if view.model is None or not view.table_columns:
                continue
            if not tables.sortable_columns(view.model, view.table_columns):
                problems.append(name)
        self.assertEqual(problems, [], "list views with nothing sortable")


class RowActionTests(EnglishLabelMixin, TestCase):
    """A module's own verb rides in the shared table, not in a table of its own."""

    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="row_admin")

    def setUp(self):
        super().setUp()
        self.client.login(username="row_admin", password=PASSWORD)

    def test_a_deleted_student_can_be_restored_from_the_shared_table(self):
        from apps.students.models import Student

        student = build_student(self.fixture, "Deleted Student", "D-900")
        student.delete()

        page = self.client.get(reverse("students:student_archive"))
        self.assertContains(page, "D-900")
        # The button posts through the table's own form, so it carries the
        # target rather than nesting a form inside one.
        self.assertContains(
            page, f'formaction="{reverse("students:student_restore", args=[student.pk])}"'
        )

        self.client.post(reverse("students:student_restore", args=[student.pk]))
        self.assertTrue(Student.objects.filter(pk=student.pk).exists())

    def test_an_open_period_offers_closing_it_in_its_row(self):
        from apps.finance.models import FiscalPeriod

        period = FiscalPeriod.objects.filter(branch=self.fixture.branch).first()
        page = self.client.get(reverse("finance:period_list"))
        self.assertContains(
            page, f'formaction="{reverse("finance:period_close", args=[period.pk])}"'
        )


class OneTableEverywhereTests(TestCase):
    """Every list screen is the same table, not a module's own copy of one."""

    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="sweep_admin")

    def setUp(self):
        self.client.login(username="sweep_admin", password=PASSWORD)

    def test_every_list_page_renders_the_shared_table(self):
        problems = []
        for name, (_view, route) in sorted(list_views().items()):
            if route is None:
                continue
            response = self.client.get(reverse(route))
            if response.status_code != 200:
                problems.append(f"{name}: HTTP {response.status_code}")
            elif b"data-table-form" not in response.content:
                problems.append(f"{name}: not the shared table")
        self.assertEqual(problems, [], "list pages not using the shared table")

    def test_every_list_page_offers_the_same_paging_controls(self):
        problems = []
        for name, (_view, route) in sorted(list_views().items()):
            if route is None:
                continue
            response = self.client.get(reverse(route))
            if response.status_code == 200 and b"data-per-page" not in response.content:
                problems.append(name)
        self.assertEqual(problems, [], "list pages without the rows-per-page control")


class QueryCountTests(TestCase):
    """A longer page must not cost more queries than a short one."""

    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="query_admin")
        for index in range(60):
            build_student(cls.fixture, f"Counted {index:02d}", f"Q-{index:03d}")

    def setUp(self):
        self.client.login(username="query_admin", password=PASSWORD)

    def _queries(self, per_page):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                reverse("students:student_list"), {"per_page": str(per_page)}
            )
            self.assertEqual(response.status_code, 200)
        return len(captured)

    def test_the_query_count_does_not_grow_with_the_rows(self):
        # The definition of an N+1: twice the rows, twice the queries. The
        # count must stay flat instead.
        self._queries(25)  # the first request of a session warms its caches
        short = self._queries(25)
        long = self._queries(50)
        self.assertEqual(
            long,
            short,
            f"25 rows cost {short} queries, 50 rows cost {long}",
        )
