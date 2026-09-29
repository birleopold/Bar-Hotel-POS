from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole, User
from apps.finance.models import CashbookEntry, FinanceCategoryKind, FinancePostingSource
from apps.lodging.models import (
    Folio,
    FolioLine,
    FolioStatus,
    MaintenanceStatus,
    Reservation,
    ReservationStatus,
    Room,
    RoomMaintenanceRequest,
    RoomType,
)
from apps.lodging.services import check_out_reservation, folio_totals, record_folio_payment
from apps.pos.models import Order
from apps.pos.services import record_order_payment
from apps.staff.middleware import STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, Site, Tenant, TenantSettings


@pytest.mark.django_db
def test_paid_discounted_pos_sale_on_folio_does_not_create_second_balance():
    tenant = Tenant.objects.create(name="POS Folio", slug="pos-folio")
    site = Site.objects.create(tenant=tenant, name="Main")
    outlet = Outlet.objects.create(site=site, name="Shop", outlet_type="supermarket")
    user = User.objects.create_user(email="pos-folio@example.invalid", password="TestPass9!")
    folio = Folio.objects.create(tenant=tenant, site=site, guest_name="Guest", currency="UGX")
    order = Order.objects.create(
        tenant=tenant, outlet=outlet, folio=folio, created_by=user, currency="UGX",
        subtotal=Decimal("100"), tax_total=Decimal("10"), discount_amount=Decimal("20"), total=Decimal("90"),
    )
    record_order_payment(order=order, user=user, amount=Decimal("90"), method="cash", idempotency_key="paid-pos-folio")
    assert folio_totals(folio) == (Decimal("0"), Decimal("0"), Decimal("0"))
    assert list(folio.lines.values_list("amount", "tax_amount")) == [
        (Decimal("80"), Decimal("10")), (Decimal("-90"), Decimal("0")),
    ]
    assert CashbookEntry.objects.count() == 1


@pytest.mark.django_db
def test_closed_folio_rejects_pos_payment_without_finance_side_effect():
    tenant = Tenant.objects.create(name="Closed POS Folio", slug="closed-pos-folio")
    site = Site.objects.create(tenant=tenant, name="Main")
    outlet = Outlet.objects.create(site=site, name="Shop", outlet_type="supermarket")
    user = User.objects.create_user(email="closed-folio@example.invalid", password="TestPass9!")
    folio = Folio.objects.create(tenant=tenant, site=site, guest_name="Guest", currency="UGX", status=FolioStatus.CLOSED)
    order = Order.objects.create(tenant=tenant, outlet=outlet, folio=folio, created_by=user, currency="UGX", subtotal=Decimal("10"), total=Decimal("10"))
    with pytest.raises(ValidationError, match="Folio must be open"):
        record_order_payment(order=order, user=user, amount=Decimal("10"), method="cash", idempotency_key="closed-folio-pay")
    order.refresh_from_db()
    assert not order.is_paid
    assert not order.payments.exists()
    assert not folio.lines.exists()
    assert not CashbookEntry.objects.exists()


@pytest.mark.django_db
def test_unpaid_folio_blocks_checkout_then_payment_closes_stay_and_posts_income():
    tenant = Tenant.objects.create(name="Settlement Hotel", slug="settlement-hotel")
    TenantSettings.objects.create(tenant=tenant, default_currency="UGX")
    site = Site.objects.create(tenant=tenant, name="Main property")
    user = User.objects.create_user(email="frontdesk@example.invalid", password="TestPass9!")
    room_type = RoomType.objects.create(tenant=tenant, site=site, name="Standard")
    room = Room.objects.create(room_type=room_type, name="101")
    reservation = Reservation.objects.create(
        tenant=tenant,
        site=site,
        room=room,
        guest_name="Paying Guest",
        check_in=date(2026, 9, 21),
        check_out=date(2026, 9, 22),
        status=ReservationStatus.CHECKED_IN,
    )
    folio = Folio.objects.create(
        tenant=tenant,
        site=site,
        reservation=reservation,
        guest_name=reservation.guest_name,
        currency="UGX",
    )
    FolioLine.objects.create(
        tenant=tenant,
        folio=folio,
        description="Room night",
        amount=Decimal("100000"),
        tax_amount=Decimal("18000"),
    )

    with pytest.raises(ValidationError, match="Settle the guest folio"):
        check_out_reservation(reservation=reservation, user=user)

    payment = record_folio_payment(
        folio=folio,
        amount=Decimal("118000"),
        method="mobile_money",
        reference="MOMO-123",
        idempotency_key="folio-pay-1",
        user=user,
    )
    repeated = record_folio_payment(
        folio=folio,
        amount=Decimal("118000"),
        method="mobile_money",
        reference="MOMO-123",
        idempotency_key="folio-pay-1",
        user=user,
    )
    assert repeated.pk == payment.pk
    with pytest.raises(ValidationError, match="different folio payment"):
        record_folio_payment(folio=folio, amount=Decimal("1"), method="mobile_money", reference="MOMO-123", idempotency_key="folio-pay-1", user=user)
    other_folio = Folio.objects.create(tenant=tenant, site=site, guest_name="Other Guest", currency="UGX")
    with pytest.raises(ValidationError, match="different folio payment"):
        record_folio_payment(folio=other_folio, amount=Decimal("118000"), method="mobile_money", reference="MOMO-123", idempotency_key="folio-pay-1", user=user)
    assert folio_totals(folio) == (Decimal("118000"), Decimal("118000"), Decimal("0"))
    assert CashbookEntry.objects.get(posting_link__source_type=FinancePostingSource.FOLIO_PAYMENT).category.kind == FinanceCategoryKind.INCOME

    check_out_reservation(reservation=reservation, user=user)
    reservation.refresh_from_db()
    folio.refresh_from_db()
    room.refresh_from_db()
    assert reservation.status == ReservationStatus.CHECKED_OUT
    assert folio.status == FolioStatus.CLOSED
    assert room.status == "dirty"


