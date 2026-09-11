"""ID cards: what goes on them, in which language, and what a scan reveals.

The privacy rule these tests hold is that the verification page a QR code
opens shows only what is already printed on the card face. Anything a card
does not display — address, phone, date of birth — must not appear there
either, because that page is reachable by anyone holding the card.
"""

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.core import idcards
from apps.core.tests.factories import (
    build_admin,
    build_branch,
    build_staff,
    build_student,
)

PASSWORD = "Str0ngPassphrase!42"


class CardBuildingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        cls.student = build_student(cls.fixture, "Ayesha Khan", "ADM-100")
        cls.student.father_name = "Kabeer Khan"
        cls.student.date_of_birth = dt.date(2014, 4, 9)
        cls.student.phone = "+923001234567"
        cls.student.address = "12 Example Street"
        cls.student.save()
        cls.staff = build_staff(cls.fixture, "Yusuf Ali", "EMP-100")

    def test_a_student_card_carries_the_identity_fields(self):
        card = idcards.student_card(self.student)

        self.assertEqual(card.identifier, "ADM-100")
        self.assertEqual(card.full_name, "Ayesha Khan")
        self.assertTrue(card.valid)
        self.assertIn(("Father's Name", "Kabeer Khan"), card.rows)
        self.assertIn(("Class", self.fixture.school_class.name), card.rows)

    def test_a_staff_card_carries_the_employment_fields(self):
        card = idcards.staff_card(self.staff)

        self.assertEqual(card.identifier, "EMP-100")
        self.assertEqual(card.full_name, "Yusuf Ali")
        labels = [label for label, _value in card.rows]
        self.assertIn("Designation", labels)
        self.assertIn("Joining Date", labels)

    def test_the_qr_is_inline_svg_pointing_at_the_verification_page(self):
        card = idcards.student_card(self.student)

        self.assertTrue(card.qr_svg.lstrip().startswith("<svg"))
        self.assertNotIn("<?xml", card.qr_svg)
        self.assertEqual(
            card.verify_url, reverse("core:verify", args=["student", self.student.pk])
        )

    def test_an_empty_field_is_left_off_the_card(self):
        blank = build_student(self.fixture, "No Details", "ADM-101")
        card = idcards.student_card(blank)
        self.assertNotIn("Father's Name", [label for label, _value in card.rows])

    def test_an_inactive_person_gets_an_invalid_card(self):
        from apps.students.models import Student

        self.student.status = Student.Status.INACTIVE
        card = idcards.student_card(self.student)
        self.assertFalse(card.valid)
        self.assertEqual(card.validity_label, "Not valid")


class CardLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        cls.student = build_student(cls.fixture, "Ayesha Khan", "ADM-200")
        cls.student.father_name = "Kabeer Khan"
        cls.student.save()

    def test_labels_are_written_in_the_cards_language(self):
        urdu = idcards.student_card(self.student, language="ur")
        arabic = idcards.student_card(self.student, language="ar")

        self.assertEqual(urdu.id_label, "طالب علم نمبر")
        self.assertIn("والد کا نام", [label for label, _value in urdu.rows])
        self.assertEqual(arabic.id_label, "رقم الطالب")
        self.assertIn("اسم الأب", [label for label, _value in arabic.rows])

    def test_a_persons_own_name_is_never_translated(self):
        # Only the labels change language; proper names are the record's own.
        for language in ("en", "ur", "ar"):
            with self.subTest(language=language):
                card = idcards.student_card(self.student, language=language)
                self.assertEqual(card.full_name, "Ayesha Khan")
                self.assertIn(("Kabeer Khan"), [value for _label, value in card.rows])

    def test_an_unknown_language_falls_back_to_english(self):
        card = idcards.student_card(self.student, language="fr")
        self.assertEqual(card.id_label, "Student ID")

    def test_the_card_language_is_independent_of_the_interface_language(self):
        # A madrasa running its interface in English still prints Urdu cards.
        with translation.override("en"):
            card = idcards.student_card(self.student, language="ur")
        self.assertEqual(card.title, "طالب علم شناختی کارڈ")


class CardPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        cls.student = build_student(cls.fixture, "Ayesha Khan", "ADM-300")
        cls.staff = build_staff(cls.fixture, "Yusuf Ali", "EMP-300")
        build_admin(cls.fixture.branch, username="card_admin")

    def setUp(self):
        self.client.login(username="card_admin", password=PASSWORD)

    def test_a_student_card_page_renders(self):
        response = self.client.get(
            reverse("core:student_card", args=[self.student.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ADM-300")

    def test_a_staff_card_page_renders(self):
        response = self.client.get(reverse("core:staff_card", args=[self.staff.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EMP-300")

    def test_a_card_in_urdu_lays_out_right_to_left(self):
        response = self.client.get(
            reverse("core:student_card", args=[self.student.pk]), {"lang": "ur"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="ur"')
        self.assertContains(response, 'dir="rtl"')

    def test_an_english_card_lays_out_left_to_right(self):
        response = self.client.get(
            reverse("core:student_card", args=[self.student.pk]), {"lang": "en"}
        )
        self.assertContains(response, 'dir="ltr"')

    def test_the_back_of_the_card_is_optional(self):
        front_only = self.client.get(
            reverse("core:student_card", args=[self.student.pk])
        )
        self.assertNotContains(front_only, "idcard-back")

        with_back = self.client.get(
            reverse("core:student_card", args=[self.student.pk]), {"back": "1"}
        )
        self.assertContains(with_back, "idcard-back")

    def test_a_bulk_sheet_lists_the_branch_students(self):
        response = self.client.get(reverse("core:student_cards"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ADM-300")

    def test_a_card_from_another_branch_is_not_reachable(self):
        other = build_branch(self.fixture.organization, name="Elsewhere", code="ELS")
        foreign = build_student(other, "Foreign Student", "ADM-999")

        response = self.client.get(reverse("core:student_card", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)

        sheet = self.client.get(reverse("core:student_cards"))
        self.assertNotContains(sheet, "ADM-999")


class VerificationPageTests(TestCase):
    """The QR target is public, so what it shows is a privacy decision."""

    @classmethod
    def setUpTestData(cls):
        cls.fixture = build_branch()
        cls.student = build_student(cls.fixture, "Ayesha Khan", "ADM-400")
        cls.student.father_name = "Kabeer Khan"
        cls.student.date_of_birth = dt.date(2014, 4, 9)
        cls.student.phone = "+923001234567"
        cls.student.address = "12 Example Street"
        cls.student.save()
        cls.staff = build_staff(cls.fixture, "Yusuf Ali", "EMP-400")

    def test_a_scan_works_without_signing_in(self):
        response = self.client.get(
            reverse("core:verify", args=["student", self.student.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ayesha Khan")
        self.assertContains(response, "ADM-400")

    def test_a_scan_reveals_nothing_private(self):
        response = self.client.get(
            reverse("core:verify", args=["student", self.student.pk])
        )
        for private in (b"2014-04-09", b"+923001234567", b"12 Example Street",
                        b"Kabeer Khan"):
            with self.subTest(value=private):
                self.assertNotIn(private, response.content)

    def test_a_staff_scan_shows_the_role_not_the_contact_details(self):
        response = self.client.get(
            reverse("core:verify", args=["staff", self.staff.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EMP-400")
        self.assertNotContains(response, self.staff.basic_salary)

    def test_an_unknown_card_is_not_confirmed(self):
        import uuid

        response = self.client.get(
            reverse("core:verify", args=["student", uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "not recognised", status_code=404)

    def test_an_unknown_kind_is_rejected(self):
        import uuid

        response = self.client.get(
            reverse("core:verify", args=["guardian", uuid.uuid4()])
        )
        self.assertEqual(response.status_code, 404)

    def test_an_inactive_person_is_shown_as_invalid(self):
        from apps.students.models import Student

        self.student.status = Student.Status.INACTIVE
        self.student.save(update_fields=["status"])

        response = self.client.get(
            reverse("core:verify", args=["student", self.student.pk])
        )
        self.assertContains(response, "Not valid")
