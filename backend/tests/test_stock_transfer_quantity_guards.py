"""F3: rejected transfer quantities cannot affect either branch's ledger."""
from decimal import Decimal
import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import execute_stock_transfer
from apps.tenants.models import Outlet, OutletType
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "0", "1.0001", "invalid"])
def test_transfer_rejects_invalid_quantity_before_moving_stock(bad):
    data = _seed_tenant_bundle(
        name="Transfer Validation", slug="transfer-validation",
        user_email="transfer-validation@example.test",
    )
    source = data["outlet"]
    other = Outlet.objects.create(
        site=data["site"], name="Receiving", outlet_type=OutletType.RETAIL,
    )
    stock = StockBalance.objects.create(
        tenant=data["tenant"], outlet=source, menu_item=data["item"],
        quantity=Decimal("15"),
    )
    membership = Membership.objects.get(user=data["user"], tenant=data["tenant"])
    with pytest.raises(ValidationError):
        execute_stock_transfer(
            tenant_id=data["tenant"].pk, membership=membership,
            from_outlet=source, to_outlet=other,
            menu_item=data["item"], quantity=bad, user=data["user"],
        )
    stock.refresh_from_db()
    assert stock.quantity == Decimal("15")
    assert not StockMovement.objects.filter(tenant=data["tenant"]).exists()


def test_transfer_screen_discloses_immediate_stock_posting_and_has_submission_guard():
    from pathlib import Path
    template = (
        Path(__file__).resolve().parents[1]
        / "apps" / "staff" / "templates" / "staff" / "inventory"
        / "transfer_form.html"
    ).read_text(encoding="utf-8")
    assert "Only the sender\'s stock decreases now" in template
    assert "recipient confirms quantities before stock is added at the receiving outlet" in template
    assert "data-transfer-form" in template
    assert "inFlight" in template
    assert 'aria-live="polite"' in template
