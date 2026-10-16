"""Focused, database-independent contracts for read-only loyalty reconciliation.

Run with: python manage.py test tests.test_loyalty_reconciliation
Database/RLS integration certification is tracked separately.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.customers.loyalty_reconciliation import (
    reconcile_loyalty_account,
    reconcile_loyalty_tenant,
)


class LoyaltyReconciliationContracts(SimpleTestCase):
    def setUp(self):
        self.tenant = SimpleNamespace(pk="tenant-a")
        self.customer = SimpleNamespace(pk="customer-a", tenant_id="tenant-a", merged_into_id=None)

    @patch("apps.customers.loyalty_reconciliation.LoyaltyLedgerEntry")
    def test_account_breakdown_does_not_mutate_ledger(self, model):
        model.objects.filter.return_value.values.return_value.annotate.return_value = [
            {"source_type": "sale", "net": 14},
            {"source_type": "refund", "net": -19},
            {"source_type": "adjustment", "net": 2},
        ]
        result = reconcile_loyalty_account(tenant=self.tenant, customer=self.customer)
        self.assertEqual(result["balance"], -3)
        self.assertEqual(result["points_to_recover"], 3)
        self.assertTrue(result["sale_reversals_exceed_earnings"])
        self.assertEqual(result["redemptions"], 0)
        model.objects.create.assert_not_called()
        model.objects.update.assert_not_called()

    @patch("apps.customers.loyalty_reconciliation.LoyaltyLedgerEntry")
    def test_zero_points_without_entries(self, model):
        model.objects.filter.return_value.values.return_value.annotate.return_value = []
        result = reconcile_loyalty_account(tenant=self.tenant, customer=self.customer)
        self.assertEqual(result["balance"], 0)
        self.assertEqual(result["points_to_recover"], 0)
        self.assertFalse(result["sale_reversals_exceed_earnings"])

    @patch("apps.customers.loyalty_reconciliation.LoyaltyLedgerEntry")
    def test_rejects_other_tenant_or_merged_customer_before_query(self, model):
        self.customer.tenant_id = "tenant-b"
        with self.assertRaises(ValueError):
            reconcile_loyalty_account(tenant=self.tenant, customer=self.customer)
        self.customer.tenant_id = "tenant-a"
        self.customer.merged_into_id = "successor"
        with self.assertRaises(ValueError):
            reconcile_loyalty_account(tenant=self.tenant, customer=self.customer)
        model.objects.filter.assert_not_called()

    @patch("apps.customers.loyalty_reconciliation.LoyaltyLedgerEntry")
    @patch("apps.customers.loyalty_reconciliation.Customer")
    def test_tenant_uses_grouped_sql_not_per_customer_iteration(self, customer_model, entry_model):
        active = customer_model.objects.filter.return_value.values_list.return_value
        entries = entry_model.objects.filter.return_value
        entries.values.return_value.annotate.return_value = [
            {"source_type": "sale", "net": 120},
            {"source_type": "refund", "net": -25},
        ]
        negative = MagicMock()
        negative.filter.return_value.count.return_value = 3
        entries.values.side_effect = [
            MagicMock(annotate=MagicMock(return_value=[
                {"source_type": "sale", "net": 120},
                {"source_type": "refund", "net": -25},
            ])),
            MagicMock(annotate=MagicMock(return_value=negative)),
        ]
        result = reconcile_loyalty_tenant(tenant=self.tenant)
        self.assertEqual(result["net_points_outstanding"], 95)
        self.assertEqual(result["accounts_with_negative_points"], 3)
        customer_model.objects.filter.assert_called_once_with(
            tenant=self.tenant, merged_into__isnull=True,
        )
        entry_model.objects.filter.assert_called_once_with(
            tenant=self.tenant, customer_id__in=active,
        )
        entries.iterator.assert_not_called()
        entry_model.objects.create.assert_not_called()
