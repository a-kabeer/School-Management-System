from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ParentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.parents"
    label = "parents"
    verbose_name = _("Parents")
