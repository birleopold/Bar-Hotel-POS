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

    def test_all_merchandise_label_templates_generate_from_same_workflow(self):
        item = self._item(name="Template phone", price="650000")
        item.brand = "Acme"
        item.model_number = "A100"
        item.reference_code = "REF-100"
        item.msrp = Decimal("700000")
        item.barcode = "9988776655"
        item.save(update_fields=[
            "brand", "model_number", "reference_code", "msrp", "barcode",
        ])
        url = reverse("staff-inventory-shelf-labels")
        page = self.client.get(
            url,
            {"outlet": str(self.outlet.pk), "template": "product"},
        )
        self.assertEqual(page.status_code, 200)
        for label in ("Shelf / price", "Product identity", "Markdown", "Receiving"):
            self.assertContains(page, label)

        for template_key in ("shelf", "product", "markdown", "receiving"):
            response = self.client.post(
                url,
                {
                    "action": "print",
                    "outlet": str(self.outlet.pk),
                    "template": template_key,
                    "item_ids": [str(item.pk)],
                    f"copies_{item.pk}": "1",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn(
                f'filename="{template_key}-labels.pdf"',
                response["Content-Disposition"],
            )
            self.assertGreater(len(response.content), 500)

    def test_manual_label_request_and_dismiss_are_audited_queue_states(self):
        item = self._item(name="Manual label item", price="6200")
        url = reverse("staff-inventory-shelf-labels")

        queued = self.client.post(
            url,
            {
                "action": "manual_queue",
                "outlet": str(self.outlet.pk),
                "manual_item_id": str(item.pk),
                "queue_note": "Shelf label was damaged",
                "return_queue": "1",
            },
        )
        self.assertEqual(queued.status_code, 302)
        entry = ProductLabelQueueEntry.objects.get(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=item,
            reason=ProductLabelQueueEntry.Reason.MANUAL,
        )
        self.assertEqual(entry.status, ProductLabelQueueEntry.Status.PENDING)
        self.assertEqual(entry.price_snapshot, Decimal("6200.00"))
        self.assertEqual(entry.note, "Shelf label was damaged")
        self.assertEqual(entry.requested_by, self.user)

        page = self.client.get(
            url,
            {"outlet": str(self.outlet.pk), "queue": "1"},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pending label work")
        self.assertContains(page, "Manual request")
        self.assertContains(page, "Shelf label was damaged")
        self.assertContains(page, item.name)

        dismissed = self.client.post(
            url,
            {
                "action": "dismiss_queue",
                "outlet": str(self.outlet.pk),
                "queue_entry_ids": [str(entry.pk)],
                "dismiss_note": "Display removed",
                "return_queue": "1",
            },
        )
        self.assertEqual(dismissed.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, ProductLabelQueueEntry.Status.DISMISSED)
        self.assertEqual(entry.completed_by, self.user)
        self.assertIsNotNone(entry.completed_at)
        self.assertEqual(entry.note, "Display removed")

        history = self.client.get(
            url,
            {"outlet": str(self.outlet.pk), "queue": "1"},
        )
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Recent completed label work")
        self.assertContains(history, "Dismissed")

    def test_label_queue_management_requires_inventory_adjust_capability(self):
        item = self._item(name="Restricted label item")
        accountant = User.objects.create_user(
            email="label-accountant@test.local",
            password="Password9!",
        )
        membership = Membership.objects.create(
            user=accountant,
            tenant=self.tenant,
            role=MembershipRole.ACCOUNTANT,
        )
        membership.sites.add(self.site)
        membership.outlets.add(self.outlet)
        self.client.force_login(accountant)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

        response = self.client.post(
            reverse("staff-inventory-shelf-labels"),
            {
                "action": "manual_queue",
                "outlet": str(self.outlet.pk),
                "manual_item_id": str(item.pk),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=item,
                reason=ProductLabelQueueEntry.Reason.MANUAL,
            ).exists()
        )

    def test_malformed_label_queue_ids_fail_closed(self):
        item = self._item(name="Malformed queue target")
        url = reverse("staff-inventory-shelf-labels")
        response = self.client.post(
            url,
            {
                "action": "manual_queue",
                "outlet": str(self.outlet.pk),
                "manual_item_id": "not-a-uuid",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(menu_item=item).exists()
        )
        response = self.client.post(
            url,
            {
                "action": "dismiss_queue",
                "outlet": str(self.outlet.pk),
                "queue_entry_ids": ["not-a-uuid"],
            },
        )
        self.assertEqual(response.status_code, 302)

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
