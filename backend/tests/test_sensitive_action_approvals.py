import uuid
from decimal import Decimal

import pytest

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import SensitiveActionApproval
from apps.staff.services.approvals import (
    SensitiveApprovalError,
    authorize_sensitive_action,
    sensitive_action_approvers,
)
from apps.staff.terminal import set_member_pin
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


@pytest.fixture
def approval_setup(db):
    tenant = Tenant.objects.create(name="Approval Store", slug="approval-store")
    TenantSettings.objects.create(tenant=tenant, business_lines=["supermarket"])
    site = Site.objects.create(tenant=tenant, name="Main")
    outlet = Outlet.objects.create(
        site=site,
        name="Till 1",
        outlet_type=OutletType.SUPERMARKET,
    )
    cashier_user = User.objects.create_user(
        email="approval-cashier@example.test",
        password="StrongPass!2026",
    )
    cashier = Membership.objects.create(
        tenant=tenant,
        user=cashier_user,
        role=MembershipRole.SERVER,
    )
    cashier.sites.add(site)
    cashier.outlets.add(outlet)

    manager_user = User.objects.create_user(
        email="approval-manager@example.test",
        password="StrongPass!2026",
    )
    manager = Membership.objects.create(
        tenant=tenant,
        user=manager_user,
        role=MembershipRole.OUTLET_MANAGER,
    )
    manager.sites.add(site)
    manager.outlets.add(outlet)
    set_member_pin(manager, "573951")

    return {
        "tenant": tenant,
        "site": site,
        "outlet": outlet,
        "cashier": cashier,
        "manager": manager,
    }


@pytest.mark.django_db
def test_sensitive_approval_is_pin_bound_exact_and_idempotent(approval_setup):
    setup = approval_setup
    request_key = str(uuid.uuid4())
    intent = {
        "amount": str(Decimal("12000.00")),
        "reason": "Customer refund",
        "payment_id": "",
    }
    approval = authorize_sensitive_action(
        requester=setup["cashier"],
        approver_id=setup["manager"].pk,
        approver_pin="573951",
        action="refund",
        entity_type="order",
        entity_id="order-123",
        request_key=request_key,
        intent_payload=intent,
        outlet_id=setup["outlet"].pk,
    )
    assert approval.used_at is not None
    assert approval.expires_at > approval.created_at
    assert approval.approver_id == setup["manager"].pk
    assert approval.intent_payload == intent

    replay = authorize_sensitive_action(
        requester=setup["cashier"],
        approver_id=setup["manager"].pk,
        approver_pin="573951",
        action="refund",
        entity_type="order",
        entity_id="order-123",
        request_key=request_key,
        intent_payload=intent,
        outlet_id=setup["outlet"].pk,
    )
    assert replay.pk == approval.pk
    assert SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="refund", request_key=request_key,
    ).count() == 1

    with pytest.raises(SensitiveApprovalError, match="different transaction details"):
        authorize_sensitive_action(
            requester=setup["cashier"],
            approver_id=setup["manager"].pk,
            approver_pin="573951",
            action="refund",
            entity_type="order",
            entity_id="order-123",
            request_key=request_key,
            intent_payload={**intent, "amount": "12001.00"},
            outlet_id=setup["outlet"].pk,
        )


@pytest.mark.django_db
def test_sensitive_approval_rejects_bad_pin_and_non_manager(approval_setup):
    setup = approval_setup
    with pytest.raises(SensitiveApprovalError, match="approval failed"):
        authorize_sensitive_action(
            requester=setup["cashier"],
            approver_id=setup["manager"].pk,
            approver_pin="000000",
            action="refund",
            entity_type="order",
            entity_id="order-456",
            request_key=str(uuid.uuid4()),
            intent_payload={"amount": "1000.00"},
            outlet_id=setup["outlet"].pk,
        )
    assert not SensitiveActionApproval.objects.filter(entity_id="order-456").exists()

    other_user = User.objects.create_user(
        email="approval-other-cashier@example.test",
        password="StrongPass!2026",
    )
    other = Membership.objects.create(
        tenant=setup["tenant"],
        user=other_user,
        role=MembershipRole.SERVER,
    )
    other.sites.add(setup["site"])
    other.outlets.add(setup["outlet"])
    set_member_pin(other, "864209")
    with pytest.raises(SensitiveApprovalError, match="approval failed"):
        authorize_sensitive_action(
            requester=setup["cashier"],
            approver_id=other.pk,
            approver_pin="864209",
            action="refund",
            entity_type="order",
            entity_id="order-789",
            request_key=str(uuid.uuid4()),
            intent_payload={"amount": "1000.00"},
            outlet_id=setup["outlet"].pk,
        )


