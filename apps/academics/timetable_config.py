"""Central timetable working-week policy.

The current default is Monday through Friday. A future deployment can
override ``ACADEMICS_WORKING_WEEKDAYS`` without duplicating weekday checks
through timetable views and forms.
"""

from django.conf import settings

DEFAULT_WORKING_WEEKDAYS = (0, 1, 2, 3, 4)


def working_weekdays():
    """Return configured weekday numbers in stable calendar order."""
    configured = getattr(settings, "ACADEMICS_WORKING_WEEKDAYS", DEFAULT_WORKING_WEEKDAYS)
    return tuple(sorted({int(day) for day in configured if 0 <= int(day) <= 6}))


def is_working_day(weekday):
    return weekday in working_weekdays()
