"""Executive reporting reuses scoped sales data; no parallel ledger."""
import pytest
from decimal import Decimal
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.pos.models import Order, OrderStatus, Payment, PosShift, Refund, Workstation
from apps.staff.report_csv import format_sales_summary_csv
from apps.staff.sales_summary import build_sales_summary
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_owner_executive_sales_report_has_bounded_period_and_empty_state():
    fixture = _seed_tenant_bundle(
        name="Executive report example", slug="executive-report-example",
        user_email="executive-report-owner@test.local",
    )
    client = Client()
    assert client.login(username=fixture["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(fixture["tenant"].pk)
    session.save()
    path = reverse("staff-management")
    response = client.get(path, {"view": "reports"})
    assert response.status_code == 200
    assert response.context["executive_sales"]["gross_sales"] == 0
    assert b"Executive sales overview" in response.content
    assert b"No payments recorded" in response.content

    invalid = client.get(path, {"view": "reports", "date_from": "2025-01-01", "date_to": "2025-03-01"})
    assert invalid.status_code == 200
    assert "executive_error" in invalid.context
    assert "executive_sales" not in invalid.context

    member = Membership.objects.get(tenant=fixture["tenant"], user=fixture["user"])
    member.role = MembershipRole.SERVER
    member.save(update_fields=["role"])
    denied = client.get(path, {"view": "reports"})
    assert denied.status_code == 403


@pytest.mark.django_db
def test_sales_summary_preserves_register_hour_and_legacy_attribution():
    fixture = _seed_tenant_bundle(
        name="Sales dimensions example",
        slug="sales-dimensions-example",
        user_email="sales-dimensions-owner@test.local",
    )
    tenant = fixture["tenant"]
    outlet = fixture["outlet"]
    user = fixture["user"]
    workstation = Workstation.objects.create(
        tenant=tenant,
        outlet=outlet,
        name="Front register",
        code="front-register",
    )
    shift = PosShift.objects.create(
        tenant=tenant,
        outlet=outlet,
        workstation=workstation,
        status="closed",
        opened_by=user,
        closed_by=user,
        expected_cash=Decimal("100.00"),
        counted_cash=Decimal("100.00"),
        closed_at=timezone.now(),
    )

    order = Order.objects.create(
        tenant=tenant,
        outlet=outlet,
        status=OrderStatus.CLOSED,
        is_paid=True,
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        created_by=user,
    )
    payment = Payment.objects.create(
        tenant=tenant,
        order=order,
        shift=shift,
        amount=Decimal("100.00"),
        method="cash",
        idempotency_key="register-dimension-payment",
        recorded_by=user,
    )
    Refund.objects.create(
        tenant=tenant,
        order=order,
        payment=payment,
        shift=shift,
        amount=Decimal("20.00"),
        reason="Returned",
        idempotency_key="register-dimension-refund",
        recorded_by=user,
    )

    legacy_order = Order.objects.create(
        tenant=tenant,
        outlet=outlet,
        status=OrderStatus.CLOSED,
        is_paid=True,
        subtotal=Decimal("40.00"),
        total=Decimal("40.00"),
        created_by=user,
    )
    Payment.objects.create(
        tenant=tenant,
        order=legacy_order,
        amount=Decimal("40.00"),
        method="card",
        idempotency_key="legacy-dimension-payment",
        recorded_by=user,
    )

    today = timezone.localdate()
    summary = build_sales_summary(
        tenant.pk,
        today,
        today,
        allowed_outlet_ids=[outlet.pk],
    )
    register = next(
        row for row in summary["by_register"]
        if row["register_code"] == "front-register"
    )
    assert register["gross_sales"] == Decimal("100.00")
    assert register["refunds_total"] == Decimal("20.00")
    assert register["net_sales"] == Decimal("80.00")
    legacy = next(
        row for row in summary["by_register"]
        if row["register_key"] == "legacy"
    )
    assert legacy["gross_sales"] == Decimal("40.00")
    assert legacy["net_sales"] == Decimal("40.00")

    hour = timezone.localtime(payment.created_at).hour
    hourly = summary["hourly_sales"][hour]
    assert hourly["payments_count"] >= 1
    assert hourly["refunds_count"] >= 1
    assert hourly["gross_sales"] >= Decimal("100.00")
    assert hourly["refunds_total"] >= Decimal("20.00")

    csv_body = format_sales_summary_csv(
        tenant.pk,
        today,
        today,
        outlet.pk,
        allowed_outlet_ids=[outlet.pk],
    )
    assert "register,register_code,payments_count,refunds_count" in csv_body
    assert "Front register,front-register" in csv_body
    assert "Unattributed / legacy" in csv_body
    assert "hour,hour_label,payments_count,refunds_count" in csv_body
