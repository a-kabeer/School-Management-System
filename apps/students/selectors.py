"""Read-side queries for students.

Views call these instead of assembling querysets inline, so the joins and the
tenancy scoping stay in one reviewable place.
"""

from django.db.models import Count, Prefetch, Q

from .models import Student, StudentEnrollment, StudentGuardian


def students_for(user, branch=None, *, with_enrollment=True):
    queryset = Student.objects.for_user(user, branch)
    if with_enrollment:
        # No `to_attr`: Student.current_enrollment reads the standard prefetch
        # cache, so filling that is what spares the list one query per row.
        queryset = queryset.prefetch_related(
            Prefetch(
                "enrollments",
                queryset=StudentEnrollment.objects.filter(is_current=True)
                .select_related("school_class", "section", "academic_year"),
            )
        )
    return queryset


def student_detail(user, pk, branch=None):
    """One student with everything the detail page shows, or ``None``."""
    return (
        Student.objects.for_user(user, branch)
        .select_related("profile", "branch")
        .prefetch_related(
            Prefetch(
                "guardian_links",
                queryset=StudentGuardian.objects.select_related("guardian"),
            ),
            "documents",
            "enrollments__school_class",
            "enrollments__section",
            "status_history",
            "class_history__school_class",
        )
        .filter(pk=pk)
        .first()
    )


def students_in_section(user, section, branch=None):
    return (
        Student.objects.for_user(user, branch)
        .filter(enrollments__section=section, enrollments__is_current=True)
        .order_by("enrollments__roll_number", "full_name")
    )


def students_in_class(user, school_class, section=None, branch=None):
    queryset = Student.objects.for_user(user, branch).filter(
        enrollments__school_class=school_class, enrollments__is_current=True
    )
    if section is not None:
        queryset = queryset.filter(enrollments__section=section)
    return queryset.order_by("enrollments__roll_number", "full_name")


def class_strength(user, branch=None):
    """Head count per class for dashboards and reports."""
    return (
        StudentEnrollment.objects.for_user(user, branch)
        .filter(is_current=True, student__status=Student.Status.ACTIVE)
        .values("school_class__name", "school_class__level")
        .annotate(total=Count("id"))
        .order_by("school_class__level")
    )


def status_breakdown(user, branch=None):
    return (
        Student.objects.for_user(user, branch)
        .values("status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )


def search_students(user, term, branch=None, limit=20):
    """Type-ahead lookup used by the payment and attendance screens."""
    term = (term or "").strip()
    if not term:
        return Student.objects.none()
    return (
        Student.objects.for_user(user, branch)
        .filter(
            Q(full_name__icontains=term)
            | Q(admission_no__icontains=term)
            | Q(father_name__icontains=term)
        )
        .filter(status=Student.Status.ACTIVE)
        .order_by("full_name")[:limit]
    )
