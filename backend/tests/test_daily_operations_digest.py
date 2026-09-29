"""Celery daily digest: verifies logging vs email paths."""

from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.api.tasks import daily_operations_digest
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.staff.report_csv import format_cashbook_csv_for_tenant_range, format_sales_summary_csv
from apps.tenants.models import Site, Tenant

User = get_user_model()

# Freeze "now" so digest_date and fixture rows stay deterministic and timezone-aware everywhere.
_DIGEST_FROZEN_NOW = datetime(2026, 5, 13, 14, 30, tzinfo=dt_timezone.utc)


@pytest.mark.django_db
def test_daily_operations_digest_logs_without_sending_mail():
    with patch("django.utils.timezone.now", return_value=_DIGEST_FROZEN_NOW):
        tenant = Tenant.objects.create(name="Digest Co", slug="digest-co")
        Site.objects.create(tenant=tenant, name="HQ")
        user = User.objects.create_user(email="owner@digest-co.test", password="x")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        cat = FinanceCategory.objects.create(
            tenant=tenant,
            name="Petty",
            kind=FinanceCategoryKind.EXPENSE,
        )
        day = timezone.now().date() - timedelta(days=1)
        CashbookEntry.objects.create(
            tenant=tenant,
            category=cat,
            site=None,
            amount=Decimal("3.00"),
            transaction_date=day,
            created_by=user,
        )

        with patch.object(settings, "DAILY_OPERATIONS_DIGEST_SEND", False):
            with patch("apps.api.tasks.EmailMessage.send") as mock_send:
                daily_operations_digest()
        mock_send.assert_not_called()


@pytest.mark.django_db
def test_daily_operations_digest_sends_when_enabled():
    with patch("django.utils.timezone.now", return_value=_DIGEST_FROZEN_NOW):
        tenant = Tenant.objects.create(name="Digest Send", slug="digest-send")
        Site.objects.create(tenant=tenant, name="HQ")
        user = User.objects.create_user(email="admin@digest-send.test", password="x")
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.TENANT_ADMIN)
        day = timezone.now().date() - timedelta(days=1)

        sales_preview = format_sales_summary_csv(tenant.id, day, day, outlet_id=None)
        cash_preview = format_cashbook_csv_for_tenant_range(tenant.id, day, day)

        with patch.object(settings, "DAILY_OPERATIONS_DIGEST_SEND", True):
            with patch("apps.api.tasks.EmailMessage") as mock_em_class:
                instance = mock_em_class.return_value
                daily_operations_digest()

        mock_em_class.assert_called_once()
        instance.attach.assert_called()
        instance.send.assert_called_once_with(fail_silently=False)
        assert "net_sales" in sales_preview
        assert "transaction_date" in cash_preview
