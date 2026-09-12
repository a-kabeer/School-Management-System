from django.urls import resolve, reverse

from apps.academics.tests.test_workflow import AcademicsFixture


class AcademicsRegressionTests(AcademicsFixture):
    def test_all_academics_routes_resolve_to_real_views(self):
        routes = (
            ("academics:overview", ()),
            ("academics:year_list", ()),
            ("academics:year_create", ()),
            ("academics:year_detail", (self.year.pk,)),
            ("academics:year_update", (self.year.pk,)),
            ("academics:year_delete", (self.year.pk,)),
            ("academics:term_list", ()),
            ("academics:term_create", ()),
            ("academics:term_detail", (self.term.pk,)),
            ("academics:term_update", (self.term.pk,)),
            ("academics:term_delete", (self.term.pk,)),
            ("academics:class_list", ()),
            ("academics:class_create", ()),
            ("academics:class_detail", (self.school_class.pk,)),
            ("academics:class_update", (self.school_class.pk,)),
            ("academics:class_delete", (self.school_class.pk,)),
            ("academics:section_list", ()),
            ("academics:section_create", ()),
            ("academics:section_detail", (self.section.pk,)),
            ("academics:section_update", (self.section.pk,)),
            ("academics:section_delete", (self.section.pk,)),
            ("academics:subject_list", ()),
            ("academics:subject_create", ()),
            ("academics:subject_detail", (self.subject.pk,)),
            ("academics:subject_update", (self.subject.pk,)),
            ("academics:subject_delete", (self.subject.pk,)),
            ("academics:classsubject_list", ()),
            ("academics:classsubject_create", ()),
            ("academics:classsubject_detail", (self.class_subject.pk,)),
            ("academics:classsubject_update", (self.class_subject.pk,)),
            ("academics:classsubject_delete", (self.class_subject.pk,)),
            ("academics:assignment_list", ()),
            ("academics:assignment_create", ()),
            ("academics:assignment_detail", (self.assignment.pk,)),
            ("academics:assignment_update", (self.assignment.pk,)),
            ("academics:assignment_delete", (self.assignment.pk,)),
            ("academics:timetable", ()),
            ("academics:timetable_affected", ()),
            ("academics:timetable_list", ()),
            ("academics:timetable_create", ()),
            ("academics:timetable_detail", (self.slot.pk,)),
            ("academics:timetable_update", (self.slot.pk,)),
            ("academics:timetable_delete", (self.slot.pk,)),
        )
        for name, args in routes:
            with self.subTest(route=name):
                url = reverse(name, args=args)
                match = resolve(url)
                self.assertIsNotNone(match.func)

    def test_class_timetable_action_keeps_all_sections_semantics(self):
        response = self.client.get(reverse("academics:class_detail", args=[self.school_class.pk]))
        self.assertContains(response, f"/academics/timetable/?school_class={self.school_class.pk}")
        self.assertNotContains(response, "?school_class=%s&section=" % self.school_class.pk)

    def test_contextual_list_links_keep_origin_for_back_navigation(self):
        response = self.client.get(
            reverse("academics:class_detail", args=[self.school_class.pk]),
            {"return_to": reverse("academics:class_list") + "?page=2&sort=name"},
        )
        self.assertContains(response, "href=\"/academics/classes/?page=2&amp;sort=name\"")
        self.assertContains(response, "return_to=")

    def test_related_add_links_keep_origin_context(self):
        response = self.client.get(reverse("academics:class_detail", args=[self.school_class.pk]))
        self.assertContains(response, "return_to=%2Facademics%2Fclasses%2F")
