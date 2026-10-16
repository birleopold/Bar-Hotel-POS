"""A malformed grocery stocktake must never partially post a ledger."""
from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.inventory.models import StockBalance, StockCountLine, StockCountSession, StockMovement
from apps.inventory.services import complete_stock_count_session
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [
    "NaN", "Infinity", "-1", "1.0001", "1000000000000",
])
def test_invalid_count_does_not_change_stock_or_create_movements(invalid):
    setup = _seed_tenant_bundle(
        name="Grocery Count Safety", slug="grocery-count-invalid",
        user_email="grocery-count-invalid@example.test",
    )
    item = setup["item"]
    count = StockCountSession.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"], created_by=setup["user"],
    )
    balance = StockBalance.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"],
        menu_item=item, quantity=Decimal("10"),
    )
    membership = Membership.objects.get(tenant=setup["tenant"], user=setup["user"])
    with pytest.raises(ValidationError, match="Invalid count"):
        complete_stock_count_session(
            session=count, user=setup["user"], membership=membership,
            resolved_lines=[{"menu_item": item, "counted_quantity": invalid}],
        )
    balance.refresh_from_db()
    assert balance.quantity == Decimal("10")
    assert not StockMovement.objects.filter(tenant=setup["tenant"]).exists()
    assert not StockCountLine.objects.filter(session=count).exists()


@pytest.mark.django_db
def test_duplicate_count_item_fails_before_any_stock_change():
    setup = _seed_tenant_bundle(
        name="Grocery Duplicate Count", slug="grocery-duplicate-count",
        user_email="grocery-duplicate-count@example.test",
    )
    item = setup["item"]
    count = StockCountSession.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"], created_by=setup["user"],
    )
    balance = StockBalance.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"],
        menu_item=item, quantity=Decimal("10"),
    )
    membership = Membership.objects.get(tenant=setup["tenant"], user=setup["user"])
    with pytest.raises(ValidationError, match="Duplicate count"):
        complete_stock_count_session(
            session=count, user=setup["user"], membership=membership,
            resolved_lines=[
                {"menu_item": item, "counted_quantity": Decimal("8")},
                {"menu_item": item, "counted_quantity": Decimal("7")},
            ],
        )
    balance.refresh_from_db()
    assert balance.quantity == Decimal("10")
    assert not StockMovement.objects.filter(tenant=setup["tenant"]).exists()
    assert not StockCountLine.objects.filter(session=count).exists()
