"""Celery daily_operations_digest: shared CSV paths and optional email."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.api.tasks import daily_operations_digest
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.staff.report_csv import format_cashbook_csv_for_tenant_range, format_sales_summary_csv
from apps.tenants.models import Site, Tenant

from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_daily_operations_digest_logs_without_sending_mail():
    tenant = Tenant.objects.create(name="Digest Co", slug="digest-co")
    Site.objects.create(tenant=tenant, name="HQ")
    user = User.objects.create_user(email="owner@digest-co.test", password="x")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
    cat = FinanceCategory.objects.create(
        tenant=tenant, name="Petty", kind=FinanceCategoryKind.EXPENSE
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
        with patch("apps.api.tasks.EmailMessage.send") as send_mail_msg:
            daily_operations_digest()
    send_mail_msg.assert_not_called()


@pytest.mark.django_db
def test_daily_operations_digest_sends_when_enabled():
    tenant = Tenant.objects.create(name="Digest Send", slug="digest-send")
    Site.objects.create(tenant=tenant, name="HQ")
    user = User.objects.create_user(email="admin@digest-send.test", password="x")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.TENANT_ADMIN)
    day = timezone.now().date() - timedelta(days=1)

    sales_body = format_sales_summary_csv(tenant.id, day, day, outlet_id=None)
    cash_body = format_cashbook_csv_for_tenant_range(tenant.id, day, day)

    with patch.object(settings, "DAILY_OPERATIONS_DIGEST_SEND", True):
        with patch("apps.api.tasks.EmailMessage") as EM:
            instance = EM.return_value
            daily_operations_digest()
    EM.assert_called_once()
    instance.attach.assert_called()
    instance.send.assert_called_once_with(fail_silently=False)
    assert "net_sales" in sales_body
    assert "transaction_date" in cash_body
