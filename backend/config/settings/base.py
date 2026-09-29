from pathlib import Path

import environ
from celery.schedules import crontab
from django.contrib.messages import constants as message_constants

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    JSON_LOGS=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
PASSWORD_RESET_EMAIL_SUBJECT = env("PASSWORD_RESET_EMAIL_SUBJECT", default="Password reset")
PASSWORD_RESET_URL_TEMPLATE = env("PASSWORD_RESET_URL_TEMPLATE", default="")

# PostgreSQL RLS: set True only with migration 0003_postgres_row_level_security applied
# and a DB user subject to RLS (not superuser). See ARCHITECTURE.md.
POSTGRES_SET_REQUEST_TENANT_GUC = env.bool("POSTGRES_SET_REQUEST_TENANT_GUC", default=False)

SECRET_KEY = env("SECRET_KEY", default="dev-only-change-in-production")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "192.168.100.15"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "apps.common",
    "apps.tenants",
    "apps.accounts",
    "apps.catalog",
    "apps.pos",
    "apps.inventory",
    "apps.purchasing",
    "apps.lodging",
    "apps.audit",
    "apps.events",
    "apps.finance",
    "apps.integrations",
    "apps.api",
    "apps.staff",
    "apps.console",
    "apps.realtime",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.request_id.RequestIdMiddleware",
    "apps.audit.middleware.AuditRequestContextMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.api.middleware.TenantContextMiddleware",
    "apps.staff.middleware.StaffSessionTenantMiddleware",
    "apps.common.middleware.operation_context.OperationContextMiddleware",
    "apps.api.middleware.PostgresRequestTenantGucMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.staff.context_processors.staff_branding",
                "apps.staff.context_processors.staff_nav",
                "apps.console.context_processors.console_nav",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

REDIS_URL = env("REDIS_URL", default="").strip()
MENU_CACHE_TTL_SECONDS = env.int("MENU_CACHE_TTL_SECONDS", default=60)

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "hotelnbarmgmt-locmem",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

DAILY_OPERATIONS_DIGEST_SEND = env.bool("DAILY_OPERATIONS_DIGEST_SEND", default=False)

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL or "memory://")
CELERY_TASK_ALWAYS_EAGER = env.bool(
    "CELERY_TASK_ALWAYS_EAGER",
    default=(CELERY_BROKER_URL == "memory://"),
)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_BEAT_SCHEDULE = {
    "daily-operations-digest": {
        "task": "apps.api.tasks.daily_operations_digest",
        "schedule": crontab(hour=6, minute=0),
    },
    "process-efris-submissions": {
        "task": "apps.integrations.tasks.process_efris_submission_queue",
        "schedule": crontab(minute="*/5"),
    },
}

PAYMENT_WEBHOOK_SHARED_SECRET = env("PAYMENT_WEBHOOK_SHARED_SECRET", default="")
EFRIS_INTEGRATION_ENABLED = env.bool("EFRIS_INTEGRATION_ENABLED", default=False)
EFRIS_QUEUE_BATCH_SIZE = env.int("EFRIS_QUEUE_BATCH_SIZE", default=50)
EFRIS_RETRY_BASE_SECONDS = env.int("EFRIS_RETRY_BASE_SECONDS", default=300)

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
FORMS_URLFIELD_ASSUME_HTTPS = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/staff/login/"
LOGIN_REDIRECT_URL = "/staff/"
LOGOUT_REDIRECT_URL = "/staff/login/"

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.TenantJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "jwt_obtain": "30/minute",
        "jwt_refresh": "60/minute",
        "offline_sync": "200/hour",
        "offline_batch": "60/hour",
        "catalog_version": "600/hour",
        "invite_accept": "20/minute",
        "invite_create": "60/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Hotel & Bar Management API",
    "DESCRIPTION": (
        "Tenant-scoped hospitality API. Authenticated calls use **Bearer** JWT. "
        "Send header **X-Tenant-Id** (tenant UUID) on tenant-scoped routes; omit on "
        "`/health/`, `/auth/token/`, `/auth/token/refresh/`, `/auth/password/reset/`, "
        "`/auth/password/reset/confirm/`, and `/invites/accept/`."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "SERVERS": [
        {"url": "http://127.0.0.1:8000", "description": "Local"},
        {"url": "https://api.example.com", "description": "Production (example)"},
    ],
    "TAGS": [
        {"name": "Health"},
        {"name": "Auth"},
        {"name": "Session"},
        {"name": "Tenant"},
        {"name": "Reports"},
        {"name": "POS"},
        {"name": "Invites"},
        {"name": "Catalog"},
        {"name": "Lodging"},
        {"name": "Inventory"},
        {"name": "Purchasing"},
        {"name": "Events"},
        {"name": "Integrations"},
        {"name": "Audit"},
    ],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "tenantId": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Tenant-Id",
                "description": "Active tenant UUID; required for most authenticated routes.",
            }
        }
    },
    "AUTHENTICATION_WHITELIST": [
        "apps.api.authentication.TenantJWTAuthentication",
    ],
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.api.schema_hooks.postprocess_tenant_header_param",
    ],
    "ENUM_NAME_OVERRIDES": {
        "PosOrderStatus": "apps.pos.models.OrderStatus",
        "LodgingFolioStatus": "apps.lodging.models.FolioStatus",
        "PurchaseOrderWorkflowStatus": "apps.purchasing.models.PurchaseOrderStatus",
    },
}

from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)

_LOG_JSON = env.bool("JSON_LOGS", default=False)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "apps.common.middleware.request_id.RequestIdLogFilter",
        },
        "operation_context": {
            "()": "apps.common.middleware.operation_context.OperationContextLogFilter",
        },
    },
    "formatters": {
        "json": {"()": "apps.common.json_logging.JsonLogFormatter"},
        "simple": {"format": "%(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id", "operation_context"],
            "formatter": "json" if _LOG_JSON else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

SENTRY_DSN = env("SENTRY_DSN", default="").strip()
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        send_default_pii=False,
    )
