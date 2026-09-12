from django.test import SimpleTestCase
from django.urls import reverse

from apps.academics.documents import DOCUMENTS


class AcademicDocumentArchitectureTests(SimpleTestCase):
    def test_supported_document_types_are_data_driven(self):
        self.assertEqual(
            set(DOCUMENTS),
            {
                "class-timetable",
                "section-timetable",
                "teacher-timetable",
                "class-summary",
                "section-summary",
                "teacher-assignments",
                "academic-year-summary",
            },
        )

    def test_document_route_is_shared(self):
        self.assertEqual(
            reverse("academics:document", kwargs={"document_type": "class-timetable"}),
            "/en/academics/documents/class-timetable/",
        )
