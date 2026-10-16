"""Scheduled owner reports: local dates, opt-in delivery, recipient scope and replay."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.api.owner_reports import (
    deliver_owner_report, eligible_recipients, scheduled_period,
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
@override_settings(DEFAULT_FROM_EMAIL="reports@example.test")
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
@override_settings(DEFAULT_FROM_EMAIL="reports@example.test")
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
