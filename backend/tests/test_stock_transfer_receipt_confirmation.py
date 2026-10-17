"""An internal transfer posts stock only once, regardless of receiving outcome."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.inventory.models import StockBalance, StockMovement, StockTransferReceipt
from apps.inventory.services import execute_stock_transfer, verify_stock_transfer_receipt
from apps.tenants.models import Outlet, OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def make_transfer(slug):
    setup = _seed_tenant_bundle(
        name=slug, slug=slug, user_email=f"{slug}@example.test",
    )
    receiver = get_user_model().objects.create_user(
        email=f"receiver-{slug}@example.test", password="TestPass999!",
    )
    receiver_membership = Membership.objects.create(
        tenant=setup["tenant"], user=receiver, role=MembershipRole.STOREKEEPER,
    )
    receiver_membership.sites.add(setup["site"])
    destination = Outlet.objects.create(
        site=setup["site"], name="Receiving", outlet_type=OutletType.BAR,
    )
    receiver_membership.outlets.add(destination)
    manager = Membership.objects.get(user=setup["user"], tenant=setup["tenant"])
    origin = StockBalance.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"],
        menu_item=setup["item"], quantity=Decimal("15"),
    )
    transfer_id, outgoing, incoming = execute_stock_transfer(
        tenant_id=setup["tenant"].id,
        membership=manager, from_outlet=setup["outlet"], to_outlet=destination,
        menu_item=setup["item"], quantity=Decimal("4"),
        user=setup["user"],
    )
    transfer = StockTransferReceipt.objects.get(transfer_batch=transfer_id)
    return setup, destination, receiver, receiver_membership, origin, transfer


@pytest.mark.django_db
def test_received_quantity_match_does_not_post_stock_twice():
    setup, destination, receiver, membership, origin, transfer = make_transfer("transfer-match")
    assert transfer.status == "awaiting"
    assert transfer.dispatched_quantity == Decimal("4")
    assert StockBalance.objects.get(outlet=destination, menu_item=setup["item"]).quantity == 4
    assert StockMovement.objects.filter(transfer_batch=transfer.transfer_batch).count() == 2
    verify_stock_transfer_receipt(
        receipt=transfer, membership=membership, user=receiver, received_quantity="4",
    )
    transfer.refresh_from_db()
    assert transfer.status == "matched"
    assert transfer.received_quantity == Decimal("4")
    assert StockBalance.objects.get(outlet=destination, menu_item=setup["item"]).quantity == 4
    assert StockMovement.objects.filter(transfer_batch=transfer.transfer_batch).count() == 2
    with pytest.raises(ValidationError, match="already"):
        verify_stock_transfer_receipt(
            receipt=transfer, membership=membership, user=receiver, received_quantity="4",
        )


@pytest.mark.django_db
def test_difference_needs_reason_and_records_dispute_without_changing_ledgers():
    setup, destination, receiver, membership, origin, transfer = make_transfer("transfer-short")
    with pytest.raises(ValidationError, match="Explain"):
        verify_stock_transfer_receipt(
            receipt=transfer, membership=membership, user=receiver, received_quantity="2",
        )
    verify_stock_transfer_receipt(
        receipt=transfer, membership=membership, user=receiver,
        received_quantity="2", note="Only two pieces arrived at receiving desk.",
    )
    transfer.refresh_from_db()
    origin.refresh_from_db()
    assert transfer.status == "disputed"
    assert origin.quantity == Decimal("11")
    assert StockBalance.objects.get(outlet=destination, menu_item=setup["item"]).quantity == 4
    assert StockMovement.objects.filter(transfer_batch=transfer.transfer_batch).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1.0001", "abc"])
def test_invalid_received_amount_keeps_check_open(value):
    setup, destination, receiver, membership, origin, transfer = make_transfer(
        "transfer-bad-" + value.lower().replace(".", "-"),
    )
    with pytest.raises(ValidationError):
        verify_stock_transfer_receipt(
            receipt=transfer, membership=membership, user=receiver, received_quantity=value,
        )
    transfer.refresh_from_db()
    assert transfer.status == "awaiting"
    assert transfer.checked_by_id is None


@pytest.mark.django_db
def test_dispatcher_cannot_sign_own_receipt_and_other_tenant_cannot_verify():
    setup, destination, receiver, membership, origin, transfer = make_transfer("transfer-scope")
    manager = Membership.objects.get(tenant=setup["tenant"], user=setup["user"])
    with pytest.raises(ValidationError, match="different"):
        verify_stock_transfer_receipt(
            receipt=transfer, membership=manager,
            user=setup["user"], received_quantity="4",
        )
    other = _seed_tenant_bundle(
        name="Unrelated Tenant", slug="unrelated-transfer-tenant",
        user_email="unrelated-transfer@example.test",
    )
    other_manager = Membership.objects.get(tenant=other["tenant"], user=other["user"])
    with pytest.raises(ValidationError, match="destination"):
        verify_stock_transfer_receipt(
            receipt=transfer, membership=other_manager,
            user=other["user"], received_quantity="4",
        )
    transfer.refresh_from_db()
    assert transfer.status == "awaiting"
