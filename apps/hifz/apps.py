from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HifzConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hifz"
    label = "hifz"
    verbose_name = _("Hifz")
