"""Production defaults: TLS-oriented cookies, HSTS, and fail-closed ``SECRET_KEY``."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

_DEV_SECRET = "dev-only-change-in-production"
if not SECRET_KEY or str(SECRET_KEY).strip() == _DEV_SECRET:
    raise ImproperlyConfigured(
        "Production settings require a strong SECRET_KEY in the environment. "
        "Do not use the development default. Generate one and set SECRET_KEY before deploy."
    )

# HTTPS / browser security (tune via env behind reverse proxies)
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_csrf_trusted = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if _csrf_trusted:
    CSRF_TRUSTED_ORIGINS = _csrf_trusted
