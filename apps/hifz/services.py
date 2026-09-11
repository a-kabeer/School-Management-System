"""Hifz service layer."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity, snapshot

from .models import TOTAL_PARAS, DailyProgress, HifzStudentProfile, LessonType, Revision


@transaction.atomic
def record_daily_progress(
    *, hifz_profile, date, lesson_type, actor=None, request=None, **values
):
    """Write (or correct) one day's Sabaq/Sabqi/Manzil entry.

    When new memorization is heard, the student's position in the Quran moves
    forward with it - keeping the profile and the progress log in step is the
    whole point of doing this in a service.
    """
    progress, created = DailyProgress.objects.update_or_create(
        hifz_profile=hifz_profile,
        date=date,
        lesson_type=lesson_type,
        defaults={
            "branch": hifz_profile.branch,
            "organization": hifz_profile.organization,
            **values,
        },
    )

    if lesson_type == LessonType.SABAQ and progress.to_para:
        profile_changed = False
        if progress.to_para > hifz_profile.current_para:
            hifz_profile.current_para = progress.to_para
            profile_changed = True
        if progress.surah and progress.surah != hifz_profile.current_surah:
            hifz_profile.current_surah = progress.surah
            profile_changed = True
        if profile_changed:
            hifz_profile.save(
                update_fields=["current_para", "current_surah", "updated_at"]
            )

    log_activity(
        action="create" if created else "update",
        request=request,
        user=actor,
        instance=progress,
        new_values=snapshot(progress),
    )
    return progress


@transaction.atomic
def complete_revision(*, revision, completed_date, mistakes=0, quality=None, actor=None, request=None):
    previous = snapshot(revision)
    revision.status = Revision.Status.COMPLETED
    revision.completed_date = completed_date
    revision.mistakes = mistakes
    revision.quality = quality
    revision.save(
        update_fields=["status", "completed_date", "mistakes", "quality", "updated_at"]
    )
    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=revision,
        previous_values=previous,
        new_values=snapshot(revision),
    )
    return revision


@transaction.atomic
def recalculate_memorized(hifz_profile, *, actor=None, request=None):
    """Recompute paras memorized from the Sabaq log.

    The furthest para ever heard as Sabaq is the honest measure; a hand-typed
    total drifts.
    """
    furthest = (
        DailyProgress.objects.filter(
            hifz_profile=hifz_profile, lesson_type=LessonType.SABAQ
        )
        .order_by("-to_para")
        .values_list("to_para", flat=True)
        .first()
    )
    memorized = Decimal(min(furthest or 0, TOTAL_PARAS))
    if memorized != hifz_profile.paras_memorized:
        previous = hifz_profile.paras_memorized
        hifz_profile.paras_memorized = memorized
        if memorized >= TOTAL_PARAS:
            hifz_profile.stage = HifzStudentProfile.Stage.COMPLETED
        hifz_profile.save(
            update_fields=["paras_memorized", "stage", "updated_at"]
        )
        log_activity(
            action="update",
            request=request,
            user=actor,
            instance=hifz_profile,
            previous_values={"paras_memorized": str(previous)},
            new_values={"paras_memorized": str(memorized)},
        )
    return hifz_profile


def progress_summary(user, branch=None, *, hifz_profile=None, date_from=None, date_to=None):
    """Aggregate Hifz effort for report cards and the Hifz report."""
    queryset = DailyProgress.objects.for_user(user, branch)
    if hifz_profile is not None:
        queryset = queryset.filter(hifz_profile=hifz_profile)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)

    return queryset.aggregate(
        entries=Count("id"),
        total_pages=Sum("pages"),
        total_lines=Sum("lines"),
        total_mistakes=Sum("mistakes"),
        average_quality=Avg("quality"),
    )
