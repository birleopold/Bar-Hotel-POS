"""Retail return numeric boundaries reject invalid requests before database writes."""
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.pos.services.returns import refund_retail_line


@pytest.mark.parametrize("qty,amount", [
    ("NaN", "100.00"),
    ("Infinity", "100.00"),
    ("-1", "100.00"),
    ("0", "100.00"),
    ("1.0001", "100.00"),
    ("1", "NaN"),
    ("1", "Infinity"),
    ("1", "-2"),
    ("1", "0"),
    ("1", "1.001"),
    ("not-a-number", "100.00"),
])
def test_invalid_retail_return_values_fail_before_touching_order(qty, amount):
    with pytest.raises(ValidationError):
        refund_retail_line(
            order=SimpleNamespace(pk=None),
            line=SimpleNamespace(pk=None),
            quantity=qty,
            amount=amount,
            reason="Invalid return test",
            restock=False,
            user=None,
            idempotency_key="return-invalid-test",
        )


@pytest.mark.django_db
def test_partial_return_cannot_refund_more_than_original_line_value():
    from decimal import Decimal
    from apps.pos.models import Order, OrderLine, OrderStatus
    from apps.pos.services.returns import refund_retail_line
    from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle
    from apps.tenants.models import OutletType

    setup = _seed_tenant_bundle(
        name="Refund Price Integrity", slug="refund-price-integrity",
        user_email="refund-price-integrity@example.test",
    )
    setup["outlet"].outlet_type = OutletType.SUPERMARKET
    setup["outlet"].save(update_fields=["outlet_type"])
    order = Order.objects.create(
        tenant=setup["tenant"], outlet=setup["outlet"],
        created_by=setup["user"], status=OrderStatus.CLOSED,
        is_paid=True, total=Decimal("110.00"), subtotal=Decimal("100.00"),
        tax_total=Decimal("10.00"),
    )
    line = OrderLine.objects.create(
        order=order, menu_item=setup["item"], label="Rice",
        quantity=Decimal("2"), unit_price=Decimal("60.00"),
        line_discount_amount=Decimal("20.00"),
        line_total=Decimal("100.00"), tax_amount=Decimal("10.00"),
    )
    with pytest.raises(ValidationError, match="exceeds the original amount"):
        refund_retail_line(
            order=order, line=line, quantity=Decimal("1"),
            amount=Decimal("55.01"), reason="Test",
            restock=False, user=setup["user"], idempotency_key="overprice-line",
        )
