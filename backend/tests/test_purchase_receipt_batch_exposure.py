"""Purchasing delivery and supplier balance regression coverage."""
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, SimpleTestCase

from apps.catalog.models import MenuCategory, MenuItem
from apps.purchasing.models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, SupplierPayment,
    SupplierPaymentMethod, PurchaseOrderStatus,
)
from apps.purchasing.serializers import ReceiveLineSerializer
from apps.purchasing.services_exposure import purchase_order_exposure
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class BatchReceiptValidationTests(SimpleTestCase):
    def test_receiving_batch_code_expiry_and_quantity(self):
        data = {
            "line_id": str(uuid4()), "quantity": "2.500",
            "batch_code": "BB-2026", "expiry_date": "2030-06-30",
        }
        ser = ReceiveLineSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertEqual(ser.validated_data["batch_code"], "BB-2026")

    def test_expiry_without_batch_is_not_accepted(self):
        ser = ReceiveLineSerializer(data={
            "line_id": str(uuid4()), "quantity": "1", "expiry_date": "2030-06-30",
        })
        self.assertFalse(ser.is_valid())
        self.assertIn("batch_code", ser.errors)


class SupplierPayablesScopeTests(TestCase):
    def test_received_goods_payments_and_outlet_scope(self):
        tenant = Tenant.objects.create(name="Supplier Scope", slug="supplier-scope-test")
        site = Site.objects.create(tenant=tenant, name="Warehouse")
        outlet = Outlet.objects.create(site=site, name="Main", outlet_type=OutletType.RETAIL)
        other = Outlet.objects.create(site=site, name="Other", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=tenant, name="Purchasing")
        product = MenuItem.objects.create(
            tenant=tenant, category=category, name="Tea",
            unit_price=Decimal("5000"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=tenant, name="Supplier A")
        po = PurchaseOrder.objects.create(
            tenant=tenant, supplier=supplier, outlet=outlet,
            status=PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=product, quantity_ordered=Decimal("4"),
            quantity_received=Decimal("2"), unit_cost=Decimal("1000"),
        )
        SupplierPayment.objects.create(
            tenant=tenant, purchase_order=po, amount=Decimal("500"),
            method=SupplierPaymentMethod.CASH, idempotency_key="payment-1",
        )
        result = purchase_order_exposure(tenant=tenant, outlet_ids=[outlet.id])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["received_value"], Decimal("2000"))
        self.assertEqual(result[0]["paid_amount"], Decimal("500"))
        self.assertEqual(result[0]["unpaid_received_value"], Decimal("1500"))
        self.assertFalse(result[0]["missing_cost_data"])
        self.assertEqual(purchase_order_exposure(tenant=tenant, outlet_ids=[other.id]), [])
