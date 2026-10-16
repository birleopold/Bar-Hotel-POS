"""Direct batch receipt stock accounting, status safety and staff-facing query filters."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.batches import InventoryBatch
from apps.inventory.models import StockBalance, StockMovement, StockReason
from apps.inventory.services_batches import receive_tracked_batch, change_batch_hold
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class BatchReceiptTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Batch Receipt Test", slug="batch-receipt-journey")
        site = Site.objects.create(tenant=self.tenant, name="Main store")
        self.outlet = Outlet.objects.create(site=site, name="Groceries", outlet_type=OutletType.RETAIL)
        category = MenuCategory.objects.create(tenant=self.tenant, name="Dairy")
        self.item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Milk",
            unit_price=Decimal("4500"), track_inventory=True,
        )
        self.today = timezone.localdate()

    def receive(self, **changes):
        values = {
            "tenant": self.tenant, "outlet": self.outlet,
            "menu_item": self.item, "batch_code": "LOT-100",
            "quantity": Decimal("5.250"), "received_at": self.today,
            "expiry_date": self.today + timedelta(days=5),
            "user": None,
        }
        values.update(changes)
        return receive_tracked_batch(**values)

    def test_receive_posts_one_stock_movement_and_balance(self):
        batch, movement = self.receive()
        self.assertEqual(batch.remaining_quantity, Decimal("5.250"))
        self.assertFalse(batch.quarantined)
        self.assertEqual(movement.reason, StockReason.RECEIVE)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("5.250"),
        )
        with self.assertRaises(ValidationError):
            self.receive()
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(InventoryBatch.objects.count(), 1)

    def test_expired_delivery_is_quarantined_without_double_entry(self):
        batch, _ = self.receive(
            expiry_date=self.today - timedelta(days=2),
            received_at=self.today - timedelta(days=4),
        )
        self.assertTrue(batch.quarantined)
        with self.assertRaises(ValidationError):
            change_batch_hold(
                tenant_id=self.tenant.pk, batch_id=batch.pk,
                allowed_outlet_ids=[self.outlet.pk], quarantined=False, user=None,
            )

    def test_future_receipt_and_invalid_precision_rejected(self):
        with self.assertRaises(ValidationError):
            self.receive(received_at=self.today + timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.receive(quantity=Decimal("1.0005"))
        self.assertFalse(InventoryBatch.objects.exists())

    def test_scope_and_inventory_tracking_validation(self):
        other_tenant = Tenant.objects.create(name="Other Batch Tenant", slug="another-batch-tenant")
        with self.assertRaises(ValidationError):
            self.receive(tenant=other_tenant)
        self.item.track_inventory = False
        self.item.save(update_fields=["track_inventory"])
        with self.assertRaises(ValidationError):
            self.receive()
        self.assertFalse(InventoryBatch.objects.exists())
