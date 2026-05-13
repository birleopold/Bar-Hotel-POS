from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole, UserInvite
from apps.catalog.models import MenuCategory, MenuItem, Promotion
from apps.inventory.models import StockCountSession, StockCountStatus, StockMovement
from apps.pos.models import (
    KdsLineStatus,
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    PaymentMethod,
    Refund,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings

User = get_user_model()


def _seed_tenant_bundle(*, name: str, slug: str, user_email: str) -> dict:
    tenant = Tenant.objects.create(name=name, slug=slug)
    TenantSettings.objects.get_or_create(tenant=tenant)
    site = Site.objects.create(tenant=tenant, name=f"{name} Site")
    outlet = Outlet.objects.create(site=site, name=f"{name} Outlet", outlet_type=OutletType.BAR)
    category = MenuCategory.objects.create(tenant=tenant, name=f"{name} Cat")
    item = MenuItem.objects.create(
        tenant=tenant,
        category=category,
        name=f"{name} Item",
        unit_price=Decimal("5.00"),
        track_inventory=True,
    )
    user = User.objects.create_user(email=user_email, password="TestPass9!")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
    return {
        "tenant": tenant,
        "site": site,
        "outlet": outlet,
        "category": category,
        "item": item,
        "user": user,
    }


def _create_open_order(*, tenant, outlet, total: str = "10.00") -> Order:
    amount = Decimal(total)
    return Order.objects.create(
        tenant=tenant,
        outlet=outlet,
        status=OrderStatus.OPEN,
        subtotal=amount,
        tax_total=Decimal("0.00"),
        total=amount,
        discount_amount=Decimal("0.00"),
        currency="USD",
    )


@pytest.mark.django_db
def test_cross_tenant_invite_create_forbidden_and_no_side_effect(api_client):
    a = _seed_tenant_bundle(name="Tenant A", slug="tenant-a-inv", user_email="ta-inv@test.local")
    b = _seed_tenant_bundle(name="Tenant B", slug="tenant-b-inv", user_email="tb-inv@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    before = UserInvite.objects.filter(tenant=b["tenant"]).count()
    r = api_client.post(
        "/api/v1/invites/",
        {"email": "new-user@test.local"},
        format="json",
        HTTP_X_TENANT_ID=str(b["tenant"].id),
    )
    assert r.status_code == 403
    body = r.json()
    assert body["error"]["code"] == "tenant_forbidden"
    after = UserInvite.objects.filter(tenant=b["tenant"]).count()
    assert after == before


@pytest.mark.django_db
def test_cross_tenant_order_payment_cannot_target_foreign_order(api_client):
    a = _seed_tenant_bundle(name="Tenant A", slug="tenant-a-pay", user_email="ta-pay@test.local")
    b = _seed_tenant_bundle(name="Tenant B", slug="tenant-b-pay", user_email="tb-pay@test.local")
    foreign_order = _create_open_order(tenant=b["tenant"], outlet=b["outlet"], total="12.00")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    before = Payment.objects.filter(order=foreign_order).count()
    r = api_client.post(
        f"/api/v1/orders/{foreign_order.id}/payments/",
        {"amount": "5.00", "method": PaymentMethod.CASH},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        HTTP_IDEMPOTENCY_KEY="cross-tenant-payment-1",
    )
    assert r.status_code == 404
    after = Payment.objects.filter(order=foreign_order).count()
    assert after == before


@pytest.mark.django_db
def test_cross_tenant_stock_movement_rejects_foreign_resources(api_client):
    a = _seed_tenant_bundle(name="Tenant A", slug="tenant-a-stock", user_email="ta-stock@test.local")
    b = _seed_tenant_bundle(name="Tenant B", slug="tenant-b-stock", user_email="tb-stock@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    before = StockMovement.objects.filter(tenant=b["tenant"]).count()
    r = api_client.post(
        "/api/v1/stock/movements/",
        {
            "outlet": str(b["outlet"].id),
            "menu_item": str(b["item"].id),
            "quantity_change": "2.000",
            "reason": "receive",
            "note": "cross-tenant attempt",
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 400
    after = StockMovement.objects.filter(tenant=b["tenant"]).count()
    assert after == before


@pytest.mark.django_db
@pytest.mark.parametrize("url_path", ["void-line", "apply-promotion", "kds-line"])
def test_cross_tenant_order_update_actions_are_blocked(api_client, url_path):
    safe = url_path.replace("-", "_")
    a = _seed_tenant_bundle(name="OTA", slug=f"ota-iso-{safe}", user_email=f"ota-{safe}@test.local")
    b = _seed_tenant_bundle(name="OTB", slug=f"otb-iso-{safe}", user_email=f"otb-{safe}@test.local")
    order = _create_open_order(tenant=b["tenant"], outlet=b["outlet"], total="10.00")
    line = OrderLine.objects.create(
        order=order,
        menu_item=b["item"],
        label=b["item"].name,
        quantity=Decimal("1"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
        kds_station="bar",
    )
    promo = Promotion.objects.create(
        tenant=b["tenant"],
        name="Cross promo",
        discount_percent=Decimal("10"),
        starts_at=timezone.now() - timedelta(days=1),
    )
    promo.outlets.add(b["outlet"])
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    if url_path == "void-line":
        body = {"line_id": str(line.id), "reason": "test"}
        extra = {}
    elif url_path == "apply-promotion":
        body = {"promotion_id": str(promo.id)}
        extra = {}
    else:
        body = {"line_id": str(line.id), "kds_status": KdsLineStatus.READY}
        extra = {}
    st_before = line.kds_status
    void_before = line.is_voided
    r = api_client.post(
        f"/api/v1/orders/{order.id}/{url_path}/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        **extra,
    )
    assert r.status_code == 404
    line.refresh_from_db()
    assert line.kds_status == st_before
    assert line.is_voided == void_before
    order.refresh_from_db()
    assert order.applied_promotion_id is None


@pytest.mark.django_db
@pytest.mark.parametrize("action_path", ["complete", "cancel"])
def test_cross_tenant_stock_count_update_actions_are_blocked(api_client, action_path):
    a = _seed_tenant_bundle(name="SCA", slug=f"sca-iso-{action_path}", user_email=f"sca-{action_path}@test.local")
    b = _seed_tenant_bundle(name="SCB", slug=f"scb-iso-{action_path}", user_email=f"scb-{action_path}@test.local")
    session = StockCountSession.objects.create(
        tenant=b["tenant"],
        outlet=b["outlet"],
        status=StockCountStatus.DRAFT,
        created_by=b["user"],
    )
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    url = f"/api/v1/stock/count-sessions/{session.id}/{action_path}/"
    if action_path == "complete":
        r = api_client.post(
            url,
            {"lines": [{"menu_item": str(b["item"].id), "counted_quantity": "1.000"}]},
            format="json",
            HTTP_X_TENANT_ID=str(a["tenant"].id),
        )
    else:
        r = api_client.post(url, {}, format="json", HTTP_X_TENANT_ID=str(a["tenant"].id))
    assert r.status_code == 404
    session.refresh_from_db()
    assert session.status == StockCountStatus.DRAFT
    assert StockMovement.objects.filter(tenant=b["tenant"]).count() == 0


@pytest.mark.django_db
def test_offline_sync_replay_does_not_duplicate_payment(api_client):
    a = _seed_tenant_bundle(name="OffPay", slug="off-pay", user_email="offpay@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    order = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10.00")
    body = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "device-pay-replay",
        "operation_type": "order_payment",
        "payload": {
            "order_id": str(order.id),
            "amount": "10.00",
            "method": PaymentMethod.CASH,
            "idempotency_key": "off-sync-pay-1",
        },
    }
    r1 = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r1.status_code == 201, r1.content
    r2 = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r2.status_code == 200, r2.content
    assert r2.json()["replay"] is True
    assert Payment.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_payment_idempotency_replay_then_conflict_across_orders(api_client):
    a = _seed_tenant_bundle(name="PayIdem", slug="pay-idem", user_email="payidem@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    o1 = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10.00")
    o2 = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10.00")
    r1 = api_client.post(
        f"/api/v1/orders/{o1.id}/payments/",
        {"amount": "10.00", "method": PaymentMethod.CASH},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        HTTP_IDEMPOTENCY_KEY="shared-pay-key-1",
    )
    assert r1.status_code == 201, r1.content
    r2 = api_client.post(
        f"/api/v1/orders/{o2.id}/payments/",
        {"amount": "10.00", "method": PaymentMethod.CASH},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        HTTP_IDEMPOTENCY_KEY="shared-pay-key-1",
    )
    assert r2.status_code == 400
    assert Payment.objects.filter(idempotency_key="shared-pay-key-1").count() == 1


@pytest.mark.django_db
def test_refund_idempotency_replay_then_conflict_across_orders(api_client):
    a = _seed_tenant_bundle(name="RefIdem", slug="ref-idem", user_email="refidem@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    o1 = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10.00")
    o2 = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10.00")
    for oid in (o1.id, o2.id):
        pr = api_client.post(
            f"/api/v1/orders/{oid}/payments/",
            {"amount": "10.00", "method": PaymentMethod.CASH},
            format="json",
            HTTP_X_TENANT_ID=str(a["tenant"].id),
            HTTP_IDEMPOTENCY_KEY=f"pay-{oid}-1",
        )
        assert pr.status_code == 201, pr.content
    r1 = api_client.post(
        f"/api/v1/orders/{o1.id}/refunds/",
        {"amount": "2.00", "reason": "a"},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        HTTP_IDEMPOTENCY_KEY="shared-refund-key-1",
    )
    assert r1.status_code == 201, r1.content
    r2 = api_client.post(
        f"/api/v1/orders/{o2.id}/refunds/",
        {"amount": "2.00", "reason": "b"},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
        HTTP_IDEMPOTENCY_KEY="shared-refund-key-1",
    )
    assert r2.status_code == 400
    assert Refund.objects.filter(idempotency_key="shared-refund-key-1").count() == 1
