"""Read helpers for the Academics screens.

The View screens all ask the same kind of question — what hangs off this
record, and how much of it — so the questions live here rather than being
re-asked slightly differently in each view.
"""

from django.urls import reverse


def listing(url_name, **params):
    """A list URL carrying the filter that makes it about one parent record.

    This is what turns "View sections" into "the sections of *this* class"
    without inventing a second screen: the list is the same list, already
    filtered, with its search, sorting and paging intact.
    """
    query = "&".join(f"{key}={value}" for key, value in params.items() if value)
    url = reverse(url_name)
    return f"{url}?{query}" if query else url


def year_terms(user, branch, year):
    from .models import Term

    return (
        Term.objects.for_user(user, branch)
        .filter(academic_year=year)
        .order_by("sequence")
    )


def class_sections(user, branch, school_class):
    from .models import Section

    return (
        Section.objects.for_user(user, branch)
        .filter(school_class=school_class)
        .select_related("class_teacher")
        .order_by("name")
    )


def class_subjects_for(user, branch, *, school_class=None, subject=None, year=None):
    from .models import ClassSubject

    queryset = (
        ClassSubject.objects.for_user(user, branch)
        .select_related("subject", "school_class", "academic_year")
        .order_by("school_class__level", "subject__name")
    )
    if school_class is not None:
        queryset = queryset.filter(school_class=school_class)
    if subject is not None:
        queryset = queryset.filter(subject=subject)
    if year is not None:
        queryset = queryset.filter(academic_year=year)
    return queryset


def assignments_for(user, branch, **filters):
    from .models import TeacherAssignment

    return (
        TeacherAssignment.objects.for_user(user, branch)
        .filter(**filters)
        .select_related(
            "teacher", "section", "class_subject__subject", "class_subject__school_class"
        )
        .order_by("teacher__full_name")
    )


def slots_for(user, branch, **filters):
    from .models import Timetable

    return (
        Timetable.objects.for_user(user, branch)
        .filter(**filters)
        .select_related(
            "teacher", "section__school_class", "class_subject__subject", "academic_year"
        )
        .order_by("weekday", "period")
    )


def section_students(user, branch, section):
    from apps.students.models import StudentEnrollment

    return (
        StudentEnrollment.objects.for_user(user, branch)
        .filter(section=section, is_current=True)
        .select_related("student")
        .order_by("roll_number", "student__full_name")
    )


def current_year(user, branch):
    from .models import AcademicYear

    return (
        AcademicYear.objects.for_user(user, branch).filter(is_current=True).first()
        or AcademicYear.objects.for_user(user, branch).first()
    )
