#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main() -> None:
    # A production VPS must not create a second SQLite database by accident.
    guarded = {"migrate", "makemigrations", "flush", "loaddata", "sqlflush"}
    command = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), "")
    if (
        command in guarded
        and os.path.isfile("/etc/leosoft-pos/pos.env")
        and os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.production"
    ):
        sys.exit(
            "Database-changing command refused on Fizo production host: "
            "load /etc/leosoft-pos/pos.env and explicitly set "
            "DJANGO_SETTINGS_MODULE=config.settings.production first. "
            "Prefer deployment/contabo/deploy-app.sh for migrations."
        )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Is it installed and available on your PYTHONPATH?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
