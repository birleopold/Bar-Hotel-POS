"""Staged transfer dispatch and physical receiving must be non-duplicating."""
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from apps.inventory.batches import InventoryBatch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.inventory.models import StockBalance, StockMovement, StockTransferReceipt
from apps.inventory.services import (
    execute_stock_transfer, verify_stock_transfer_receipt, resolve_stock_transfer_discrepancy,
)
from apps.tenants.models import Outlet, OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def start(slug, batches=False):
    data = _seed_tenant_bundle(name=slug, slug=slug, user_email=slug + "@example.test")
    dest = Outlet.objects.create(site=data["site"], name="Receiving", outlet_type=OutletType.RETAIL)
    StockBalance.objects.create(tenant=data["tenant"], outlet=data["outlet"],
                                menu_item=data["item"], quantity=Decimal("10"))
    if batches:
        InventoryBatch.objects.create(
            tenant=data["tenant"], outlet=data["outlet"], menu_item=data["item"],
            batch_code="LOT-42", received_at=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=90),
            received_quantity=Decimal("10"), remaining_quantity=Decimal("10"),
        )
    sender = Membership.objects.get(tenant=data["tenant"], user=data["user"])
    receive_user = get_user_model().objects.create_user(email="recv-" + slug + "@example.test", password="Password123!")
    receive_role = Membership.objects.create(tenant=data["tenant"], user=receive_user, role=MembershipRole.STOREKEEPER)
    receive_role.sites.add(data["site"])
    receive_role.outlets.add(dest)
    manager_user = get_user_model().objects.create_user(email="mgr-" + slug + "@example.test", password="Password123!")
    manager = Membership.objects.create(tenant=data["tenant"], user=manager_user, role=MembershipRole.SITE_MANAGER)
    manager.sites.add(data["site"])
    manager.outlets.add(dest, data["outlet"])
    ref, out, arriving = execute_stock_transfer(
        tenant_id=data["tenant"].id, membership=sender,
        from_outlet=data["outlet"], to_outlet=dest, menu_item=data["item"],
        quantity=Decimal("4"), user=data["user"], staged=True,
    )
    return data, dest, receive_user, receive_role, manager_user, manager, StockTransferReceipt.objects.get(transfer_batch=ref)


@pytest.mark.django_db
def test_dispatch_only_moves_source_then_receipt_posts_exactly_once():
    data, dest, user, role, reviewer, manager, receipt = start("staged-full")
    assert receipt.mode == "staged"
    assert receipt.status == "in_transit"
    assert receipt.outstanding_quantity == 4
    assert StockBalance.objects.get(outlet=data["outlet"], menu_item=data["item"]).quantity == 6
    assert not StockBalance.objects.filter(outlet=dest, menu_item=data["item"]).exists()
    assert StockMovement.objects.filter(transfer_batch=receipt.transfer_batch).count() == 1
    verify_stock_transfer_receipt(receipt=receipt, membership=role, user=user, received_quantity="4")
    receipt.refresh_from_db()
    assert receipt.status == "matched" and receipt.outstanding_quantity == 0
    assert StockBalance.objects.get(outlet=dest, menu_item=data["item"]).quantity == 4
    assert StockMovement.objects.filter(transfer_batch=receipt.transfer_batch).count() == 2
    with pytest.raises(ValidationError, match="already"):
        verify_stock_transfer_receipt(receipt=receipt, membership=role, user=user, received_quantity="4")


@pytest.mark.django_db
@pytest.mark.parametrize("action,source_qty,dest_qty,loss", [
    ("receive_missing", 6, 4, 0),
    ("return_source", 8, 2, 0),
    ("write_off", 6, 2, 2),
])
def test_shortage_reconciliation_is_a_single_manager_action(action, source_qty, dest_qty, loss):
    data, dest, user, role, reviewer, manager, receipt = start("staged-" + action)
    verify_stock_transfer_receipt(
        receipt=receipt, membership=role, user=user,
        received_quantity="2", note="Only two units arrived",
    )
    receipt.refresh_from_db()
    assert receipt.status == "disputed" and receipt.outstanding_quantity == 2
    resolve_stock_transfer_discrepancy(
        receipt=receipt, membership=manager, user=reviewer, action=action,
        note="Checked the source and destination with the stock team.",
    )
    receipt.refresh_from_db()
    assert receipt.status == "resolved" and receipt.outstanding_quantity == 0
    assert receipt.written_off_quantity == loss
    assert StockBalance.objects.get(outlet=data["outlet"], menu_item=data["item"]).quantity == source_qty
    assert StockBalance.objects.get(outlet=dest, menu_item=data["item"]).quantity == dest_qty
    with pytest.raises(ValidationError, match="Only an open"):
        resolve_stock_transfer_discrepancy(
            receipt=receipt, membership=manager, user=reviewer,
            action=action, note="Duplicate should not post",
        )


