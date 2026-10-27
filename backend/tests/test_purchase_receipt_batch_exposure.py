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


class GroceryReceivingServicePreflightTests(TestCase):
    def test_invalid_delivery_cannot_post_receipt_or_stock(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.inventory.models import StockBalance, StockMovement
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import receive_purchase_order_goods
        from rest_framework.exceptions import ValidationError

        tenant = Tenant.objects.create(name="Grocery Receiving", slug="grocery-receiving-preflight")
        site = Site.objects.create(tenant=tenant, name="Store")
        outlet = Outlet.objects.create(site=site, name="Receiving", outlet_type=OutletType.SUPERMARKET)
        category = MenuCategory.objects.create(tenant=tenant, name="Food")
        item = MenuItem.objects.create(
            tenant=tenant, category=category, name="Rice",
            unit_price=Decimal("3200"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=tenant, name="Mill")
        po = PurchaseOrder.objects.create(
            tenant=tenant, supplier=supplier, outlet=outlet, status=PurchaseOrderStatus.SENT,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item, quantity_ordered=Decimal("100"),
            unit_cost=Decimal("2000"),
        )
        user = User.objects.create_user(email="grocery-receiver@example.test", password="TestPass9!")
        membership = Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        for quantity in ("NaN", "Infinity", "-1", "2.0001", "not-a-number"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    receive_purchase_order_goods(
                        po=po, membership=membership, user=user,
                        lines_payload=[{"line_id": line.pk, "quantity": quantity}],
                    )
                self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())
                self.assertFalse(StockMovement.objects.filter(tenant=tenant).exists())
                self.assertFalse(StockBalance.objects.filter(menu_item=item, outlet=outlet).exists())

        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, membership=membership, user=user,
                lines_payload=[
                    {"line_id": line.pk, "quantity": "2"},
                    {"line_id": line.pk, "quantity": "3"},
                ],
            )
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, membership=membership, user=user,
                delivery_reference="A" * 129,
                lines_payload=[{"line_id": line.pk, "quantity": "1"}],
            )
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())


    def test_partial_delivery_audited_and_duplicate_supplier_reference_blocked(self):
        from apps.accounts.models import Membership, MembershipRole, User
        from apps.audit.models import AuditEvent
        from apps.inventory.models import StockBalance
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import receive_purchase_order_goods
        from rest_framework.exceptions import ValidationError

        tenant = Tenant.objects.create(name="Grocery Delivery Audit", slug="grocery-delivery-audit")
        site = Site.objects.create(tenant=tenant, name="Store")
        outlet = Outlet.objects.create(site=site, name="Receiving", outlet_type=OutletType.SUPERMARKET)
        category = MenuCategory.objects.create(tenant=tenant, name="Food")
        item = MenuItem.objects.create(
            tenant=tenant, category=category, name="Flour",
            unit_price=Decimal("3200"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=tenant, name="Mill")
        po = PurchaseOrder.objects.create(
            tenant=tenant, supplier=supplier, outlet=outlet, status=PurchaseOrderStatus.SENT,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item, quantity_ordered=Decimal("20"),
            unit_cost=Decimal("2000"),
        )
        user = User.objects.create_user(email="delivery-audit@example.test", password="TestPass9!")
        membership = Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
        receive_purchase_order_goods(
            po=po, membership=membership, user=user,
            delivery_reference=" Truck-001 ", discrepancy_note="12 units still with supplier",
            lines_payload=[{"line_id": line.pk, "quantity": "8"}],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        self.assertEqual(receipt.delivery_reference, "Truck-001")
        self.assertEqual(receipt.discrepancy_note, "12 units still with supplier")
        self.assertEqual(
            StockBalance.objects.get(outlet=outlet, menu_item=item).quantity,
            Decimal("8"),
        )
        audit = AuditEvent.objects.get(
            tenant=tenant, action="purchase.goods_received",
            entity_id=str(receipt.pk),
        )
        self.assertEqual(audit.payload["lines"][0]["quantity_received"], "8")
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, membership=membership, user=user,
                delivery_reference="truck-001",
                lines_payload=[{"line_id": line.pk, "quantity": "1"}],
            )
        self.assertEqual(PurchaseReceipt.objects.filter(purchase_order=po).count(), 1)
        self.assertEqual(
            StockBalance.objects.get(outlet=outlet, menu_item=item).quantity,
            Decimal("8"),
        )


class SupplierPaymentAmountPreflightTests(SimpleTestCase):
    def test_invalid_supplier_payment_rejected_before_lookup_or_posting(self):
        from apps.purchasing.services import record_supplier_payment
        from rest_framework.exceptions import ValidationError
        for amount in ("NaN", "Infinity", "-1", "0", "0.001", "not-a-number"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    record_supplier_payment(
                        po=None, amount=amount, method="cash", reference="",
                        idempotency_key="preflight-no-finance", user=None, membership=None,
                    )


class LandedCostAllocationTests(TestCase):
    def _bundle(self, slug):
        from apps.accounts.models import Membership, MembershipRole, User
        tenant = Tenant.objects.create(name=slug, slug=slug)
        site = Site.objects.create(tenant=tenant, name="Warehouse")
        outlet = Outlet.objects.create(
            site=site, name="Receiving", outlet_type=OutletType.SUPERMARKET
        )
        category = MenuCategory.objects.create(tenant=tenant, name="Goods")
        item_a = MenuItem.objects.create(
            tenant=tenant, category=category, name="Item A",
            unit_price=Decimal("1000"), track_inventory=True,
        )
        item_b = MenuItem.objects.create(
            tenant=tenant, category=category, name="Item B",
            unit_price=Decimal("2000"), track_inventory=True,
        )
        supplier = Supplier.objects.create(tenant=tenant, name="Supplier")
        po = PurchaseOrder.objects.create(
            tenant=tenant, supplier=supplier, outlet=outlet,
            status=PurchaseOrderStatus.SENT,
        )
        line_a = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item_a,
            quantity_ordered=Decimal("10"), unit_cost=Decimal("100.00"),
        )
        line_b = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item_b,
            quantity_ordered=Decimal("10"), unit_cost=Decimal("200.00"),
        )
        user = User.objects.create_user(
            email=f"{slug}@example.test", password="TestPass9!"
        )
        member = Membership.objects.create(
            tenant=tenant, user=user, role=MembershipRole.OWNER
        )
        member.sites.add(site)
        member.outlets.add(outlet)
        return tenant, outlet, po, line_a, line_b, user, member

    def test_quantity_allocation_distributes_extra_cost_by_received_units(self):
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import receive_purchase_order_goods
        _tenant, _outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-by-quantity"
        )
        receive_purchase_order_goods(
            po=po,
            membership=member,
            user=user,
            shipping_cost=Decimal("40.00"),
            duty_cost=Decimal("0.00"),
            landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
            lines_payload=[
                {"line_id": line_a.pk, "quantity": "1"},
                {"line_id": line_b.pk, "quantity": "3"},
            ],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        rows = {
            row.purchase_order_line_id: row
            for row in receipt.lines.all()
        }
        self.assertEqual(
            rows[line_a.pk].landed_cost_allocated, Decimal("10.00")
        )
        self.assertEqual(
            rows[line_b.pk].landed_cost_allocated, Decimal("30.00")
        )
        self.assertEqual(
            rows[line_a.pk].landed_unit_cost_snapshot, Decimal("110.0000")
        )
        self.assertEqual(
            rows[line_b.pk].landed_unit_cost_snapshot, Decimal("210.0000")
        )

    def test_manual_allocation_requires_exact_total_and_is_all_or_nothing(self):
        from apps.inventory.models import StockBalance
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import receive_purchase_order_goods
        from rest_framework.exceptions import ValidationError

        tenant, outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-manual"
        )
        with self.assertRaises(ValidationError) as ctx:
            receive_purchase_order_goods(
                po=po,
                membership=member,
                user=user,
                shipping_cost=Decimal("50.00"),
                landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.MANUAL,
                lines_payload=[
                    {
                        "line_id": line_a.pk,
                        "quantity": "2",
                        "landed_cost_amount": "20.00",
                    },
                    {
                        "line_id": line_b.pk,
                        "quantity": "3",
                        "landed_cost_amount": "20.00",
                    },
                ],
            )
        self.assertIn("must total 50.00", str(ctx.exception.detail))
        self.assertFalse(
            PurchaseReceipt.objects.filter(purchase_order=po).exists()
        )
        self.assertFalse(
            StockBalance.objects.filter(outlet=outlet).exists()
        )

        receive_purchase_order_goods(
            po=po,
            membership=member,
            user=user,
            shipping_cost=Decimal("50.00"),
            landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.MANUAL,
            lines_payload=[
                {
                    "line_id": line_a.pk,
                    "quantity": "2",
                    "landed_cost_amount": "20.00",
                },
                {
                    "line_id": line_b.pk,
                    "quantity": "3",
                    "landed_cost_amount": "30.00",
                },
            ],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        rows = {
            row.purchase_order_line_id: row
            for row in receipt.lines.all()
        }
        self.assertEqual(
            rows[line_a.pk].landed_cost_allocated, Decimal("20.00")
        )
        self.assertEqual(
            rows[line_b.pk].landed_cost_allocated, Decimal("30.00")
        )

    def test_posted_landed_cost_adjustment_is_append_only_and_revalues_current_stock(self):
        from apps.inventory.models import StockBalance
        from apps.purchasing.models import (
            PurchaseReceipt,
            PurchaseReceiptCostAdjustment,
        )
        from apps.purchasing.services import (
            receive_purchase_order_goods,
            record_receipt_landed_cost_adjustment,
        )

        tenant, outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-adjustment"
        )
        receive_purchase_order_goods(
            po=po,
            membership=member,
            user=user,
            shipping_cost=Decimal("40.00"),
            landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
            lines_payload=[
                {"line_id": line_a.pk, "quantity": "1"},
                {"line_id": line_b.pk, "quantity": "3"},
            ],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        original = {
            row.purchase_order_line_id: (
                row.landed_cost_allocated,
                row.landed_unit_cost_snapshot,
            )
            for row in receipt.lines.all()
        }

        adjustment = record_receipt_landed_cost_adjustment(
            receipt=receipt,
            amount=Decimal("20.00"),
            allocation_method=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
            reference="FREIGHT-ADJ-1",
            reason="Final freight invoice exceeded the provisional charge.",
            user=user,
            membership=member,
        )
        self.assertEqual(
            adjustment.amount,
            Decimal("20.00"),
        )
        allocated = {
            row.receipt_line.purchase_order_line_id: row.amount
            for row in adjustment.lines.select_related(
                "receipt_line__purchase_order_line"
            )
        }
        self.assertEqual(allocated[line_a.pk], Decimal("5.00"))
        self.assertEqual(allocated[line_b.pk], Decimal("15.00"))

        receipt.refresh_from_db()
        after_original = {
            row.purchase_order_line_id: (
                row.landed_cost_allocated,
                row.landed_unit_cost_snapshot,
            )
            for row in receipt.lines.all()
        }
        self.assertEqual(after_original, original)
        self.assertEqual(
            StockBalance.objects.get(
                outlet=outlet, menu_item=line_a.menu_item
            ).average_unit_cost,
            Decimal("115.0000"),
        )
        self.assertEqual(
            StockBalance.objects.get(
                outlet=outlet, menu_item=line_b.menu_item
            ).average_unit_cost,
            Decimal("215.0000"),
        )
        self.assertEqual(
            PurchaseReceiptCostAdjustment.objects.filter(receipt=receipt).count(),
            1,
        )

    def test_landed_cost_credit_cannot_exceed_cumulative_landed_cost(self):
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import (
            receive_purchase_order_goods,
            record_receipt_landed_cost_adjustment,
        )
        from rest_framework.exceptions import ValidationError

        _tenant, _outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-credit-limit"
        )
        receive_purchase_order_goods(
            po=po,
            membership=member,
            user=user,
            shipping_cost=Decimal("40.00"),
            landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
            lines_payload=[
                {"line_id": line_a.pk, "quantity": "1"},
                {"line_id": line_b.pk, "quantity": "3"},
            ],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        with self.assertRaises(ValidationError):
            record_receipt_landed_cost_adjustment(
                receipt=receipt,
                amount=Decimal("-50.00"),
                allocation_method=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
                reference="FREIGHT-CREDIT-TOO-LARGE",
                reason="Carrier credit exceeded the landed cost on this receipt.",
                user=user,
                membership=member,
            )
        self.assertFalse(receipt.cost_adjustments.exists())

    def test_landed_cost_adjustment_is_blocked_after_outbound_stock(self):
        from apps.inventory.models import StockReason
        from apps.inventory.services import apply_manual_stock_change
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import (
            receive_purchase_order_goods,
            record_receipt_landed_cost_adjustment,
        )
        from rest_framework.exceptions import ValidationError

        tenant, outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-after-outflow"
        )
        receive_purchase_order_goods(
            po=po,
            membership=member,
            user=user,
            shipping_cost=Decimal("20.00"),
            landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
            lines_payload=[
                {"line_id": line_a.pk, "quantity": "2"},
                {"line_id": line_b.pk, "quantity": "2"},
            ],
        )
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        apply_manual_stock_change(
            tenant_id=tenant.pk,
            outlet=outlet,
            menu_item=line_a.menu_item,
            quantity_change=Decimal("-1.000"),
            reason=StockReason.ADJUST_OUT,
            user=user,
            note="Damaged after receiving",
        )
        with self.assertRaises(ValidationError) as ctx:
            record_receipt_landed_cost_adjustment(
                receipt=receipt,
                amount=Decimal("10.00"),
                allocation_method=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
                reference="LATE-FREIGHT-1",
                reason="Late freight charge received after stock already moved.",
                user=user,
                membership=member,
            )
        self.assertIn("outbound stock activity", str(ctx.exception.detail))
        self.assertFalse(receipt.cost_adjustments.exists())

    def test_allocating_mode_rejects_missing_supplier_cost_before_stock_write(self):
        from apps.inventory.models import StockBalance
        from apps.purchasing.models import PurchaseReceipt
        from apps.purchasing.services import receive_purchase_order_goods
        from rest_framework.exceptions import ValidationError

        _tenant, outlet, po, line_a, line_b, user, member = self._bundle(
            "landed-missing-cost"
        )
        line_b.unit_cost = None
        line_b.save(update_fields=["unit_cost", "updated_at"])
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po,
                membership=member,
                user=user,
                shipping_cost=Decimal("25.00"),
                landed_cost_allocation=PurchaseReceipt.LandedCostAllocation.BY_QUANTITY,
                lines_payload=[
                    {"line_id": line_a.pk, "quantity": "1"},
                    {"line_id": line_b.pk, "quantity": "1"},
                ],
            )
        self.assertFalse(
            PurchaseReceipt.objects.filter(purchase_order=po).exists()
        )
        self.assertFalse(
            StockBalance.objects.filter(outlet=outlet).exists()
        )
