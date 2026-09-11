"""Language switching and text direction."""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.core.constants import RTL_LANGUAGES
from apps.core.context_processors import ui_chrome
from apps.core.tests.factories import build_admin, build_branch

PASSWORD = "Str0ngPassphrase!42"


class LanguageSwitchingTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        build_admin(self.fixture.branch, username="speaker")
        self.client.login(username="speaker", password=PASSWORD)

    def tearDown(self):
        # Django does not reset the active language between tests, so a test
        # that switches it would otherwise leak into whatever runs next.
        translation.activate(settings.LANGUAGE_CODE)

    def test_urls_carry_the_language_prefix(self):
        self.assertTrue(reverse("core:dashboard").startswith("/en/"))
        with translation.override("ur"):
            self.assertTrue(reverse("core:dashboard").startswith("/ur/"))

    def test_switching_to_urdu_sets_the_cookie(self):
        response = self.client.post(
            reverse("set_language"), {"language": "ur", "next": "/en/dashboard/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.cookies["sms_language"].value, "ur")

    def test_each_language_renders(self):
        for code in ("en", "ur", "ar"):
            with self.subTest(language=code):
                response = self.client.get(f"/{code}/dashboard/")
                self.assertEqual(response.status_code, 200)

    def test_direction_follows_the_language(self):
        for code in ("en", "ur", "ar"):
            with self.subTest(language=code):
                response = self.client.get(f"/{code}/dashboard/")
                expected = 'dir="rtl"' if code in RTL_LANGUAGES else 'dir="ltr"'
                self.assertContains(response, expected)
                self.assertContains(response, f'lang="{code}"')

    def test_the_context_processor_reports_direction(self):
        request = self.client.get("/en/dashboard/").wsgi_request
        with translation.override("ar"):
            context = ui_chrome(request)
            self.assertEqual(context["ui_direction"], "rtl")
            self.assertTrue(context["ui_is_rtl"])
        with translation.override("en"):
            context = ui_chrome(request)
            self.assertEqual(context["ui_direction"], "ltr")
            self.assertFalse(context["ui_is_rtl"])

    def test_every_configured_language_is_offered(self):
        response = self.client.get("/en/dashboard/")
        for code in ("en", "ur", "ar"):
            self.assertContains(response, f'value="{code}"')

    def test_the_compiled_catalogues_are_actually_used(self):
        from django.utils.translation import gettext

        with translation.override("ur"):
            self.assertEqual(gettext("Dashboard"), "ڈیش بورڈ")
        with translation.override("ar"):
            self.assertEqual(gettext("Dashboard"), "لوحة التحكم")
        with translation.override("en"):
            self.assertEqual(gettext("Dashboard"), "Dashboard")

    def test_translated_text_reaches_the_page(self):
        response = self.client.get("/ur/dashboard/")
        self.assertContains(response, "ڈیش بورڈ")


class SecurityHeaderTests(TestCase):
    def test_the_login_page_sets_a_csrf_token(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_post_without_a_csrf_token_is_refused(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post(
            reverse("accounts:login"), {"username": "x", "password": "y"}
        )
        self.assertEqual(response.status_code, 403)

    def test_clickjacking_protection_is_on(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_the_health_endpoint_is_public(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