@pytest.mark.django_db
def test_overage_is_reported_but_never_invented_as_saleable_stock():
    data, dest, user, role, reviewer, manager, receipt = start("staged-surplus")
    with pytest.raises(ValidationError, match="Explain"):
        verify_stock_transfer_receipt(
            receipt=receipt, membership=role, user=user, received_quantity="6",
        )
    verify_stock_transfer_receipt(
        receipt=receipt, membership=role, user=user,
        received_quantity="6", note="Found two unexpected units",
    )
    receipt.refresh_from_db()
    assert receipt.status == "disputed" and receipt.posted_quantity == 4
    assert StockBalance.objects.get(outlet=dest, menu_item=data["item"]).quantity == 4
    with pytest.raises(ValidationError):
        resolve_stock_transfer_discrepancy(
            receipt=receipt, membership=manager, user=reviewer,
            action="write_off", note="Should not accept a wrong result.",
        )
    resolve_stock_transfer_discrepancy(
        receipt=receipt, membership=manager, user=reviewer,
        action="acknowledge_overage", note="Quarantined extra units pending count.",
    )
    receipt.refresh_from_db()
    assert receipt.status == "resolved"
    assert StockBalance.objects.get(outlet=dest, menu_item=data["item"]).quantity == 4


@pytest.mark.django_db
def test_unrelated_tenant_cannot_resolve_shortage():
    data, dest, user, role, reviewer, manager, receipt = start("staged-tenant")
    verify_stock_transfer_receipt(
        receipt=receipt, membership=role, user=user,
        received_quantity="0", note="Nothing arrived at the destination",
    )
    other = _seed_tenant_bundle(
        name="Independent Owner", slug="staged-other",
        user_email="staged-other@example.test",
    )
    different = Membership.objects.get(tenant=other["tenant"], user=other["user"])
    with pytest.raises(ValidationError, match="manager"):
        resolve_stock_transfer_discrepancy(
            receipt=receipt, membership=different, user=other["user"],
            action="write_off", note="Cross tenant must fail.",
        )
    receipt.refresh_from_db()
    assert receipt.status == "disputed"



@pytest.mark.django_db
def test_staged_receipt_preserves_fefo_batch_identity():
    data, dest, user, role, reviewer, manager, receipt = start("staged-batch", batches=True)
    assert InventoryBatch.objects.get(outlet=data["outlet"], batch_code="LOT-42").remaining_quantity == 6
    verify_stock_transfer_receipt(
        receipt=receipt, membership=role, user=user, received_quantity="2",
        note="Two units physically arrived in this lot.",
    )
    received = InventoryBatch.objects.get(outlet=dest, batch_code="LOT-42")
    assert received.remaining_quantity == 2
    resolve_stock_transfer_discrepancy(
        receipt=receipt, membership=manager, user=reviewer,
        action="return_source", note="The remaining two units were physically returned to sender.",
    )
    receipt.refresh_from_db()
    assert receipt.outstanding_quantity == 0
    assert InventoryBatch.objects.get(outlet=data["outlet"], batch_code="LOT-42").remaining_quantity == 8
    assert InventoryBatch.objects.get(outlet=dest, batch_code="LOT-42").remaining_quantity == 2


@pytest.mark.django_db
def test_conflicting_destination_batch_rolls_back_receipt():
    data, dest, user, role, reviewer, manager, receipt = start("staged-batch-conflict", batches=True)
    InventoryBatch.objects.create(
        tenant=data["tenant"], outlet=dest, menu_item=data["item"],
        batch_code="LOT-42", received_at=timezone.localdate(),
        expiry_date=timezone.localdate() + timedelta(days=1),
        received_quantity=Decimal("0"), remaining_quantity=Decimal("0"),
    )
    with pytest.raises(ValidationError, match="incompatible"):
        verify_stock_transfer_receipt(
            receipt=receipt, membership=role, user=user, received_quantity="4",
        )
    receipt.refresh_from_db()
    assert receipt.status == "in_transit" and receipt.outstanding_quantity == 4
    assert not StockBalance.objects.filter(outlet=dest, menu_item=data["item"]).exists()
    assert StockMovement.objects.filter(transfer_batch=receipt.transfer_batch).count() == 1
