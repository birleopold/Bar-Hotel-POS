"""Scheduled owner reports: local dates, opt-in delivery, recipient scope and replay."""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.pos.models import Order, OrderLine, OrderStatus, Payment
from apps.staff.report_csv import format_sales_summary_csv_from_summary
from apps.api.owner_reports import (
    _summary_for_schedule, deliver_owner_report, eligible_recipients,
    scheduled_period,
)
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import (
    OwnerReportDelivery, OwnerReportDeliveryStatus, OwnerReportFrequency,
    OwnerReportSchedule, TenantSettings,
)
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def schedule_fixture(slug="scheduled-owner-fixture"):
    a = _seed_tenant_bundle(
        name="Owner Digest", slug=slug,
        user_email=slug + "@example.test",
    )
    config = TenantSettings.objects.get(tenant=a["tenant"])
    config.default_timezone = "Africa/Kampala"
    config.save(update_fields=["default_timezone"])
    schedule = OwnerReportSchedule.objects.create(
        tenant=a["tenant"], frequency=OwnerReportFrequency.DAILY,
        local_send_hour=8,
    )
    owner = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    schedule.recipients.add(owner)
    return a, schedule


@pytest.mark.django_db
def test_daily_weekly_monthly_schedule_uses_local_dates():
    a, schedule = schedule_fixture("local-owner-report")
    instant = datetime(2026, 10, 16, 6, 30, tzinfo=dt_timezone.utc)
    assert scheduled_period(schedule, at=instant) == (
        datetime(2026, 10, 15).date(), datetime(2026, 10, 15).date(),
    )
    schedule.frequency = OwnerReportFrequency.WEEKLY
    schedule.send_weekday = 4  # Friday
    assert scheduled_period(schedule, at=instant) == (
        datetime(2026, 10, 9).date(), datetime(2026, 10, 15).date(),
    )
    schedule.frequency = OwnerReportFrequency.MONTHLY
    schedule.send_monthday = 16
    assert scheduled_period(schedule, at=instant) == (
        datetime(2026, 9, 1).date(), datetime(2026, 9, 30).date(),
    )
    schedule.send_monthday = 1
    assert scheduled_period(schedule, at=instant) is None


@pytest.mark.django_db
def test_disabled_schedule_never_attempts_email():
    _, schedule = schedule_fixture("disabled-owner-report")
    now = datetime(2026, 10, 16, 6, 30, tzinfo=dt_timezone.utc)
    with patch("apps.api.owner_reports.EmailMessage.send") as mock_send:
        assert deliver_owner_report(schedule=schedule, at=now) is None
    mock_send.assert_not_called()
    assert not OwnerReportDelivery.objects.exists()


@pytest.mark.django_db
@override_settings(
    DEFAULT_FROM_EMAIL="reports@example.test",
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
)
def test_scheduled_digest_sends_one_pdf_and_csv_and_deduplicates():
    a, schedule = schedule_fixture("sent-owner-report")
    schedule.is_enabled = True
    schedule.save(update_fields=["is_enabled"])
    now = datetime(2026, 10, 16, 6, 30, tzinfo=dt_timezone.utc)
    with patch("apps.api.owner_reports.EmailMessage.send", return_value=1) as email:
        first = deliver_owner_report(schedule=schedule, at=now)
        second = deliver_owner_report(schedule=schedule, at=now + timedelta(minutes=20))
    assert first is not None
    assert second is None
    assert email.call_count == 1
    delivery = OwnerReportDelivery.objects.get(tenant=a["tenant"])
    assert delivery.status == OwnerReportDeliveryStatus.SENT
    assert delivery.attempts == 1
    assert delivery.sent_at is not None
    assert delivery.recipient_snapshot == [a["user"].email]


