from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.label_queue import queue_product_label
from apps.catalog.models import MenuCategory, MenuItem, ProductLabelQueueEntry
from apps.inventory.models import StockBalance
from apps.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus, Supplier
from apps.purchasing.services import receive_purchase_order_goods
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class ProductLabelQueueTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Label queue shop", slug="label-queue-shop")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["inventory", "purchasing", "pos", "workspace"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Shop floor", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="labels@test.local", password="Password9!")
        self.membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _item(self, *, name="Soap", price="3000", track=True):
        return MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name=name,
            sku=name.upper().replace(" ", "-"),
            barcode="",
            unit_price=Decimal(price),
            track_inventory=track,
        )

    def test_console_new_product_queues_new_product_label(self):
        response = self.client.post(
            reverse("console-org-menu-item-create"),
            {
                "category": str(self.category.pk),
                "product_family": "",
                "name": "New Shampoo",
                "description": "",
                "brand": "Acme",
                "model_number": "",
                "reference_code": "",
                "msrp": "",
                "display_image_url": "",
                "sku": "SHAMPOO-1",
                "barcode": "991001",
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "on",
                "serial_tracking": "",
                "serial_identifier_type": "serial",
                "warranty_months": "",
                "reorder_level": "",
                "unit_price": "7500",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = MenuItem.objects.get(tenant=self.tenant, sku="SHAMPOO-1")
        entry = ProductLabelQueueEntry.objects.get(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.NEW_PRODUCT,
            status=ProductLabelQueueEntry.Status.PENDING,
        )
        self.assertEqual(entry.price_snapshot, Decimal("7500.00"))

    def test_base_price_change_queues_current_price_label(self):
        item = self._item()
        response = self.client.post(
            reverse("console-org-menu-item-edit", args=[item.pk]),
            {
                "category": str(self.category.pk),
                "product_family": "",
                "name": item.name,
                "description": "",
                "brand": "",
                "model_number": "",
                "reference_code": "",
                "msrp": "",
                "display_image_url": "",
                "sku": item.sku,
                "barcode": "",
                "unit_of_measure": "each",
                "units_per_carton": "1",
                "track_inventory": "on",
                "serial_tracking": "",
                "serial_identifier_type": "serial",
                "warranty_months": "",
                "reorder_level": "",
                "unit_price": "3500",
                "tax_rate_percent": "",
                "is_active": "on",
                "kds_station": "",
                "consume_recipe_on_sale": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        entry = ProductLabelQueueEntry.objects.get(
            menu_item=item,
            outlet=self.outlet,
            reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
            status=ProductLabelQueueEntry.Status.PENDING,
        )
        self.assertEqual(entry.price_snapshot, Decimal("3500.00"))

    def test_repeated_same_reason_coalesces_pending_label_and_updates_snapshot(self):
        item = self._item()
        first = queue_product_label(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
            user=self.user,
            note="First",
        )
        item.unit_price = Decimal("4200")
        item.save(update_fields=["unit_price"])
        second = queue_product_label(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
            user=self.user,
            note="Second",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            ProductLabelQueueEntry.objects.filter(
                menu_item=item,
                outlet=self.outlet,
                reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).count(),
            1,
        )
        second.refresh_from_db()
        self.assertEqual(second.price_snapshot, Decimal("4200.00"))
        self.assertEqual(second.note, "Second")

    def test_goods_receiving_queues_label_without_changing_stock_semantics(self):
        item = self._item()
        supplier = Supplier.objects.create(tenant=self.tenant, name="Supplier")
        po = PurchaseOrder.objects.create(
            tenant=self.tenant,
            supplier=supplier,
            outlet=self.outlet,
            status=PurchaseOrderStatus.SENT,
            created_by=self.user,
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=po,
            menu_item=item,
            quantity_ordered=Decimal("5"),
            unit_cost=Decimal("2000"),
        )
        receive_purchase_order_goods(
            po=po,
            lines_payload=[{"line_id": line.pk, "quantity": Decimal("5")}],
            user=self.user,
            membership=self.membership,
            delivery_reference="DN-LABEL-1",
        )
        self.assertEqual(
            StockBalance.objects.get(outlet=self.outlet, menu_item=item).quantity,
            Decimal("5"),
        )
        self.assertTrue(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=item,
                reason=ProductLabelQueueEntry.Reason.RECEIVING,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).exists()
        )

    def test_pending_queue_filter_and_pdf_print_complete_pending_work(self):
        item = self._item()
        queue_product_label(
            tenant_id=self.tenant.pk,
            outlet=self.outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.PRICE_CHANGE,
            user=self.user,
            note="Price changed",
        )
        url = reverse("staff-inventory-shelf-labels")
        page = self.client.get(url, {"outlet": str(self.outlet.pk), "queue": "1"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pending queue · 1")
        self.assertContains(page, "Price change")
        self.assertContains(page, item.name)

        printed = self.client.post(
            url,
            {
                "outlet": str(self.outlet.pk),
                "return_queue": "1",
                "item_ids": [str(item.pk)],
                f"copies_{item.pk}": "1",
            },
        )
        self.assertEqual(printed.status_code, 200)
        self.assertEqual(printed["Content-Type"], "application/pdf")
        entry = ProductLabelQueueEntry.objects.get(menu_item=item, outlet=self.outlet)
        self.assertEqual(entry.status, ProductLabelQueueEntry.Status.PRINTED)
        self.assertEqual(entry.completed_by, self.user)
        self.assertIsNotNone(entry.completed_at)

    def test_hospitality_outlet_does_not_receive_retail_label_queue_entry(self):
        hotel_outlet = Outlet.objects.create(
            site=self.site, name="Hotel desk", outlet_type=OutletType.LODGING_FRONT_DESK,
        )
        item = self._item()
        result = queue_product_label(
            tenant_id=self.tenant.pk,
            outlet=hotel_outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.MANUAL,
            user=self.user,
        )
        self.assertIsNone(result)
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(outlet=hotel_outlet, menu_item=item).exists()
        )
