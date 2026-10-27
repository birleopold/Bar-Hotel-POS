from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.catalog.serializers import MenuItemListSerializer, MenuItemSerializer
from apps.inventory.models import (
    InventorySerialReturnLink,
    InventorySerialUnit,
    SerializedUnitStatus,
    StockBalance,
    StockMovement,
    StockReason,
)
from apps.inventory.services import execute_stock_transfer
from apps.inventory.services_serials import assign_serial_to_order_line
from apps.pos.models import Order, OrderLine, Payment
from apps.pos.services import add_supermarket_line_by_code, process_supermarket_line_return, record_order_payment
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, PurchaseReceipt, Supplier
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SerializedInventoryLifecycleTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Serialized retail", slug="serialized-retail")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "inventory", "purchasing"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main store")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Electronics", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="serialized@test.local", password="Password9!",
        )
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="Phones")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Smartphone X",
            sku="PHONE-X",
            unit_price=Decimal("500000"),
            track_inventory=True,
            serial_tracking=True,
            serial_identifier_type="imei",
            warranty_months=12,
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Phone supplier")
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _receive_two(self):
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=self.supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            reference="PO-IMEI-001",
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=self.item,
            quantity_ordered=Decimal("2"),
            unit_cost=Decimal("400000"),
        )
        response = self.client.post(
            reverse("staff-purchasing-order-detail", kwargs={"po_id": po.pk}),
            {
                "action": "receive",
                f"recv_{line.pk}": "",
                f"recv_packages_{line.pk}": "",
                f"recv_cartons_{line.pk}": "",
                f"recv_serials_{line.pk}": "356000000000001\n356000000000002",
                f"batch_{line.pk}": "",
                f"expiry_{line.pk}": "",
                "delivery_reference": "DN-IMEI-001",
                "receipt_note": "Two phones checked",
                "discrepancy_note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        return po, line

    def _open_sale(self, *, total="500000"):
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
            subtotal=Decimal(total),
            total=Decimal(total),
        )
        line = OrderLine.objects.create(
            order=order,
            menu_item=self.item,
            label=self.item.name,
            quantity=Decimal("1"),
            unit_price=Decimal(total),
            line_total=Decimal(total),
        )
        return order, line

    def test_catalog_api_exposes_and_validates_serialized_product_settings(self):
        request = SimpleNamespace(tenant=self.tenant)
        valid = MenuItemSerializer(
            data={
                "category": str(self.category.pk),
                "name": "Tracked tablet",
                "sku": "TAB-SER",
                "barcode": "",
                "unit_of_measure": "each",
                "units_per_carton": 1,
                "track_inventory": True,
                "serial_tracking": True,
                "serial_identifier_type": "serial",
                "warranty_months": 24,
                "unit_price": "900000",
                "is_active": True,
            },
            context={"request": request},
        )
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertTrue(valid.validated_data["serial_tracking"])
        self.assertEqual(valid.validated_data["warranty_months"], 24)

        untracked = MenuItemSerializer(
            data={
                "category": str(self.category.pk),
                "name": "Invalid untracked phone",
                "unit_of_measure": "each",
                "track_inventory": False,
                "serial_tracking": True,
                "serial_identifier_type": "imei",
                "unit_price": "1000",
            },
            context={"request": request},
        )
        self.assertFalse(untracked.is_valid())
        self.assertIn("serial_tracking", untracked.errors)

        weighted = MenuItemSerializer(
            data={
                "category": str(self.category.pk),
                "name": "Invalid weighted serial",
                "unit_of_measure": "kg",
                "track_inventory": True,
                "serial_tracking": True,
                "serial_identifier_type": "serial",
                "unit_price": "1000",
            },
            context={"request": request},
        )
        self.assertFalse(weighted.is_valid())
        self.assertIn("serial_tracking", weighted.errors)

        payload = MenuItemListSerializer(self.item).data
        self.assertTrue(payload["serial_tracking"])
        self.assertEqual(payload["serial_identifier_type"], "imei")
        self.assertEqual(payload["warranty_months"], 12)

    def test_serial_detail_route_is_not_available_in_hospitality_only_workspace(self):
        other = Tenant.objects.create(name="Hotel only serials", slug="hotel-only-serials")
        TenantSettings.objects.create(
            tenant=other,
            business_lines=["hotel"],
            enabled_staff_modules=["inventory", "lodging"],
        )
        site = Site.objects.create(tenant=other, name="Hotel")
        outlet = Outlet.objects.create(site=site, name="Stores", outlet_type=OutletType.LODGING_FRONT_DESK)
        user = User.objects.create_user(email="hotel-serial@test.local", password="Password9!")
        member = Membership.objects.create(user=user, tenant=other, role=MembershipRole.OWNER)
        member.sites.add(site)
        member.outlets.add(outlet)
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(other.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(outlet.pk)
        session.save()

        response = self.client.get(reverse("staff-inventory-serial-detail", args=[self.item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff-dashboard"))

    def test_serialized_po_receipt_creates_stock_and_identifiers_together(self):
        po, line = self._receive_two()
        line.refresh_from_db()
        self.assertEqual(line.quantity_received, Decimal("2"))
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("2"),
        )
        units = InventorySerialUnit.objects.filter(
            tenant=self.tenant, menu_item=self.item, outlet=self.outlet,
        ).order_by("serial_number")
        self.assertEqual(
            list(units.values_list("serial_number", flat=True)),
            ["356000000000001", "356000000000002"],
        )
        self.assertTrue(all(unit.status == SerializedUnitStatus.AVAILABLE for unit in units))
        self.assertTrue(all(unit.warranty_started_at is None for unit in units))
        self.assertTrue(all(unit.warranty_expires_at is None for unit in units))
        receipt = PurchaseReceipt.objects.get(purchase_order=po)
        self.assertEqual(receipt.lines.get().serialized_units.count(), 2)

    def test_final_payment_requires_exact_serial_assignment_and_starts_warranty(self):
        self._receive_two()
        order, line = self._open_sale()

        with self.assertRaises(ValidationError):
            record_order_payment(
                order=order,
                user=self.user,
                amount=Decimal("500000"),
                method="cash",
                idempotency_key="serial-no-imei",
            )
        order.refresh_from_db()
        self.assertFalse(order.is_paid)
        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("2"),
        )

        unit = assign_serial_to_order_line(
            order_line=line,
            serial_number="356000000000001",
            user=self.user,
        )
        self.assertEqual(unit.status, SerializedUnitStatus.RESERVED)
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Serial / IMEI assignment")
        self.assertContains(page, "356000000000001")

        payment, replay = record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("500000"),
            method="cash",
            idempotency_key="serial-with-imei",
        )
        self.assertFalse(replay)
        self.assertEqual(payment.amount, Decimal("500000"))
        order.refresh_from_db()
        unit.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "closed")
        self.assertEqual(unit.status, SerializedUnitStatus.SOLD)
        self.assertEqual(unit.sold_order_line, line)
        self.assertIsNone(unit.reserved_order_line)
        self.assertEqual(unit.warranty_started_at, timezone.localdate())
        self.assertIsNotNone(unit.warranty_expires_at)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("1"),
        )
        self.assertEqual(
            StockMovement.objects.get(order=order, menu_item=self.item, reason=StockReason.SALE).quantity_change,
            Decimal("-1"),
        )

    def test_scanning_imeis_adds_and_reserves_exact_units_through_fast_basket_path(self):
        self._receive_two()
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
        )
        first = add_supermarket_line_by_code(
            order=order,
            code="356000000000001",
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(first.quantity, Decimal("1"))
        first_unit = InventorySerialUnit.objects.get(serial_number="356000000000001")
        self.assertEqual(first_unit.status, SerializedUnitStatus.RESERVED)
        self.assertEqual(first_unit.reserved_order_line, first)

        second = add_supermarket_line_by_code(
            order=order,
            code="356000000000002",
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(second.pk, first.pk)
        second.refresh_from_db()
        self.assertEqual(second.quantity, Decimal("2"))
        self.assertEqual(second.reserved_serial_units.filter(status=SerializedUnitStatus.RESERVED).count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("1000000.00"))

        payment, replay = record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("1000000"),
            method="cash",
            idempotency_key="serial-fast-scan-sale",
        )
        self.assertFalse(replay)
        self.assertEqual(payment.amount, Decimal("1000000"))
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("0"),
        )
        self.assertEqual(
            InventorySerialUnit.objects.filter(
                menu_item=self.item, status=SerializedUnitStatus.SOLD,
            ).count(),
            2,
        )

    def test_exact_serial_return_restocks_and_replay_cannot_swap_imei(self):
        self._receive_two()
        order, line = self._open_sale()
        assign_serial_to_order_line(
            order_line=line, serial_number="356000000000001", user=self.user,
        )
        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("500000"),
            method="cash",
            idempotency_key="serial-return-sale",
        )
        returned = process_supermarket_line_return(
            order=order,
            line=line,
            quantity=Decimal("1"),
            reason="Customer exchange",
            restock=True,
            user=self.user,
            idempotency_key="serial-return-physical",
            serial_numbers="356000000000001",
        )
        unit = InventorySerialUnit.objects.get(serial_number="356000000000001")
        self.assertEqual(unit.status, SerializedUnitStatus.RETURNED)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("2"),
        )
        link = InventorySerialReturnLink.objects.get(return_record=returned)
        self.assertEqual(link.serial_unit, unit)
        self.assertEqual(link.disposition, InventorySerialReturnLink.Disposition.RESTOCKED)

        replay = process_supermarket_line_return(
            order=order,
            line=line,
            quantity=Decimal("1"),
            reason="Customer exchange",
            restock=True,
            user=self.user,
            idempotency_key="serial-return-physical",
            serial_numbers="356000000000001",
        )
        self.assertEqual(replay.pk, returned.pk)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("2"),
        )
        with self.assertRaises(ValidationError):
            process_supermarket_line_return(
                order=order,
                line=line,
                quantity=Decimal("1"),
                reason="Customer exchange",
                restock=True,
                user=self.user,
                idempotency_key="serial-return-physical",
                serial_numbers="356000000000002",
            )

    def test_serialized_non_restock_return_is_quarantined_without_stock_increase(self):
        self._receive_two()
        order, line = self._open_sale()
        assign_serial_to_order_line(
            order_line=line, serial_number="356000000000002", user=self.user,
        )
        record_order_payment(
            order=order,
            user=self.user,
            amount=Decimal("500000"),
            method="cash",
            idempotency_key="serial-quarantine-sale",
        )
        before = StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity
        returned = process_supermarket_line_return(
            order=order,
            line=line,
            quantity=Decimal("1"),
            reason="Screen damaged on return",
            restock=False,
            user=self.user,
            serial_numbers="356000000000002",
        )
        unit = InventorySerialUnit.objects.get(serial_number="356000000000002")
        self.assertEqual(unit.status, SerializedUnitStatus.QUARANTINED)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            before,
        )
        self.assertEqual(
            InventorySerialReturnLink.objects.get(return_record=returned).disposition,
            InventorySerialReturnLink.Disposition.QUARANTINED,
        )

    def test_serialized_transfer_moves_exact_custody_and_aggregate_stock_together(self):
        self._receive_two()
        destination = Outlet.objects.create(
            site=self.site, name="Phone kiosk", outlet_type=OutletType.SUPERMARKET,
        )
        self.membership.outlets.add(destination)
        response = self.client.post(
            reverse("staff-inventory-serials"),
            {
                "from_outlet": str(self.outlet.pk),
                "to_outlet": str(destination.pk),
                "serial_numbers": "356000000000001",
                "note": "Move one phone to kiosk",
            },
        )
        self.assertEqual(response.status_code, 302)
        unit = InventorySerialUnit.objects.get(serial_number="356000000000001")
        self.assertEqual(unit.outlet, destination)
        self.assertEqual(unit.status, SerializedUnitStatus.AVAILABLE)
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("1"),
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=destination, menu_item=self.item).quantity,
            Decimal("1"),
        )
        movements = StockMovement.objects.filter(
            menu_item=self.item,
            reason__in=[StockReason.TRANSFER_OUT, StockReason.TRANSFER_IN],
        ).order_by("created_at")
        self.assertEqual(movements.count(), 2)
        self.assertEqual(movements[0].transfer_batch, movements[1].transfer_batch)
        self.assertTrue(unit.events.filter(event_type="transferred", outlet=destination).exists())

    def test_generic_transfer_rejects_serialized_product_without_side_effect(self):
        self._receive_two()
        other_outlet = Outlet.objects.create(
            site=self.site, name="Branch two", outlet_type=OutletType.SUPERMARKET,
        )
        self.membership.outlets.add(other_outlet)
        with self.assertRaises(ValidationError):
            execute_stock_transfer(
                tenant_id=self.tenant.pk,
                membership=self.membership,
                from_outlet=self.outlet,
                to_outlet=other_outlet,
                menu_item=self.item,
                quantity=Decimal("1"),
                user=self.user,
            )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=self.item).quantity,
            Decimal("2"),
        )
        self.assertFalse(StockBalance.objects.filter(outlet=other_outlet, menu_item=self.item).exists())

    def test_serial_register_and_trace_are_tenant_scoped(self):
        self._receive_two()
        unit = InventorySerialUnit.objects.get(serial_number="356000000000001")
        listing = self.client.get(reverse("staff-inventory-serials"), {"q": "356000000000001"})
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "356000000000001")
        detail = self.client.get(reverse("staff-inventory-serial-detail", args=[unit.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Custody history")
        self.assertContains(detail, "Received")