@pytest.mark.django_db
def test_api_cannot_close_unsettled_folio_and_can_record_payment():
    tenant = Tenant.objects.create(name="API Settlement", slug="api-settlement")
    TenantSettings.objects.create(tenant=tenant, default_currency="UGX")
    site = Site.objects.create(tenant=tenant, name="Main")
    user = User.objects.create_user(email="api-frontdesk@example.invalid", password="TestPass9!")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.FRONT_DESK)
    folio = Folio.objects.create(tenant=tenant, site=site, guest_name="Guest", currency="UGX")
    FolioLine.objects.create(tenant=tenant, folio=folio, description="Charge", amount=Decimal("50000"))
    client = APIClient()
    client.force_login(user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.id)}

    blocked = client.patch(
        f"/api/v1/lodging/folios/{folio.pk}/",
        {"status": "closed"},
        format="json",
        **headers,
    )
    assert blocked.status_code == 400
    paid = client.post(
        f"/api/v1/lodging/folios/{folio.pk}/payments/",
        {"amount": "50000.00", "method": "cash", "reference": "RCPT-1", "idempotency_key": "api-pay-1"},
        format="json",
        **headers,
    )
    assert paid.status_code == 201
    closed = client.patch(
        f"/api/v1/lodging/folios/{folio.pk}/",
        {"status": "closed"},
        format="json",
        **headers,
    )
    assert closed.status_code == 200
    assert closed.data["status"] == "closed"
    assert closed.data["balance_due"] == "0.00"


@pytest.mark.django_db
def test_dashboard_property_pulse_uses_scoped_live_lodging_counts():
    tenant = Tenant.objects.create(name="Pulse Hotel", slug="pulse-hotel")
    TenantSettings.objects.create(tenant=tenant, default_currency="UGX", business_lines=["lodging"])
    site = Site.objects.create(tenant=tenant, name="Entebbe Property")
    user = User.objects.create_user(email="pulse-owner@example.invalid", password="TestPass9!")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
    room_type = RoomType.objects.create(tenant=tenant, site=site, name="Deluxe")
    ready = Room.objects.create(room_type=room_type, name="201", status="clean")
    Room.objects.create(room_type=room_type, name="202", status="dirty")
    Reservation.objects.create(
        tenant=tenant,
        site=site,
        room=ready,
        guest_name="Today Guest",
        check_in=date.today(),
        check_out=date.today() + timedelta(days=1),
        status=ReservationStatus.CONFIRMED,
    )
    client = APIClient()
    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
    session[STAFF_SESSION_SITE_KEY] = str(site.id)
    session.save()
    response = client.get("/staff/")
    assert response.status_code == 200
    assert "Property pulse" in response.content.decode()
    assert "Today at Entebbe Property" in response.content.decode()
    assert "Today Guest" in response.content.decode()
    assert response.context["staff_dashboard_lodging_snapshot"].dirty_rooms == 1


@pytest.mark.django_db
def test_room_maintenance_work_order_can_be_created_assigned_and_resolved():
    tenant = Tenant.objects.create(name="Maintenance Hotel", slug="maintenance-hotel")
    TenantSettings.objects.create(tenant=tenant, business_lines=["lodging"])
    site = Site.objects.create(tenant=tenant, name="Main Property")
    owner = User.objects.create_user(email="maintenance-owner@example.invalid", password="TestPass9!")
    technician = User.objects.create_user(email="technician@example.invalid", password="TestPass9!")
    Membership.objects.create(user=owner, tenant=tenant, role=MembershipRole.OWNER)
    Membership.objects.create(user=technician, tenant=tenant, role=MembershipRole.SITE_MANAGER)
    room_type = RoomType.objects.create(tenant=tenant, site=site, name="Standard")
    room = Room.objects.create(room_type=room_type, name="104")
    client = APIClient()
    client.force_login(owner)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
    session[STAFF_SESSION_SITE_KEY] = str(site.id)
    session.save()

    created = client.post(
        "/staff/lodging/maintenance/",
        {
            "action": "create",
            "room": str(room.id),
            "title": "Air conditioner not cooling",
            "description": "Guest reported warm air.",
            "priority": "urgent",
            "assigned_to": str(technician.id),
            "expected_by": date.today().isoformat(),
        },
    )
    assert created.status_code == 302
    item = RoomMaintenanceRequest.objects.get(tenant=tenant)
    assert item.assigned_to == technician
    assert item.status == MaintenanceStatus.OPEN

    resolved = client.post(
        "/staff/lodging/maintenance/",
        {"action": "status", "request_id": str(item.id), "status": MaintenanceStatus.RESOLVED},
    )
    assert resolved.status_code == 302
    item.refresh_from_db()
    assert item.status == MaintenanceStatus.RESOLVED
    assert item.resolved_at is not None
