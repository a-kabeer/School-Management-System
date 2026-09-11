"""Staff service layer."""

from django.db import transaction

from apps.audit.services import log_activity

from .models import Staff, StaffStatusHistory


@transaction.atomic
def change_staff_status(
    *, staff, new_status, effective_date, reason="", actor=None, request=None
):
    if new_status == staff.status:
        return staff

    previous_status = staff.status
    staff.status = new_status
    if new_status in {Staff.Status.RESIGNED, Staff.Status.TERMINATED}:
        staff.leaving_date = effective_date
        # Someone who has left should not stay on a live teaching roster.
        staff.teaching_assignments.filter(is_active=True).update(is_active=False)
        staff.hifz_assignments.filter(is_active=True).update(is_active=False)
    staff.save(update_fields=["status", "leaving_date", "updated_at"])

    StaffStatusHistory.objects.create(
        branch=staff.branch,
        organization=staff.organization,
        staff=staff,
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
        instance=staff,
        previous_values={"status": previous_status},
        new_values={"status": new_status},
        metadata={"event": "staff_status_change", "reason": reason},
    )
    return staff
