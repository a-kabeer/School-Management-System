"""Student service layer: admission, enrollment, transfers, status changes."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.audit.services import log_activity, snapshot
from apps.core.utils import next_sequence_number

from .models import (
    Student,
    StudentClassHistory,
    StudentEnrollment,
    StudentStatusHistory,
)


def next_admission_number(branch, prefix=None):
    """Next free admission number for a branch, e.g. ``ADM-00042``."""
    prefix = prefix or f"{branch.code.upper()}-"
    return next_sequence_number(
        Student.all_objects.filter(branch=branch), "admission_no", prefix=prefix
    )


@transaction.atomic
def admit_student(
    *,
    branch,
    academic_year,
    school_class,
    section=None,
    roll_number="",
    start_date=None,
    actor=None,
    request=None,
    **student_fields,
):
    """Create a student and their first enrollment as one unit.

    A half-admitted student (a record with no class) is the kind of state that
    quietly breaks attendance and billing later, so both rows are written in
    the same transaction or neither is.
    """
    if not student_fields.get("admission_no"):
        student_fields["admission_no"] = next_admission_number(branch)

    student = Student(branch=branch, organization=branch.organization, **student_fields)
    student.full_clean(exclude=["organization"])
    student.save()

    enrollment = enroll_student(
        student=student,
        academic_year=academic_year,
        school_class=school_class,
        section=section,
        roll_number=roll_number,
        start_date=start_date or student.admission_date,
        actor=actor,
        request=request,
        log=False,
    )

    log_activity(
        action="create",
        request=request,
        user=actor,
        instance=student,
        new_values=snapshot(student),
        metadata={"enrollment": str(enrollment.pk)},
    )
    return student, enrollment


@transaction.atomic
def enroll_student(
    *,
    student,
    academic_year,
    school_class,
    section=None,
    roll_number="",
    start_date=None,
    actor=None,
    request=None,
    log=True,
):
    """Place a student in a class, closing any enrollment still marked current."""
    if section is not None and section.school_class_id != school_class.pk:
        raise ValidationError({"section": _("That section belongs to a different class.")})

    start_date = start_date or academic_year.start_date

    StudentEnrollment.objects.filter(student=student, is_current=True).update(
        is_current=False, end_date=start_date
    )

    enrollment = StudentEnrollment(
        branch=student.branch,
        organization=student.organization,
        student=student,
        academic_year=academic_year,
        school_class=school_class,
        section=section,
        roll_number=roll_number,
        start_date=start_date,
        is_current=True,
    )
    enrollment.full_clean(exclude=["organization"])
    enrollment.save()

    StudentClassHistory.objects.create(
        branch=student.branch,
        organization=student.organization,
        student=student,
        academic_year=academic_year,
        school_class=school_class,
        section=section,
        moved_on=start_date,
        reason=_("Enrollment"),
        recorded_by=actor,
    )

    if log:
        log_activity(
            action="create",
            request=request,
            user=actor,
            instance=enrollment,
            new_values=snapshot(enrollment),
        )
    return enrollment


@transaction.atomic
def transfer_student(
    *, student, school_class, section=None, moved_on, reason="", actor=None, request=None
):
    """Move a student to another class/section inside the same academic year."""
    current = student.enrollments.filter(is_current=True).first()
    if current is None:
        raise ValidationError(_("This student has no current enrollment."))

    previous = snapshot(current)
    if section is not None and section.school_class_id != school_class.pk:
        raise ValidationError({"section": _("That section belongs to a different class.")})

    current.school_class = school_class
    current.section = section
    current.save(update_fields=["school_class", "section", "updated_at"])

    StudentClassHistory.objects.create(
        branch=student.branch,
        organization=student.organization,
        student=student,
        academic_year=current.academic_year,
        school_class=school_class,
        section=section,
        moved_on=moved_on,
        reason=reason,
        recorded_by=actor,
    )

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=current,
        previous_values=previous,
        new_values=snapshot(current),
        metadata={"event": "class_transfer"},
    )
    return current


@transaction.atomic
def change_student_status(
    *, student, new_status, effective_date, reason="", actor=None, request=None
):
    """Record a status change and keep the history row alongside it."""
    if new_status == student.status:
        return student

    previous_status = student.status
    student.status = new_status
    student.save(update_fields=["status", "updated_at"])

    if new_status != Student.Status.ACTIVE:
        # A student who has left should not stay on a live class register.
        student.enrollments.filter(is_current=True).update(
            is_current=False, end_date=effective_date
        )

    StudentStatusHistory.objects.create(
        branch=student.branch,
        organization=student.organization,
        student=student,
        previous_status=previous_status,
        new_status=new_status,
        effective_date=effective_date,
        reason=reason,
        changed_by=actor,
    )

    log_activity(
        action="update",
        request=request,
        user=actor,
        instance=student,
        previous_values={"status": previous_status},
        new_values={"status": new_status},
        metadata={"event": "status_change", "reason": reason},
    )
    return student
