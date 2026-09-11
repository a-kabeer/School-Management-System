"""Every list and form page renders for an administrator.

A broad smoke test like this is what catches a template that references a
context key the view never sets - the kind of break unit tests walk straight
past.
"""

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.factories import build_admin, build_branch

PASSWORD = "Str0ngPassphrase!42"

#: Pages reachable with no object id.
INDEX_PAGES = [
    "core:dashboard",
    "accounts:profile",
    "accounts:change_password",
    "accounts:user_list",
    "accounts:user_create",
    "accounts:role_list",
    "accounts:role_create",
    "tenants:branch_list",
    "tenants:branch_create",
    "tenants:organization",
    "academics:year_list",
    "academics:year_create",
    "academics:term_list",
    "academics:term_create",
    "academics:class_list",
    "academics:class_create",
    "academics:section_list",
    "academics:section_create",
    "academics:subject_list",
    "academics:subject_create",
    "academics:classsubject_list",
    "academics:classsubject_create",
    "academics:assignment_list",
    "academics:assignment_create",
    "academics:timetable_list",
    "academics:timetable_create",
    "students:student_list",
    "students:student_create",
    "students:student_archive",
    "students:guardian_list",
    "students:guardian_create",
    "students:guardian_link",
    "students:document_create",
    "students:enrollment_list",
    "students:enrollment_create",
    "staff:staff_list",
    "staff:staff_create",
    "staff:department_list",
    "staff:department_create",
    "staff:designation_list",
    "staff:designation_create",
    "staff:document_create",
    "staff:assignment_create",
    "attendance:session_list",
    "attendance:today",
    "attendance:mark",
    "attendance:record_list",
    "attendance:staff_list",
    "attendance:clock",
    "attendance:staff_month",
    "core:student_cards",
    "core:staff_cards",
    "hifz:profile_list",
    "hifz:profile_create",
    "hifz:progress_list",
    "hifz:progress_create",
    "hifz:revision_list",
    "hifz:revision_create",
    "hifz:assessment_list",
    "hifz:assessment_create",
    "hifz:teacher_list",
    "hifz:teacher_create",
    "fees:type_list",
    "fees:type_create",
    "fees:structure_list",
    "fees:structure_create",
    "fees:studentfee_list",
    "fees:studentfee_create",
    "fees:discount_list",
    "fees:discount_create",
    "fees:invoice_list",
    "fees:invoice_generate",
    "fees:payment_list",
    "fees:payment_create",
    "fees:refund_list",
    "finance:account_list",
    "finance:account_create",
    "finance:accounttype_list",
    "finance:accounttype_create",
    "finance:journal_list",
    "finance:journal_create",
    "finance:entry_list",
    "finance:entry_create",
    "finance:period_list",
    "finance:period_create",
    "finance:method_list",
    "finance:method_create",
    "finance:trial_balance",
    "payroll:component_list",
    "payroll:component_create",
    "payroll:structure_list",
    "payroll:structure_create",
    "payroll:structureline_create",
    "payroll:salary_list",
    "payroll:salary_create",
    "payroll:period_list",
    "payroll:period_create",
    "payroll:run_list",
    "payroll:run_process",
    "payroll:payment_list",
    "exams:grade_list",
    "exams:grade_create",
    "exams:term_list",
    "exams:term_create",
    "exams:exam_list",
    "exams:exam_create",
    "exams:subject_create",
    "exams:schedule_create",
    "exams:result_list",
    "parents:guardian_list",
    "parents:request_list",
    "notifications:list",
    "notifications:announce",
    "notifications:template_list",
    "notifications:template_create",
    "reports:index",
    "reports:saved_list",
    "subscriptions:detail",
    "subscriptions:invoice_list",
    "audit:list",
]


class PageSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        build_admin(cls.fixture.branch, username="smoke_admin")

    def setUp(self):
        self.client.login(username="smoke_admin", password=PASSWORD)

    def test_every_index_page_renders(self):
        for name in INDEX_PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code, 200, msg=f"{name} returned {response.status_code}"
                )

    def test_no_page_leaks_an_unclosed_template_comment(self):
        # Django's {# #} comment is single-line only; a multi-line one renders
        # as visible page text instead. That is invisible to a status-code
        # check, so assert on the markup.
        for name in INDEX_PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertNotIn(
                    b"{#",
                    response.content,
                    msg=f"{name} rendered a raw template comment",
                )

    def test_every_report_renders(self):
        from apps.reports.registry import REGISTRY

        for key in REGISTRY:
            with self.subTest(report=key):
                response = self.client.get(reverse("reports:detail", args=[key]))
                self.assertEqual(response.status_code, 200)

    def test_pages_render_in_urdu(self):
        # RTL rendering exercises the same templates through a different
        # locale, which is where a missing {% load i18n %} shows up.
        for name in ("core:dashboard", "students:student_list", "fees:invoice_list"):
            with self.subTest(page=name):
                path = reverse(name).replace("/en/", "/ur/", 1)
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'dir="rtl"')
