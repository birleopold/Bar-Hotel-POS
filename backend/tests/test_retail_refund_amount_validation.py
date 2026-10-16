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
