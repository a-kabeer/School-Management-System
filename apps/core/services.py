"""Shared services: system settings.

Dashboard aggregation used to live here too. It now lives in
:mod:`apps.core.dashboard`, where it can be assembled per role.
"""

from .models import SystemSetting


def get_setting(key, default=None, organization=None):
    setting = SystemSetting.objects.filter(
        key=key, organization=organization
    ).first()
    if setting is None and organization is not None:
        setting = SystemSetting.objects.filter(key=key, organization=None).first()
    return setting.value if setting else default


def set_setting(key, value, *, organization=None, description="", actor=None):
    setting, _created = SystemSetting.objects.update_or_create(
        key=key,
        organization=organization,
        defaults={"value": value, "description": description},
    )
    if actor is not None:
        from apps.audit.services import log_activity

        log_activity(
            user=actor,
            organization=organization,
            action="settings_change",
            instance=setting,
            new_values={"key": key, "value": value},
        )
    return setting
