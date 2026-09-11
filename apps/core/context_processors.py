"""Template context shared by every page."""

from django.conf import settings
from django.utils import translation

from .constants import RTL_LANGUAGES
from .navigation import visible_navigation


def ui_chrome(request):
    """Language direction, navigation and permission helpers for templates."""
    language = translation.get_language() or settings.LANGUAGE_CODE
    user = getattr(request, "user", None)
    return {
        "ui_direction": "rtl" if language in RTL_LANGUAGES else "ltr",
        "ui_is_rtl": language in RTL_LANGUAGES,
        "ui_language": language,
        "ui_languages": settings.LANGUAGES,
        "navigation": visible_navigation(
            user,
            getattr(request, "active_branch", None),
            current_path=getattr(request, "path", "") or "",
        ),
        "site_name": settings.SITE_NAME,
    }
