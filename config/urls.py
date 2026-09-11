"""URL configuration.

Every application URL lives inside ``i18n_patterns`` so the active language is
part of the path (``/en/students/``, ``/ur/students/``). The health check and
the language switcher stay outside it, because they must work before a
language is chosen.
"""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("tenants/", include("apps.tenants.urls")),
    path("academics/", include("apps.academics.urls")),
    path("students/", include("apps.students.urls")),
    path("staff/", include("apps.staff.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("hifz/", include("apps.hifz.urls")),
    path("fees/", include("apps.fees.urls")),
    path("finance/", include("apps.finance.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("exams/", include("apps.exams.urls")),
    path("parents/", include("apps.parents.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("reports/", include("apps.reports.urls")),
    path("subscriptions/", include("apps.subscriptions.urls")),
    path("audit/", include("apps.audit.urls")),
    path("", include("apps.core.urls")),
    prefix_default_language=True,
)

handler403 = "apps.core.views.permission_denied_view"
handler404 = "apps.core.views.not_found_view"
handler500 = "apps.core.views.server_error_view"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
