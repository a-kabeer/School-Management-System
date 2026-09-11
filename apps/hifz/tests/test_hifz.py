"""Hifz progress tracking."""

import datetime as dt
from decimal import Decimal

from django.db.utils import IntegrityError
from django.test import TestCase

from apps.core.tests.factories import build_branch, build_staff, build_student, build_user
from apps.hifz.models import DailyProgress, HifzStudentProfile, LessonType, Revision
from apps.hifz.services import (
    complete_revision,
    progress_summary,
    recalculate_memorized,
    record_daily_progress,
)

DATE = dt.date(2026, 6, 1)


class HifzProgressTests(TestCase):
    def setUp(self):
        self.fixture = build_branch()
        self.actor = build_user(self.fixture.branch, username="ustadh_user")
        self.teacher = build_staff(self.fixture, name="Ustadh Yusuf")
        self.student = build_student(self.fixture, "Hafiz Student", "H-001")
        self.profile = HifzStudentProfile.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            student=self.student,
            stage=HifzStudentProfile.Stage.HIFZ,
            started_on=DATE,
            current_para=1,
        )

    def test_recording_sabaq_moves_the_student_forward(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            teacher=self.teacher,
            from_para=1,
            to_para=3,
            pages=Decimal("1.50"),
            mistakes=2,
            actor=self.actor,
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_para, 3)

    def test_sabqi_does_not_move_the_student_forward(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABQI,
            from_para=5,
            to_para=6,
            actor=self.actor,
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.current_para, 1)

    def test_re_recording_the_same_lesson_updates_it(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            from_para=1,
            to_para=2,
            mistakes=5,
        )
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            from_para=1,
            to_para=2,
            mistakes=1,
        )
        self.assertEqual(DailyProgress.objects.count(), 1)
        self.assertEqual(DailyProgress.objects.first().mistakes, 1)

    def test_the_database_refuses_a_duplicate_lesson(self):
        record_daily_progress(
            hifz_profile=self.profile, date=DATE, lesson_type=LessonType.SABAQ
        )
        with self.assertRaises(IntegrityError):
            DailyProgress.objects.create(
                branch=self.fixture.branch,
                organization=self.fixture.organization,
                hifz_profile=self.profile,
                date=DATE,
                lesson_type=LessonType.SABAQ,
            )

    def test_all_three_daily_duties_coexist_on_one_day(self):
        for lesson in (LessonType.SABAQ, LessonType.SABQI, LessonType.MANZIL):
            record_daily_progress(
                hifz_profile=self.profile, date=DATE, lesson_type=lesson
            )
        self.assertEqual(DailyProgress.objects.count(), 3)

    def test_memorized_paras_are_recomputed_from_the_log(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            from_para=1,
            to_para=7,
        )
        recalculate_memorized(self.profile, actor=self.actor)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.paras_memorized, Decimal("7.00"))

    def test_finishing_all_thirty_paras_completes_the_stage(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            from_para=29,
            to_para=30,
        )
        recalculate_memorized(self.profile, actor=self.actor)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.stage, HifzStudentProfile.Stage.COMPLETED)

    def test_the_summary_aggregates_effort(self):
        record_daily_progress(
            hifz_profile=self.profile,
            date=DATE,
            lesson_type=LessonType.SABAQ,
            pages=Decimal("2.00"),
            mistakes=3,
        )
        summary = progress_summary(
            self.actor, self.fixture.branch, hifz_profile=self.profile
        )
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["total_pages"], Decimal("2.00"))
        self.assertEqual(summary["total_mistakes"], 3)

    def test_completing_a_revision_records_the_date(self):
        revision = Revision.objects.create(
            branch=self.fixture.branch,
            organization=self.fixture.organization,
            hifz_profile=self.profile,
            from_para=1,
            to_para=5,
            scheduled_date=DATE,
        )
        complete_revision(
            revision=revision, completed_date=DATE, mistakes=1, actor=self.actor
        )
        revision.refresh_from_db()
        self.assertEqual(revision.status, Revision.Status.COMPLETED)
        self.assertEqual(revision.completed_date, DATE)
