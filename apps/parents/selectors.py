"""Child-scoped queries for the parent portal.

Every portal view goes through :func:`accessible_students` or
:func:`get_child`. A parent's own guardian link is the only thing that puts a
student in scope, so an id typed into the URL for somebody else's child
resolves to nothing.
"""

from django.http import Http404
from django.utils.translation import gettext_lazy as _

from apps.students.models import Student


def guardian_for(user):
    """The guardian record behind a portal login, or ``None``."""
    return getattr(user, "guardian_profile", None)


def accessible_students(user):
    """Students this user may view in the portal."""
    guardian = guardian_for(user)
    if guardian is None:
        return Student.objects.none()
    return (
        Student.objects.filter(
            guardian_links__guardian=guardian,
            guardian_links__can_view_portal=True,
        )
        .select_related("branch")
        .distinct()
        .order_by("full_name")
    )


def get_child(user, student_id):
    """One child, or 404. Never trusts the id on its own."""
    student = accessible_students(user).filter(pk=student_id).first()
    if student is None:
        raise Http404(_("Record not found."))
    return student


def child_attendance(user, student, limit=30):
    from apps.attendance.models import StudentAttendance

    get_child(user, student.pk)
    return (
        StudentAttendance.objects.filter(student=student)
        .select_related("session__school_class")
        .order_by("-date")[:limit]
    )


def child_invoices(user, student):
    from apps.fees.models import FeeInvoice

    get_child(user, student.pk)
    return (
        FeeInvoice.objects.filter(student=student)
        .exclude(status=FeeInvoice.Status.DRAFT)
        .order_by("-issue_date")
    )


def child_payments(user, student, limit=20):
    from apps.fees.models import FeePayment

    get_child(user, student.pk)
    return (
        FeePayment.objects.filter(student=student, is_void=False)
        .select_related("payment_method", "invoice")
        .order_by("-payment_date")[:limit]
    )


def child_results(user, student):
    """Published results only - unpublished marks are not parent-visible."""
    from apps.exams.models import Exam, ResultSummary

    get_child(user, student.pk)
    return (
        ResultSummary.objects.filter(
            student_exam__student=student,
            student_exam__exam__status=Exam.Status.PUBLISHED,
        )
        .select_related("student_exam__exam", "grade")
        .order_by("-student_exam__exam__start_date")
    )


def child_hifz(user, student, limit=30):
    from apps.hifz.models import DailyProgress

    get_child(user, student.pk)
    profile = getattr(student, "hifz_profile", None)
    if profile is None:
        return None, DailyProgress.objects.none()
    progress = (
        DailyProgress.objects.filter(hifz_profile=profile)
        .select_related("teacher")
        .order_by("-date")[:limit]
    )
    return profile, progress