@pytest.mark.django_db
@override_settings(
    DEFAULT_FROM_EMAIL="reports@example.test",
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
)
def test_failed_email_can_retry_without_creating_duplicate_delivery():
    a, schedule = schedule_fixture("retry-owner-report")
    schedule.is_enabled = True
    schedule.save(update_fields=["is_enabled"])
    now = datetime(2026, 10, 16, 6, 30, tzinfo=dt_timezone.utc)
    with patch("apps.api.owner_reports.EmailMessage.send", side_effect=OSError("SMTP down")):
        with pytest.raises(OSError):
            deliver_owner_report(schedule=schedule, at=now)
    row = OwnerReportDelivery.objects.get(tenant=a["tenant"])
    assert row.status == OwnerReportDeliveryStatus.FAILED
    assert row.attempts == 1
    with patch("apps.api.owner_reports.EmailMessage.send", return_value=1) as ok:
        assert deliver_owner_report(schedule=schedule, at=now + timedelta(minutes=5)) is None
        again = deliver_owner_report(schedule=schedule, at=now + timedelta(minutes=60))
    assert ok.call_count == 1
    assert again == row.pk
    row.refresh_from_db()
    assert row.status == OwnerReportDeliveryStatus.SENT
    assert row.attempts == 2
    assert OwnerReportDelivery.objects.filter(tenant=a["tenant"]).count() == 1


@pytest.mark.django_db
def test_email_recipients_must_be_active_owner_or_admin():
    a, schedule = schedule_fixture("scope-owner-report")
    worker = User.objects.create_user(email="worker-report@example.test")
    m = Membership.objects.create(
        tenant=a["tenant"], user=worker, role=MembershipRole.SERVER,
    )
    schedule.recipients.add(m)
    assert eligible_recipients(schedule) == [a["user"].email]


@pytest.mark.django_db
def test_report_preferences_page_uses_authenticated_workspace():
    a, schedule = schedule_fixture("report-preferences-view")
    client = Client()
    assert client.login(username=a["user"].email, password="TestPass9!")
    sess = client.session
    sess[STAFF_SESSION_TENANT_KEY] = str(a["tenant"].pk)
    sess.save()
    page = client.get(reverse("staff-owner-report-settings"))
    assert page.status_code == 200, page.content[:400]
    assert b"Scheduled owner reports" in page.content

@pytest.mark.django_db
def test_owner_summary_includes_historical_cost_coverage_without_guessing():
    a, schedule = schedule_fixture("owner-profitability")
    period_day = datetime(2026, 10, 15).date()
    order = Order.objects.create(
        tenant=a["tenant"],
        outlet=a["outlet"],
        status=OrderStatus.CLOSED,
        subtotal=Decimal("100.00"),
        tax_total=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total=Decimal("100.00"),
        is_paid=True,
        created_by=a["user"],
    )
    OrderLine.objects.create(
        order=order,
        menu_item=a["item"],
        label=a["item"].name,
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
        cost_unit_snapshot=None,
        cost_basis_complete_snapshot=False,
        merchandise_category_snapshot=a["item"].category.name,
        merchandise_sku_snapshot=a["item"].sku or "",
        inventory_tracked_snapshot=True,
    )
    payment = Payment.objects.create(
        tenant=a["tenant"],
        order=order,
        amount=Decimal("100.00"),
        method="cash",
        idempotency_key="owner-profitability-payment",
        recorded_by=a["user"],
    )
    Payment.objects.filter(pk=payment.pk).update(
        created_at=datetime(2026, 10, 15, 12, 0, tzinfo=dt_timezone.utc),
    )

    summary = _summary_for_schedule(schedule, (period_day, period_day))
    profitability = summary["merchandise_profitability"]
    assert profitability["sale_revenue"] == Decimal("100.00")
    assert profitability["covered_net_revenue"] == Decimal("0.00")
    assert profitability["uncovered_net_revenue"] == Decimal("100.00")
    assert profitability["cost_coverage_percent"] == Decimal("0.0")
    assert profitability["profitability_complete"] is False
    assert profitability["known_net_cogs"] == Decimal("0.00")
    assert profitability["categories"][0]["category_name"] == a["item"].category.name

    csv_body = format_sales_summary_csv_from_summary(summary)
    assert "merchandise_profitability_metric" in csv_body
    assert "covered_net_revenue,0.00,UGX" in csv_body
    assert "uncovered_net_revenue,100.00,UGX" in csv_body
    assert "merchandise_category" in csv_body
    assert a["item"].category.name in csv_body
    assert "cost_coverage_percent,0.0,%" in csv_body
    assert "profitability_complete,no," in csv_body

