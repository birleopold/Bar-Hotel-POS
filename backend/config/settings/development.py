from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Run Celery tasks in-process so password reset and future jobs work without ``celery worker``.
CELERY_TASK_ALWAYS_EAGER = True
