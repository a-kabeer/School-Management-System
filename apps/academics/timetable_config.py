"""Central timetable working-week policy.

Keep the policy in one place so every timetable surface uses the same week.
The default matches the school's current schedule: Monday through Friday.
A future deployment can override the setting without changing timetable code.
"""

from django.conf import settings

DEFAULT_WORKING_WEEKDAYS = (0, 1, 2, 3, 4)


def working_weekdays():
    """Return the configured weekday numbers in fixed Monday-Friday order."""
    configured = getattr(settings, "ACADEMICS_WORKING_WEEKDAYS", DEFAULT_WORKING_WEEKDAYS)
    return tuple(day for day in DEFAULT_WORKING_WEEKDAYS if day in configured)


def is_working_day(weekday):
    return weekday in working_weekdays()
