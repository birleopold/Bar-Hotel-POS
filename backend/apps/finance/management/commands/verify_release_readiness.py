"""Read-only release gate: database connectivity, migration state and safe settings.

Run with production settings before switching traffic. It never migrates,
creates sample transactions, or contacts a financial/fiscal provider.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def release_readiness_snapshot(*, require_production=False):
    checks = {}
    checks["debug_disabled"] = not settings.DEBUG
    checks["production_settings"] = settings.SETTINGS_MODULE == "config.settings.production"
    checks["secret_configured"] = len(str(settings.SECRET_KEY or "")) >= 32
    checks["hosts_restricted"] = bool(settings.ALLOWED_HOSTS) and "*" not in settings.ALLOWED_HOSTS
    checks["secure_cookies"] = bool(
        settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
    )
    checks["database_is_postgresql"] = connection.vendor == "postgresql"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database_connected"] = cursor.fetchone()[0] == 1
        executor = MigrationExecutor(connection)
        checks["migrations_applied"] = not bool(
            executor.migration_plan(executor.loader.graph.leaf_nodes())
        )
    except Exception:
        checks["database_connected"] = False
        checks["migrations_applied"] = False

    required = ["database_connected", "migrations_applied"]
    if require_production:
        required += [
            "debug_disabled", "production_settings", "secret_configured",
            "hosts_restricted", "secure_cookies", "database_is_postgresql",
        ]
    return {"ready": all(checks[key] for key in required), "checks": checks,
            "required_checks": required,
            "note": "Read-only application preflight; restore drills, workers, TLS, browsers and provider verification remain separate."}


class Command(BaseCommand):
    help = "Read-only JSON release preflight; --require-production enforces deployment settings."

    def add_arguments(self, parser):
        parser.add_argument("--require-production", action="store_true")

    def handle(self, *args, **options):
        result = release_readiness_snapshot(
            require_production=options["require_production"]
        )
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        if not result["ready"]:
            raise CommandError("Release preflight failed; see the checks above.")
