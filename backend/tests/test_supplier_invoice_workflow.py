"""Supplier invoice behaviour: document recording never invents a payment."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import MenuCategory, MenuItem
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, SupplierInvoice,
    PurchaseOrderStatus, SupplierPayment,
)
from apps.purchasing.services import record_supplier_invoice
from apps.purchasing.services_exposure import purchase_order_exposure
from apps.tenants.models import Site, Tenant, Outlet, OutletType


class SupplierInvoiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Invoice Tenant", slug="invoice-tenant-tests")
        site = Site.objects.create(tenant=self.tenant, name="Warehouse")
        self.outlet = Outlet.objects.create(site=site, name="Main", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Consumables")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Coffee",
            unit_price=Decimal("5000"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=self.tenant, name="Vendor")
        self.po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=self.po, menu_item=item, quantity_ordered=Decimal("5"),
            quantity_received=Decimal("2"), unit_cost=Decimal("1000"),
        )

    def record(self, *, reference="INV-001", amount=Decimal("1500")):
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            return record_supplier_invoice(
                po=self.po, reference=reference,
                invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 30),
                amount=amount, note="", user=None, membership=object(),
            )

    def test_document_is_idempotent_and_does_not_pay_supplier(self):
        first, replay = self.record()
        second, replay2 = self.record()
        self.assertFalse(replay)
        self.assertTrue(replay2)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SupplierInvoice.objects.filter(purchase_order=self.po).count(), 1)
        self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
        rows = purchase_order_exposure(tenant=self.tenant, outlet_ids=[self.outlet.pk])
        self.assertEqual(rows[0]["invoiced_value"], Decimal("1500"))
        self.assertEqual(rows[0]["unbilled_received_value"], Decimal("500"))
        self.assertEqual(rows[0]["earliest_invoice_due_date"], date(2026, 10, 30))

    def test_prevent_duplicate_reference_with_changed_amount(self):
        self.record()
        with self.assertRaises(ValidationError):
            self.record(amount=Decimal("1750"))

    def test_total_invoices_cannot_exceed_received_goods(self):
        self.record()
        with self.assertRaises(ValidationError):
            self.record(reference="INV-002", amount=Decimal("501"))

    def test_permission_check_rejects_unassigned_outlet(self):
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=False):
            with self.assertRaises(ValidationError):
                record_supplier_invoice(
                    po=self.po, reference="INV-OTHER",
                    invoice_date=date(2026, 10, 1), due_date=date(2026, 11, 1),
                    amount=Decimal("100"), user=None, membership=object(),
                )
        self.assertFalse(SupplierInvoice.objects.filter(purchase_order=self.po).exists())

    def test_recorded_invoice_caps_payment_but_not_received_balance(self):
        """A partial invoice cannot authorize paying the uninvoiced receipt remainder."""
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import record_supplier_payment

        self.record(amount=Decimal("1500"))
        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as post_expense:
                with self.assertRaisesRegex(ValidationError, "unpaid recorded supplier invoices"):
                    record_supplier_payment(
                        po=self.po, amount=Decimal("1500.01"),
                        method=SupplierPaymentMethod.CASH, reference="paid-overshoot",
                        idempotency_key="payment-overshoot", user=None, membership=object(),
                    )
                self.assertFalse(SupplierPayment.objects.filter(purchase_order=self.po).exists())
                post_expense.assert_not_called()
                payment, replay = record_supplier_payment(
                    po=self.po, amount=Decimal("1500.00"),
                    method=SupplierPaymentMethod.CASH, reference="paid-invoice",
                    idempotency_key="payment-invoice", user=None, membership=object(),
                )
                self.assertFalse(replay)
                self.assertEqual(payment.amount, Decimal("1500.00"))
                post_expense.assert_called_once()

    def test_receipt_backed_payment_without_invoices_remains_available(self):
        from apps.purchasing.models import SupplierPaymentMethod
        from apps.purchasing.services import record_supplier_payment

        with patch("apps.purchasing.services.outlet_belongs_to_membership", return_value=True):
            with patch("apps.purchasing.services.post_supplier_payment_expense") as post_expense:
                payment, replay = record_supplier_payment(
                    po=self.po, amount=Decimal("2000.00"),
                    method=SupplierPaymentMethod.BANK, reference="legacy-receipt",
                    idempotency_key="legacy-no-invoice", user=None, membership=object(),
                )
        self.assertFalse(replay)
        self.assertEqual(payment.amount, Decimal("2000.00"))
        post_expense.assert_called_once()