@pytest.mark.django_db
def test_sensitive_approval_rejects_self_approval(approval_setup):
    setup = approval_setup
    request_key = str(uuid.uuid4())
    with pytest.raises(SensitiveApprovalError, match="different authorized manager"):
        authorize_sensitive_action(
            requester=setup["manager"],
            approver_id=setup["manager"].pk,
            approver_pin="573951",
            action="discount",
            entity_type="order",
            entity_id="self-approved-order",
            request_key=request_key,
            intent_payload={"line_id": "line-1", "discount_amount": "10.00"},
            outlet_id=setup["outlet"].pk,
        )
    assert not SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="discount", request_key=request_key,
    ).exists()
    assert setup["manager"] not in sensitive_action_approvers(
        requester=setup["manager"],
        action="discount",
        outlet_id=setup["outlet"].pk,
    )


@pytest.mark.django_db
def test_sensitive_approvers_are_pin_enabled_and_outlet_scoped(approval_setup):
    setup = approval_setup
    second_site = Site.objects.create(tenant=setup["tenant"], name="Other")
    second_outlet = Outlet.objects.create(
        site=second_site,
        name="Till 2",
        outlet_type=OutletType.SUPERMARKET,
    )
    remote_user = User.objects.create_user(
        email="approval-remote-manager@example.test",
        password="StrongPass!2026",
    )
    remote = Membership.objects.create(
        tenant=setup["tenant"],
        user=remote_user,
        role=MembershipRole.OUTLET_MANAGER,
    )
    remote.sites.add(second_site)
    remote.outlets.add(second_outlet)
    set_member_pin(remote, "246813")

    approvers = sensitive_action_approvers(
        requester=setup["cashier"],
        action="refund",
        outlet_id=setup["outlet"].pk,
    )
    assert setup["manager"] in approvers
    assert remote not in approvers


@pytest.mark.django_db
def test_retail_cashier_refund_requires_and_records_manager_approval(client, approval_setup):
    from apps.pos.models import Order, OrderStatus, Payment, PaymentMethod, Refund
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from django.urls import reverse

    setup = approval_setup
    order = Order.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        created_by=setup["cashier"].user,
        status=OrderStatus.CLOSED,
        is_paid=True,
        subtotal=Decimal("12000.00"),
        total=Decimal("12000.00"),
    )
    Payment.objects.create(
        tenant=setup["tenant"],
        order=order,
        amount=Decimal("12000.00"),
        method=PaymentMethod.CASH,
        idempotency_key="approval-payment-1",
        recorded_by=setup["cashier"].user,
    )

    client.force_login(setup["cashier"].user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()

    url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
    page = client.get(url)
    assert page.status_code == 200
    assert b"Supervisor PIN" in page.content
    assert setup["manager"].user.email.encode() in page.content

    bad_key = str(uuid.uuid4())
    denied = client.post(url, {
        "action": "record_refund",
        "refund_request_key": bad_key,
        "amount": "12000.00",
        "reason": "Customer changed mind",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "000000",
    })
    assert denied.status_code == 302
    assert not Refund.objects.filter(order=order).exists()
    assert not SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="refund", request_key=bad_key,
    ).exists()

    good_key = str(uuid.uuid4())
    approved = client.post(url, {
        "action": "record_refund",
        "refund_request_key": good_key,
        "amount": "12000.00",
        "reason": "Customer changed mind",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "573951",
    })
    assert approved.status_code == 302
    refund = Refund.objects.get(order=order)
    assert refund.amount == Decimal("12000.00")
    approval = SensitiveActionApproval.objects.get(
        tenant=setup["tenant"], action="refund", request_key=good_key,
    )
    assert approval.used_at is not None
    assert approval.requester_id == setup["cashier"].pk
    assert approval.approver_id == setup["manager"].pk
    assert approval.intent_payload["amount"] == "12000.00"


