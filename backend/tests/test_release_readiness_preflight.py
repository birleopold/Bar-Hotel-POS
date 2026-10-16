"""Read-only release preflight must fail closed for unsafe production settings."""
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.finance.management.commands.verify_release_readiness import release_readiness_snapshot


@pytest.mark.django_db
def test_local_preflight_checks_db_and_schema_without_writing():
    result = release_readiness_snapshot()
    assert result["checks"]["database_connected"] is True
    assert result["checks"]["migrations_applied"] is True
    assert result["ready"] is True
    assert "database_is_postgresql" not in result["required_checks"]


@pytest.mark.django_db
@override_settings(DEBUG=True, ALLOWED_HOSTS=["*"])
def test_production_preflight_rejects_debug_and_wildcard_hosts():
    result = release_readiness_snapshot(require_production=True)
    assert not result["ready"]
    assert not result["checks"]["debug_disabled"]
    assert not result["checks"]["hosts_restricted"]
    with pytest.raises(CommandError):
        call_command("verify_release_readiness", require_production=True)


@pytest.mark.django_db
def test_production_preflight_never_passes_on_sqlite():
    result = release_readiness_snapshot(require_production=True)
    assert result["checks"]["database_is_postgresql"] is False
    assert not result["ready"]
