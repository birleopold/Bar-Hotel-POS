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
