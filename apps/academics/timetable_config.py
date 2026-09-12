"""Central timetable working-week policy.

Each branch can choose its own working days. Existing deployments default to
Monday-Friday, while the policy remains centralized so forms, services and
views never duplicate weekday rules.
"""

from django.conf import settings

DEFAULT_WORKING_WEEKDAYS = (0, 1, 2, 3, 4)


def working_weekdays(branch=None):
    """Return configured weekday numbers in stable Monday-Sunday order."""
    configured = getattr(branch, "working_weekdays", None) if branch is not None else None
    if not configured:
        configured = getattr(settings, "ACADEMICS_WORKING_WEEKDAYS", DEFAULT_WORKING_WEEKDAYS)
    return tuple(sorted({int(day) for day in configured if 0 <= int(day) <= 6}))


def is_working_day(weekday, branch=None):
    return int(weekday) in working_weekdays(branch)