@pytest.mark.django_db
def test_retail_line_discount_requires_exact_manager_approval_and_replay_is_safe(client, approval_setup):
    from apps.audit.models import AuditEvent
    from apps.pos.models import Order, OrderLine, OrderStatus
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from django.urls import reverse

    setup = approval_setup
    order = Order.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        created_by=setup["cashier"].user,
        status=OrderStatus.OPEN,
        is_paid=False,
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
    )
    line = OrderLine.objects.create(
        order=order,
        label="Discount item",
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    client.force_login(setup["cashier"].user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()
    url = reverse("staff-order-detail", kwargs={"order_id": order.pk})

    page = client.get(url)
    assert page.status_code == 200
    assert b"Line discount" in page.content
    assert b"Supervisor PIN" in page.content
    assert b'discount_request_key' in page.content

    denied_key = str(uuid.uuid4())
    denied = client.post(url, {
        "action": "line_discount",
        "discount_request_key": denied_key,
        "line_id": str(line.pk),
        "discount_amount": "10.00",
        "discount_percent": "",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "000000",
    })
    assert denied.status_code == 302
    line.refresh_from_db()
    assert line.line_discount_amount == Decimal("0")
    assert not SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="discount", request_key=denied_key,
    ).exists()

    request_key = str(uuid.uuid4())
    payload = {
        "action": "line_discount",
        "discount_request_key": request_key,
        "line_id": str(line.pk),
        "discount_amount": "10.00",
        "discount_percent": "",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "573951",
    }
    approved = client.post(url, payload)
    assert approved.status_code == 302
    line.refresh_from_db()
    assert line.line_discount_amount == Decimal("10.00")
    approval = SensitiveActionApproval.objects.get(
        tenant=setup["tenant"], action="discount", request_key=request_key,
    )
    assert approval.used_at is not None
    assert approval.intent_payload["line_id"] == str(line.pk)
    assert approval.intent_payload["discount_amount"] == "10.00"
    assert AuditEvent.objects.filter(
        tenant=setup["tenant"],
        action="order.line_discount_applied",
        entity_id=str(line.pk),
    ).count() == 1

    replay = client.post(url, payload)
    assert replay.status_code == 302
    assert AuditEvent.objects.filter(
        tenant=setup["tenant"],
        action="order.line_discount_applied",
        entity_id=str(line.pk),
    ).count() == 1


@pytest.mark.django_db
def test_retail_line_discount_ajax_keeps_exact_manager_approval_and_rotates_request_key(client, approval_setup):
    from apps.pos.models import Order, OrderLine, OrderStatus
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from django.urls import reverse

    setup = approval_setup
    order = Order.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        created_by=setup["cashier"].user,
        status=OrderStatus.OPEN,
        is_paid=False,
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
    )
    line = OrderLine.objects.create(
        order=order,
        label="Async discount item",
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    client.force_login(setup["cashier"].user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()
    url = reverse("staff-order-detail", kwargs={"order_id": order.pk})

    denied = client.post(
        url,
        {
            "action": "line_discount",
            "discount_request_key": str(uuid.uuid4()),
            "line_id": str(line.pk),
            "discount_amount": "10.00",
            "discount_percent": "",
            "approver_id": str(setup["manager"].pk),
            "approver_pin": "000000",
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert denied.status_code == 422
    assert denied.json()["ok"] is False

    request_key = str(uuid.uuid4())
    approved = client.post(
        url,
        {
            "action": "line_discount",
            "discount_request_key": request_key,
            "line_id": str(line.pk),
            "discount_amount": "10.00",
            "discount_percent": "",
            "approver_id": str(setup["manager"].pk),
            "approver_pin": "573951",
        },
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["ok"] is True
    assert body["message"] == "Manager-approved line discount saved."
    assert body["next_request_key"] != request_key
    uuid.UUID(body["next_request_key"])
    line.refresh_from_db()
    assert line.line_discount_amount == Decimal("10.00")


@pytest.mark.django_db
def test_retail_cashier_full_basket_void_requires_different_manager_approval(client, approval_setup):
    from apps.pos.models import Order, OrderLine, OrderStatus
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from django.urls import reverse

    setup = approval_setup
    order = Order.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        created_by=setup["cashier"].user,
        status=OrderStatus.OPEN,
        is_paid=False,
        subtotal=Decimal("7500.00"),
        total=Decimal("7500.00"),
    )
    OrderLine.objects.create(
        order=order,
        label="Basket item",
        quantity=Decimal("1"),
        unit_price=Decimal("7500.00"),
        line_total=Decimal("7500.00"),
    )
    client.force_login(setup["cashier"].user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()
    url = reverse("staff-order-detail", kwargs={"order_id": order.pk})

    page = client.get(url)
    assert page.status_code == 200
    assert b"Manager approve &amp; void" in page.content
    assert b"Supervisor PIN" in page.content
    assert setup["manager"].user.email.encode() in page.content

    bad_key = str(uuid.uuid4())
    denied = client.post(url, {
        "action": "void_order",
        "void_request_key": bad_key,
        "reason": "Customer cancelled basket",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "000000",
    })
    assert denied.status_code == 302
    order.refresh_from_db()
    assert order.status == OrderStatus.OPEN
    assert not SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="void", request_key=bad_key,
    ).exists()

    request_key = str(uuid.uuid4())
    approved = client.post(url, {
        "action": "void_order",
        "void_request_key": request_key,
        "reason": "Customer cancelled basket",
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "573951",
    })
    assert approved.status_code == 302
    assert approved["Location"] == reverse("staff-retail-pos-entry")
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED
    approval = SensitiveActionApproval.objects.get(
        tenant=setup["tenant"], action="void", request_key=request_key,
    )
    assert approval.requester_id == setup["cashier"].pk
    assert approval.approver_id == setup["manager"].pk
    assert approval.intent_payload["reason"] == "Customer cancelled basket"
    assert approval.intent_payload["active_line_count"] == 1


@pytest.mark.django_db
def test_cash_payout_requires_different_manager_and_records_one_exact_approval(client, approval_setup):
    from django.core import signing
    from django.urls import reverse
    from apps.pos.models import CashDrawerMovement, PosShift, PosShiftStatus, Workstation
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from apps.staff.terminal import set_member_pin
    from apps.staff.workstations import COOKIE as WORKSTATION_COOKIE, SALT as WORKSTATION_SALT

    setup = approval_setup
    approver_user = User.objects.create_user(
        email="approval-second-manager@example.test",
        password="StrongPass!2026",
    )
    approver = Membership.objects.create(
        tenant=setup["tenant"],
        user=approver_user,
        role=MembershipRole.OUTLET_MANAGER,
    )
    approver.sites.add(setup["site"])
    approver.outlets.add(setup["outlet"])
    set_member_pin(approver, "864209")

    station = Workstation.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        name="Approval Till",
        code="approval-till",
        requires_pairing=False,
    )
    shift = PosShift.objects.create(
        tenant=setup["tenant"],
        outlet=setup["outlet"],
        workstation=station,
        status=PosShiftStatus.OPEN,
        opened_by=setup["manager"].user,
        opening_cash=Decimal("50000.00"),
    )

    client.force_login(setup["manager"].user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()
    client.cookies[WORKSTATION_COOKIE] = signing.dumps(
        str(station.pk), salt=WORKSTATION_SALT,
    )
    url = reverse("staff-pos-shifts")

    page = client.get(url)
    assert page.status_code == 200
    assert b"Supervisor PIN" in page.content
    assert approver.user.email.encode() in page.content

    bad_key = str(uuid.uuid4())
    denied = client.post(url, {
        "action": "cash_movement",
        "shift_id": str(shift.pk),
        "idempotency_key": bad_key,
        "direction": "payout",
        "amount": "10000.00",
        "reason": "Emergency petty cash",
        "approver_id": str(approver.pk),
        "approver_pin": "000000",
    })
    assert denied.status_code == 302
    assert not CashDrawerMovement.objects.filter(shift=shift).exists()
    assert not SensitiveActionApproval.objects.filter(
        tenant=setup["tenant"], action="withdrawal", request_key=bad_key,
    ).exists()

    good_key = str(uuid.uuid4())
    approved = client.post(url, {
        "action": "cash_movement",
        "shift_id": str(shift.pk),
        "idempotency_key": good_key,
        "direction": "payout",
        "amount": "10000.00",
        "reason": "Emergency petty cash",
        "approver_id": str(approver.pk),
        "approver_pin": "864209",
    })
    assert approved.status_code == 302
    movement = CashDrawerMovement.objects.get(shift=shift, idempotency_key=good_key)
    assert movement.direction == "payout"
    assert movement.amount == Decimal("10000.00")
    approval = SensitiveActionApproval.objects.get(
        tenant=setup["tenant"], action="withdrawal", request_key=good_key,
    )
    assert approval.requester_id == setup["manager"].pk
    assert approval.approver_id == approver.pk
    assert approval.intent_payload["amount"] == "10000.00"
    assert approval.intent_payload["reason"] == "Emergency petty cash"


@pytest.mark.django_db
def test_storekeeper_stock_write_off_requires_manager_approval_and_replay_is_safe(client, approval_setup):
    from apps.catalog.models import MenuCategory, MenuItem
    from apps.inventory.models import StockBalance, StockMovement, StockReason
    from apps.inventory.services import apply_manual_stock_change
    from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
    from django.urls import reverse

    setup = approval_setup
    category = MenuCategory.objects.create(tenant=setup["tenant"], name="Write-off test")
    item = MenuItem.objects.create(
        tenant=setup["tenant"], category=category, name="Damaged tins",
        sku="DAMAGED-TINS", unit_price=Decimal("1000.00"),
        track_inventory=True, is_active=True,
    )
    apply_manual_stock_change(
        tenant_id=setup["tenant"].pk, outlet=setup["outlet"], menu_item=item,
        quantity_change=Decimal("10.000"), reason=StockReason.RECEIVE,
        user=setup["manager"].user, note="Opening test stock",
    )
    worker_user = User.objects.create_user(
        email="approval-storekeeper@example.test", password="StrongPass!2026",
    )
    worker = Membership.objects.create(
        tenant=setup["tenant"], user=worker_user, role=MembershipRole.STOREKEEPER,
    )
    worker.sites.add(setup["site"])
    worker.outlets.add(setup["outlet"])
    client.force_login(worker_user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(setup["tenant"].pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(setup["outlet"].pk)
    session.save()
    url = reverse("staff-inventory-movement-create")

    page = client.get(url)
    assert page.status_code == 200
    assert b"Supervisor PIN" in page.content
    assert setup["manager"].user.email.encode() in page.content

    request_key = str(uuid.uuid4())
    payload = {
        "outlet": str(setup["outlet"].pk),
        "menu_item": str(item.pk),
        "reason": StockReason.WASTE.value,
        "quantity": "2.000",
        "note": "Two tins crushed",
        "approval_request_key": request_key,
        "approver_id": str(setup["manager"].pk),
        "approver_pin": "573951",
    }
    approved = client.post(url, payload)
    assert approved.status_code == 302
    balance = StockBalance.objects.get(outlet=setup["outlet"], menu_item=item)
    assert balance.quantity == Decimal("8.000")
    approval = SensitiveActionApproval.objects.get(
        tenant=setup["tenant"], action="stock_write_off", request_key=request_key,
    )
    assert approval.requester_id == worker.pk
    assert approval.approver_id == setup["manager"].pk
    assert approval.intent_payload["quantity_change"] == "-2.000"
    assert StockMovement.objects.filter(
        outlet=setup["outlet"], menu_item=item, reason=StockReason.WASTE,
    ).count() == 1

    replay = client.post(url, payload)
    assert replay.status_code == 302
    balance.refresh_from_db()
    assert balance.quantity == Decimal("8.000")
    assert StockMovement.objects.filter(
        outlet=setup["outlet"], menu_item=item, reason=StockReason.WASTE,
    ).count() == 1
