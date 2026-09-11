"""Django settings for the School Management System."""

import sys
from pathlib import Path

from decouple import Csv, config
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = "test" in sys.argv

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="insecure-development-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())

RENDER_EXTERNAL_HOSTNAME = config("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    "apps.core.apps.CoreConfig",
    "apps.tenants.apps.TenantsConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.academics.apps.AcademicsConfig",
    "apps.students.apps.StudentsConfig",
    "apps.staff.apps.StaffConfig",
    "apps.attendance.apps.AttendanceConfig",
    "apps.hifz.apps.HifzConfig",
    "apps.fees.apps.FeesConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.payroll.apps.PayrollConfig",
    "apps.exams.apps.ExamsConfig",
    "apps.parents.apps.ParentsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.reports.apps.ReportsConfig",
    "apps.subscriptions.apps.SubscriptionsConfig",
    "apps.audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditRequestMiddleware",
    "apps.tenants.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "apps.core.context_processors.ui_chrome",
                "apps.tenants.context_processors.tenant_context",
                "apps.notifications.context_processors.unread_notifications",
            ],
        },
    }
]

# --------------------------------------------------------------------------
# Database - PostgreSQL only. SQLite is never used, including for tests.
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="school_management"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        "OPTIONS": {"connect_timeout": 10},
        "TEST": {"NAME": config("DB_TEST_NAME", default="school_management_test")},
    }
}

DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    from urllib.parse import unquote, urlparse

    _parsed = urlparse(DATABASE_URL)
    DATABASES["default"].update(
        {
            "NAME": _parsed.path.lstrip("/"),
            "USER": unquote(_parsed.username or ""),
            "PASSWORD": unquote(_parsed.password or ""),
            "HOST": _parsed.hostname or "",
            "PORT": str(_parsed.port or "5432"),
        }
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.RoleAwareModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalization - English (LTR), Urdu (RTL), Arabic (RTL)
# --------------------------------------------------------------------------
LANGUAGE_CODE = config("LANGUAGE_CODE", default="en")
LANGUAGES = [
    ("en", _("English")),
    ("ur", _("Urdu")),
    ("ar", _("Arabic")),
]
LANGUAGE_COOKIE_NAME = "sms_language"
LANGUAGE_COOKIE_HTTPONLY = False
LANGUAGE_COOKIE_SAMESITE = "Lax"
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
TIME_ZONE = config("TIME_ZONE", default="Asia/Karachi")

# --------------------------------------------------------------------------
# Static / media
# --------------------------------------------------------------------------
STATIC_URL = config("STATIC_URL", default="/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = config("MEDIA_URL", default="/media/")
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if DEBUG or TESTING:
    STORAGES["staticfiles"] = {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    }

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000

# Enforced by apps.core.validators.validate_upload.
UPLOAD_MAX_SIZE_MB = config("UPLOAD_MAX_SIZE_MB", default=5, cast=int)
UPLOAD_ALLOWED_EXTENSIONS = config(
    "UPLOAD_ALLOWED_EXTENSIONS",
    default="pdf,png,jpg,jpeg,webp,docx,xlsx",
    cast=Csv(),
)

# --------------------------------------------------------------------------
# Auth flow
# --------------------------------------------------------------------------
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")

# Notification transports are resolved by dotted path, never hard-coded.
NOTIFICATION_BACKENDS = {
    "in_app": "apps.notifications.backends.InAppBackend",
    "email": "apps.notifications.backends.EmailBackend",
    "sms": config("SMS_BACKEND", default="apps.notifications.backends.NullBackend"),
    "whatsapp": config(
        "WHATSAPP_BACKEND", default="apps.notifications.backends.NullBackend"
    ),
    "push": config("PUSH_BACKEND", default="apps.notifications.backends.NullBackend"),
}

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=not DEBUG, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)

SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=60 * 60 * 8, cast=int)
SESSION_EXPIRE_AT_BROWSER_CLOSE = config(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE", default=False, cast=bool
)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# --------------------------------------------------------------------------
# Application defaults
# --------------------------------------------------------------------------
SITE_NAME = config("SITE_NAME", default="School Management System")
PAGE_SIZE = config("PAGE_SIZE", default=25, cast=int)
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"}
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}
