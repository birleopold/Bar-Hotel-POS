from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.inventory.fefo import InsufficientBatchStock, plan_fefo_allocation


class FefoPlannerTests(SimpleTestCase):
    def test_consumes_nearest_unexpired_first_then_unknown_expiry(self):
        rows = [
            {"id": "unknown", "quantity": 4, "expiry_date": None},
            {"id": "late", "quantity": 6, "expiry_date": date(2026, 12, 1)},
            {"id": "early", "quantity": 2, "expiry_date": date(2026, 10, 17)},
            {"id": "expired", "quantity": 100, "expiry_date": date(2026, 10, 1)},
        ]
        self.assertEqual(
            plan_fefo_allocation(rows, Decimal("9"), as_of=date(2026, 10, 15)),
            [("early", Decimal("2")), ("late", Decimal("6")), ("unknown", Decimal("1"))],
        )

    def test_insufficient_eligible_quantity_fails_without_mutating_inputs(self):
        rows = [{"id": "expired", "quantity": 12, "expiry_date": date(2026, 9, 1)}]
        with self.assertRaises(InsufficientBatchStock):
            plan_fefo_allocation(rows, 1, as_of=date(2026, 10, 15))
        self.assertEqual(rows[0]["quantity"], 12)

    def test_rejects_duplicate_batch_ids(self):
        rows = [{"id": "x", "quantity": 2}, {"id": "x", "quantity": 3}]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            plan_fefo_allocation(rows, 1)

    def test_rejects_negative_or_nonfinite_numbers(self):
        with self.assertRaises(ValueError):
            plan_fefo_allocation([], 0)
        with self.assertRaises(ValueError):
            plan_fefo_allocation([{"id": "x", "quantity": "-1"}], 1)
        with self.assertRaises(ValueError):
            plan_fefo_allocation([{"id": "x", "quantity": "NaN"}], 1)
