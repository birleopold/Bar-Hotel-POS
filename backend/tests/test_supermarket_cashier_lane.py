"""Staff supermarket cashier flow: scan and POST-only next basket."""
from decimal import Decimal

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, Promotion, SupermarketSkuProfile
from apps.pos.models import Order
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class SupermarketCashierLaneTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Cashier Grocery", slug="cashier-grocery")
        TenantSettings.objects.create(
            tenant=self.tenant, business_lines=["supermarket"],
            default_currency="UGX",
        )
        site = Site.objects.create(tenant=self.tenant, name="Store")
        self.outlet = Outlet.objects.create(
            site=site, name="Till area", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="cashier-grocery@test.local", password="TestPass9!")
        membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OUTLET_MANAGER,
        )
        membership.sites.add(site)
        membership.outlets.add(self.outlet)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def test_pin_idle_policy_matches_selected_business_and_rejects_foreign_outlet(self):
        """Assigned retail cashiers must not inherit the two-minute hotel timer."""
        from types import SimpleNamespace
        from apps.staff.middleware import RETAIL_PIN_IDLE_SECONDS, staff_pin_idle_seconds

        retail = SimpleNamespace(
            tenant_membership=Membership.objects.get(tenant=self.tenant, user=self.user),
            session={STAFF_SESSION_OUTLET_KEY: str(self.outlet.pk)},
        )
        self.assertEqual(staff_pin_idle_seconds(retail), RETAIL_PIN_IDLE_SECONDS)

        hospitality_outlet = Outlet.objects.create(
            site=self.outlet.site, name="Shared Bar", outlet_type=OutletType.BAR,
        )
        retail.tenant_membership.outlets.add(hospitality_outlet)
        shared = SimpleNamespace(
            tenant_membership=retail.tenant_membership,
            session={STAFF_SESSION_OUTLET_KEY: str(hospitality_outlet.pk)},
        )
        self.assertEqual(staff_pin_idle_seconds(shared), 2 * 60)

        another = Tenant.objects.create(name="Other Register", slug="other-register-idle")
        foreign_site = Site.objects.create(tenant=another, name="Different Site")
        foreign_outlet = Outlet.objects.create(
            site=foreign_site, name="Foreign Retail", outlet_type=OutletType.RETAIL,
        )
        untrusted = SimpleNamespace(
            tenant_membership=retail.tenant_membership,
            session={STAFF_SESSION_OUTLET_KEY: str(foreign_outlet.pk)},
        )
        self.assertEqual(staff_pin_idle_seconds(untrusted), 2 * 60)

    def test_empty_legacy_usd_basket_opens_in_tenant_ugx(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        Order.objects.filter(pk=order.pk).update(currency="USD")
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.currency, "UGX")
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UGX")
        self.assertNotContains(response, "This sale uses USD")

    def test_print_empty_legacy_usd_basket_in_ugx(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        Order.objects.filter(pk=order.pk).update(currency="USD")
        response = self.client.get(reverse("staff-order-print", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.currency, "UGX")
        self.assertContains(response, "UGX")
        self.assertNotContains(response, "Total USD")

    def test_print_completed_legacy_usd_sale_preserves_history(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        Order.objects.filter(pk=order.pk).update(currency="USD", status="closed", is_paid=True)
        response = self.client.get(reverse("staff-order-print", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.currency, "USD")
        self.assertContains(response, "Total USD")

    def test_completed_legacy_usd_sale_is_never_relabelled(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        Order.objects.filter(pk=order.pk).update(currency="USD", status="closed", is_paid=True)
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.currency, "USD")
        self.assertContains(response, "This sale uses USD")

    def test_cashier_manager_does_not_get_owner_administration_dashboard(self):
        page = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'class="owner-home"')
        # The current tenant-aware dashboard uses the unified shell, not the
        # retired staff-dash-hero markup. Preserve the actual role boundary.
        self.assertContains(page, 'class="fizo-dash fz-industry-dashboard"')
        self.assertContains(page, "Supermarket dashboard")
        self.assertNotContains(page, "Hotel dashboard")

    def test_grocery_product_editor_and_stock_form_have_simple_labels(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        product = self.client.get(reverse("console-org-menu-item-create"))
        self.assertEqual(product.status_code, 200)
        self.assertContains(product, "Add a product")
        self.assertContains(product, "grocery-guided-form")
        self.assertContains(product, "Save product")
        stock = self.client.get(reverse("staff-inventory-movement-create"))
        self.assertEqual(stock.status_code, 200)
        self.assertContains(stock, "Receive or adjust stock")
        self.assertContains(stock, "grocery-staff-form")

    def test_owner_setup_console_has_retail_skin(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        response = self.client.get(reverse("console-org-setup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fizo-setup-area.css")
        self.assertContains(response, "grocery-console-body")
        self.assertContains(response, "fizo-shell-top")
        self.assertContains(response, "grocery-setup__hero-actions")
        self.assertContains(response, "Guided setup")

    def test_grocery_setup_stays_styled_with_restaurant_module_enabled(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        settings = TenantSettings.objects.get(tenant=self.tenant)
        settings.business_lines = ["supermarket", "restaurant"]
        settings.save(update_fields=["business_lines"])
        page = self.client.get(reverse("console-org-setup"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "grocery-console-body")
        self.assertContains(page, "fizo-setup-area.css")
        self.assertContains(page, "grocery-setup__layout")

    def test_owner_administration_shell_persists_after_navigation(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        for name in ("staff-dashboard", "staff-menu", "staff-inventory-balances", "staff-orders"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="staff-sidebar"')
                self.assertContains(response, 'class="staff-nav"')
                self.assertContains(response, "grocery-owner-body")
                self.assertContains(response, 'id="staff-main-content"')

    def test_grocery_owner_products_page_uses_retail_language(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        page = self.client.get(reverse("staff-menu"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Products")
        self.assertContains(page, "Search your sellable products by name, SKU or barcode.")
        self.assertNotContains(page, "Hotel dashboard")
        self.assertContains(page, "staff-sidebar")

    def test_owner_dashboard_has_guided_setup_and_actual_sections(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        page = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Here's your store at a glance.")
        self.assertContains(page, "Set up your store")
        # Assert the live shared owner workspace, not the retired owner-home shell.
        self.assertContains(page, "fizo-dash__head")
        self.assertContains(page, "Sales snapshot")
        self.assertContains(page, "Operations pulse")
        self.assertContains(page, "Administration")
        self.assertContains(page, "Guided setup")
        self.assertContains(page, reverse("console-org-menu-item-create"))
        self.assertContains(page, "Configure payments and tills")
        self.assertNotContains(page, "Hotel dashboard")
        self.assertIn("grocery_setup_checks", page.context)
        self.assertFalse(page.context["grocery_setup_checks"]["sale"])
        self.assertContains(page, 'href="' + reverse("staff-workspace-members") + '"')
        self.assertContains(page, 'href="' + reverse("staff-inventory-balances") + '"')

    def test_grocery_checkout_exposes_visual_layout_assets(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user
        )
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "retail-workflows.css")
        self.assertContains(page, "retail-cashier.css")
        self.assertContains(page, "retail-counter-v2.js")
        self.assertContains(page, "staff-pos-order-layout")
        self.assertContains(page, "data-retail-scan-form")
        self.assertContains(page, "staff-pos-order-side")

    def test_server_cashier_can_apply_eligible_offer_inline(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.pos.models import OrderLine

        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.SERVER
        membership.save(update_fields=["role"])

        category = MenuCategory.objects.create(
            tenant=self.tenant, name="Offer products",
        )
        item = MenuItem.objects.create(
            tenant=self.tenant,
            category=category,
            name="Offer soap",
            sku="OFFER-SOAP",
            unit_price=Decimal("10000.00"),
            is_active=True,
        )
        order = Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
            subtotal=Decimal("20000.00"),
            total=Decimal("20000.00"),
        )
        OrderLine.objects.create(
            order=order,
            menu_item=item,
            label=item.name,
            quantity=Decimal("2"),
            unit_price=Decimal("10000.00"),
            line_total=Decimal("20000.00"),
        )
        promotion = Promotion.objects.create(
            tenant=self.tenant,
            name="Cashier offer",
            discount_percent=Decimal("10"),
            starts_at=timezone.now() - timedelta(hours=1),
            is_active=True,
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-retail-promotion-form")
        self.assertContains(page, "Cashier offer")

        response = self.client.post(
            url,
            {"action": "apply_promotion", "promotion": str(promotion.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["currency"], "UGX")
        self.assertEqual(Decimal(body["discount"]), Decimal("2000.00"))
        self.assertEqual(Decimal(body["total"]), Decimal("18000.00"))

        order.refresh_from_db()
        self.assertEqual(order.applied_promotion_id, promotion.pk)
        self.assertEqual(order.discount_amount, Decimal("2000.00"))
        self.assertEqual(order.total, Decimal("18000.00"))

    def test_grocery_tiles_can_display_catalogue_photos(self):
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Fresh items")
        MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Grocery milk",
            unit_price=Decimal("3000"),
            display_image_url="https://example.com/milk.png",
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user
        )
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Grocery milk")
        self.assertContains(page, "milk.png")

    def test_purchase_delivery_preflight_and_duplicate_reference_keep_stock_accurate(self):
        from rest_framework.exceptions import ValidationError
        from apps.purchasing.models import (
            Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus,
            PurchaseReceipt,
        )
        from apps.purchasing.services import receive_purchase_order_goods
        from apps.inventory.models import StockBalance, StockMovement, StockReason

        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        category = MenuCategory.objects.create(
            tenant=self.tenant, name="Incoming supply",
        )
        item_a = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Paper towels",
            sku="PO-TOWELS", unit_price=Decimal("4000"), track_inventory=True,
        )
        item_b = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Dish soap",
            sku="PO-SOAP", unit_price=Decimal("5500"), track_inventory=True,
        )
        supplier = Supplier.objects.create(
            tenant=self.tenant, name="Incoming supply company",
        )
        po = PurchaseOrder.objects.create(
            tenant=self.tenant, supplier=supplier, outlet=self.outlet,
            status=PurchaseOrderStatus.SENT, created_by=self.user,
        )
        a = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item_a, quantity_ordered=Decimal("5"),
            units_per_carton_snapshot=2,
        )
        b = PurchaseOrderLine.objects.create(
            purchase_order=po, menu_item=item_b, quantity_ordered=Decimal("2"),
        )
        payload = [
            {"line_id": str(a.pk), "quantity": "3"},
            {"line_id": str(b.pk), "quantity": "3"},
        ]
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, lines_payload=payload, user=self.user,
                membership=membership, delivery_reference="DEL-123",
            )
        self.assertFalse(PurchaseReceipt.objects.filter(purchase_order=po).exists())
        self.assertFalse(StockMovement.objects.filter(purchase_order=po).exists())
        self.assertFalse(StockBalance.objects.filter(outlet=self.outlet,
                                                       menu_item__in=[item_a, item_b]).exists())

        payload[1]["quantity"] = "2"
        receive_purchase_order_goods(
            po=po, lines_payload=payload, user=self.user,
            membership=membership, delivery_reference="DEL-123",
            discrepancy_note="Three towels delivered now; two pending",
        )
        a.refresh_from_db()
        b.refresh_from_db()
        po.refresh_from_db()
        self.assertEqual(a.quantity_received, Decimal("3"))
        self.assertEqual(b.quantity_received, Decimal("2"))
        self.assertEqual(po.status, PurchaseOrderStatus.PARTIALLY_RECEIVED)
        self.assertEqual(PurchaseReceipt.objects.filter(purchase_order=po).count(), 1)
        self.assertEqual(StockBalance.objects.get(
            outlet=self.outlet, menu_item=item_a).quantity, Decimal("3"))
        self.assertEqual(StockBalance.objects.get(
            outlet=self.outlet, menu_item=item_b).quantity, Decimal("2"))
        with self.assertRaises(ValidationError):
            receive_purchase_order_goods(
                po=po, lines_payload=payload, user=self.user,
                membership=membership, delivery_reference="del-123",
            )
        self.assertEqual(PurchaseReceipt.objects.filter(purchase_order=po).count(), 1)
        self.assertEqual(StockMovement.objects.filter(
            purchase_order=po, reason=StockReason.RECEIVE).count(), 2)
        # A supplier carton represented as "1.0" is a valid whole carton.
        # The second delivery completes the two remaining units in the PO.
        receive_purchase_order_goods(
            po=po,
            lines_payload=[{
                "line_id": str(a.pk), "quantity": "0", "cartons": "1.0",
            }],
            user=self.user, membership=membership,
            delivery_reference="DEL-124",
        )
        po.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrderStatus.RECEIVED)
        self.assertEqual(a.quantity_received, Decimal("5"))
        self.assertEqual(StockBalance.objects.get(
            outlet=self.outlet, menu_item=item_a).quantity, Decimal("5"))
        receipt = PurchaseReceipt.objects.get(
            purchase_order=po, delivery_reference="DEL-124",
        )
        self.assertEqual(receipt.lines.get().cartons_received, 1)
        self.assertEqual(PurchaseReceipt.objects.filter(
            purchase_order=po).count(), 2)

    def test_cashier_tile_uses_effective_outlet_price_not_global_base(self):
        from apps.catalog.models import MenuItemOutlet
        from apps.pos.services import add_line_to_open_order

        cat = MenuCategory.objects.create(tenant=self.tenant, name="Outlet pricing")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Mineral water",
            sku="PRICE-OVERRIDE", unit_price=Decimal("3500.00"),
            track_inventory=False,
        )
        MenuItemOutlet.objects.create(
            menu_item=item, outlet=self.outlet, price_override=Decimal("2400.00"),
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        page = self.client.get(url, {"catalogue_q": "PRICE-OVERRIDE"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "UGX 2400.00")
        self.assertNotContains(page, "UGX 3500.00")
        line = add_line_to_open_order(
            order=order, menu_item=item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("2400.00"))
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("2400.00"))

    def test_cashier_tile_excludes_expired_and_held_batches(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.inventory.batches import InventoryBatch
        from apps.inventory.models import StockBalance
        category = MenuCategory.objects.create(
            tenant=self.tenant, name="Batch-stock shelf",
        )
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Yoghurt tub",
            sku="YOGH-EXP", unit_price=Decimal("3500"),
            track_inventory=True, reorder_level=Decimal("3"),
        )
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet,
            menu_item=item, quantity=Decimal("12"),
        )
        today = timezone.localdate()
        for code, amount, expiry, held in (
            ("expired", "5", today - timedelta(days=1), False),
            ("held", "4", today + timedelta(days=8), True),
            ("ready", "3", today + timedelta(days=8), False),
        ):
            InventoryBatch.objects.create(
                tenant=self.tenant, outlet=self.outlet,
                menu_item=item, batch_code=code, received_at=today - timedelta(days=3),
                expiry_date=expiry, received_quantity=Decimal(amount),
                remaining_quantity=Decimal(amount), quarantined=held,
            )
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        response = self.client.get(url, {"catalogue_q": "YOGH-EXP"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low stock · 3 left")
        self.assertContains(response, "Check held/expired batches")
        self.assertNotContains(response, "Sellable · 12")

    def test_cashier_tiles_show_only_selected_outlet_stock_and_reorder_warning(self):
        from apps.inventory.models import StockBalance

        category = MenuCategory.objects.create(
            tenant=self.tenant, name="Retail stock visibility",
        )
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Packing tape",
            sku="TAPE-LOW", unit_price=Decimal("4000"),
            track_inventory=True, reorder_level=Decimal("3"),
        )
        elsewhere = Outlet.objects.create(
            site=self.outlet.site, name="Warehouse", outlet_type=OutletType.RETAIL,
        )
        StockBalance.objects.create(
            tenant=self.tenant, outlet=elsewhere, menu_item=item,
            quantity=Decimal("90"),
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        empty = self.client.get(url, {"catalogue_q": "TAPE-LOW"})
        self.assertEqual(empty.status_code, 200)
        self.assertContains(empty, "No sellable stock")
        self.assertNotContains(empty, "Sellable · 90")
        StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet, menu_item=item,
            quantity=Decimal("2"),
        )
        low = self.client.get(url, {"catalogue_q": "TAPE-LOW"})
        self.assertContains(low, "Low stock · 2")
        StockBalance.objects.filter(
            outlet=self.outlet, menu_item=item,
        ).update(quantity=Decimal("12"))
        stocked = self.client.get(url, {"catalogue_q": "TAPE-LOW"})
        self.assertContains(stocked, "Sellable · 12")
        self.assertNotContains(stocked, "Low stock · 2")

    def test_settlement_rejects_combined_direct_and_recipe_stock_overdraw(self):
        from rest_framework.exceptions import ValidationError
        from apps.catalog.models import MenuItemRecipeLine
        from apps.inventory.models import StockBalance, StockMovement
        from apps.inventory.services import validate_and_consume_stock_for_paid_order
        from apps.pos.models import OrderLine, Payment
        from apps.pos.services import record_order_payment

        category = MenuCategory.objects.create(tenant=self.tenant, name="Assembly")
        ingredient = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Shared flour",
            sku="SHARED-FLOUR", unit_price=Decimal("2000"),
            track_inventory=True,
        )
        assembled = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Prepared pastry",
            sku="PASTRY", unit_price=Decimal("4000"),
            track_inventory=False, consume_recipe_on_sale=True,
        )
        MenuItemRecipeLine.objects.create(
            parent_item=assembled, ingredient_item=ingredient,
            quantity_per_unit=Decimal("2"),
        )
        balance = StockBalance.objects.create(
            tenant=self.tenant, outlet=self.outlet,
            menu_item=ingredient, quantity=Decimal("4"),
        )
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("10000"), total=Decimal("10000"),
        )
        for item, qty in ((ingredient, "3"), (assembled, "1")):
            OrderLine.objects.create(
                order=sale, menu_item=item, label=item.name,
                quantity=Decimal(qty), unit_price=item.unit_price,
                line_total=item.unit_price * Decimal(qty),
            )
        # Direct sale 3 + pastry recipe 2 = 5, not the 4 in stock.
        with self.assertRaises(ValidationError):
            validate_and_consume_stock_for_paid_order(sale, self.user)
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("4"))
        self.assertFalse(StockMovement.objects.filter(order=sale).exists())
        with self.assertRaises(ValidationError):
            record_order_payment(
                order=sale, user=self.user, amount=Decimal("10000"),
                method="cash", idempotency_key="combined-stock-rejected",
            )
        sale.refresh_from_db()
        balance.refresh_from_db()
        self.assertFalse(sale.is_paid)
        self.assertEqual(sale.status, "open")
        self.assertFalse(Payment.objects.filter(order=sale).exists())
        self.assertEqual(balance.quantity, Decimal("4"))
        self.assertFalse(StockMovement.objects.filter(order=sale).exists())

        # Once purchasing/receiving adds the missing unit, retain separate
        # SALE/RECIPE movements while deducting the combined five units.
        from apps.inventory.models import StockReason
        from apps.inventory.services import apply_manual_stock_change
        received = apply_manual_stock_change(
            tenant_id=self.tenant.pk, outlet=self.outlet,
            menu_item=ingredient, quantity_change=Decimal("1"),
            reason=StockReason.RECEIVE, user=self.user,
            note="Supplier delivery brings item to available quantity",
        )
        self.assertEqual(received.quantity_change, Decimal("1"))
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("5"))
        payment, replayed = record_order_payment(
            order=sale, user=self.user, amount=Decimal("10000"),
            method="cash", idempotency_key="combined-stock-now-available",
        )
        self.assertFalse(replayed)
        self.assertEqual(payment.amount, Decimal("10000"))
        sale.refresh_from_db()
        self.assertTrue(sale.is_paid)
        self.assertEqual(sale.status, "closed")
        balance.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal("0"))
        self.assertEqual(
            sorted(StockMovement.objects.filter(order=sale).values_list(
                "reason", "quantity_change",
            )),
            [("recipe", Decimal("-2")), ("sale", Decimal("-3"))],
        )

    def test_cashier_catalogue_search_finds_active_plu_in_current_tenant(self):
        category = MenuCategory.objects.create(tenant=self.tenant, name="Checkout products")
        product = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Fresh tomato",
            sku="TOM-LOCAL", barcode="1002003004005", unit_price=Decimal("1500"),
            track_inventory=False,
        )
        profile = SupermarketSkuProfile.objects.create(
            tenant=self.tenant, menu_item=product, plu_code="3137",
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        found = self.client.get(url, {"catalogue_q": "3137"})
        self.assertEqual(found.status_code, 200)
        ids = [
            item.pk for group in found.context["pos_menu_categories"]
            for item in group["menu_items"]
        ]
        self.assertIn(product.pk, ids)
        catalogue = self.client.get(reverse("staff-menu"), {"q": "3137"})
        self.assertEqual(catalogue.status_code, 200)
        self.assertContains(catalogue, "Fresh tomato")

        # Inactive PLU profiles must not appear in manual product search.
        profile.is_active = False
        profile.save(update_fields=["is_active"])
        missing = self.client.get(url, {"catalogue_q": "3137"})
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(missing.context["pos_menu_categories"])
        inactive_catalogue = self.client.get(reverse("staff-menu"), {"q": "3137"})
        self.assertNotContains(inactive_catalogue, "Fresh tomato")

        # A different tenant may use the same PLU without leaking its product.
        other = Tenant.objects.create(name="Neighbour store", slug="plu-neighbour-store")
        other_cat = MenuCategory.objects.create(tenant=other, name="Neighbour products")
        foreign_product = MenuItem.objects.create(
            tenant=other, category=other_cat, name="Neighbour apples",
            sku="OTHER-PLU", unit_price=Decimal("700"), track_inventory=False,
        )
        SupermarketSkuProfile.objects.create(
            tenant=other, menu_item=foreign_product, plu_code="3137",
        )
        scoped = self.client.get(url, {"catalogue_q": "3137"})
        self.assertEqual(scoped.status_code, 200)
        self.assertNotContains(scoped, "Neighbour apples")
        self.assertFalse(scoped.context["pos_menu_categories"])

    def test_barcode_and_plu_scans_merge_without_overwriting_original_source(self):
        from apps.pos.services import add_supermarket_line_by_code
        category = MenuCategory.objects.create(tenant=self.tenant, name="Scan provenance")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Milk carton",
            sku="MILK-CARTON", barcode="7776665554443",
            unit_price=Decimal("2800"), track_inventory=False,
        )
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant, menu_item=item, plu_code="4091",
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        first = add_supermarket_line_by_code(
            order=order, code="7776665554443", quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(first.pricing_source, "barcode")
        second = add_supermarket_line_by_code(
            order=order, code="4091", quantity=Decimal("2"), user=self.user,
        )
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(second.quantity, Decimal("3"))
        self.assertEqual(second.pricing_source, "barcode")
        self.assertEqual(order.total, Decimal("8400.00"))
        self.assertEqual(order.lines.filter(is_voided=False).count(), 1)

    def test_retail_weighted_scan_keeps_separate_lines_and_source(self):
        from apps.pos.services import add_supermarket_line_by_code
        from apps.catalog.models import WeightedPricingMode
        category = MenuCategory.objects.create(tenant=self.tenant, name="Measured")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Loose rice",
            sku="RICE-LOOSE", barcode="7654321012345",
            unit_price=Decimal("5200"), track_inventory=False,
        )
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant, menu_item=item, plu_code="5082",
            weighted_pricing_mode=WeightedPricingMode.WEIGHTED,
            allow_fractional_quantity=True,
        )
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        first = add_supermarket_line_by_code(
            order=order, code="7654321012345", quantity=Decimal("1.125"), user=self.user,
        )
        second = add_supermarket_line_by_code(
            order=order, code="5082", quantity=Decimal("0.500"), user=self.user,
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            list(order.lines.order_by("created_at").values_list("pricing_source", flat=True)),
            ["weighted", "weighted"],
        )
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("8450.00"))

    def test_scan_first_form_reaches_existing_server_side_checkout(self):
        cat = MenuCategory.objects.create(tenant=self.tenant, name="Grocery")
        MenuItem.objects.create(
            tenant=self.tenant, category=cat, name="Sugar", sku="SUG-001",
            barcode="1234567890123", unit_price=Decimal("4500"), track_inventory=False,
        )
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        url = reverse("staff-order-detail", kwargs={"order_id": order.id})
        response = self.client.get(url)
        assert response.status_code == 200
        assert b"Scan items" in response.content
        assert b"data-retail-scan-form" in response.content
        assert b"data-retail-scan-status" in response.content
        scanned = self.client.post(
            url, {"action": "scan_add_line", "code": "1234567890123", "quantity": "2"},
        )
        assert scanned.status_code == 302
        order.refresh_from_db()
        assert order.lines.filter(menu_item__sku="SUG-001", is_voided=False).exists()

    def test_cash_tender_helper_is_supermarket_only_and_ledger_uses_existing_payment(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            total=Decimal("9000"), subtotal=Decimal("9000"),
        )
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert response.status_code == 200
        # Checkout staff can view the change calculator only when payment is allowed.
        if response.context["can_record_payment"] and response.context["payment_form"]:
            assert "Cash &amp; change".encode("utf-8") in response.content
            assert b"data-retail-cash-received" in response.content
            assert b"data-balance-due" in response.content
            assert b"Enter cash received." in response.content
            assert b"The cash-received figure is not the sale amount" not in response.content

    def test_payment_form_contains_stable_retry_key(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            total=Decimal("5000"), subtotal=Decimal("5000"),
        )
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert page.status_code == 200
        if page.context["can_record_payment"]:
            assert b'name="payment_request_key"' in page.content
            assert page.context["payment_request_key"]
            from apps.staff.views_ops import StaffOrderDetailView
            from django.test import RequestFactory
            key = str(page.context["payment_request_key"])
            request = RequestFactory().post("/", {"payment_request_key": key})
            assert StaffOrderDetailView._payment_request_key(request) == key
            assert StaffOrderDetailView._payment_request_key(request) == key

    def test_retail_payment_ajax_updates_balance_and_completes_without_redirect(self):
        import uuid
        from apps.pos.models import Payment

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("5000"), total=Decimal("5000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})

        partial = self.client.post(
            url,
            {
                "action": "record_payment",
                "amount": "2000",
                "method": "cash",
                "payment_request_key": str(uuid.uuid4()),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(partial.status_code, 200)
        self.assertEqual(partial["Content-Type"], "application/json")
        partial_data = partial.json()
        self.assertTrue(partial_data["ok"])
        self.assertFalse(partial_data["completed"])
        self.assertEqual(Decimal(partial_data["paid"]), Decimal("2000"))
        self.assertEqual(Decimal(partial_data["due"]), Decimal("3000"))
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)

        final = self.client.post(
            url,
            {
                "action": "record_payment",
                "amount": "3000",
                "method": "cash",
                "payment_request_key": str(uuid.uuid4()),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(final.status_code, 200)
        final_data = final.json()
        self.assertTrue(final_data["ok"])
        self.assertTrue(final_data["completed"])
        self.assertEqual(Decimal(final_data["paid"]), Decimal("5000"))
        self.assertEqual(Decimal(final_data["due"]), Decimal("0"))
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "closed")
        self.assertEqual(Payment.objects.filter(order=order).count(), 2)

    def test_supermarket_walk_in_needs_no_table_or_customer(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
        )
        assert order.customer_id is None
        assert order.table_id is None
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert page.status_code == 200
        assert b"Scan items" in page.content
        assert b"Customer record" not in page.content
        assert b"Tab:" not in page.content
        assert b"Charge to folio" not in page.content

    def test_retail_hold_without_label_uses_basket_reference(self):
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, created_by=self.user)
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        response = self.client.post(url, {"action": "hold_order", "hold_label": "   "})
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.table_label, "Held " + order.bill_reference)
        self.assertEqual(response["Location"], reverse("staff-retail-pos-entry"))
        self.assertNotIn(str(order.pk), response["Location"])

    def test_held_sale_search_all_retail_outlets_recovers_older_basket(self):
        """All-retail register view must search held receipt/notes, not only 50 newest."""
        # Tenant product configuration must explicitly include both outlet
        # types, otherwise access controls correctly hide the retail outlet.
        settings = self.tenant.settings
        settings.business_lines = ["supermarket", "retail"]
        settings.save(update_fields=["business_lines"])
        second = Outlet.objects.create(
            site=self.outlet.site, name="Second Retail Till",
            outlet_type=OutletType.RETAIL,
        )
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.outlets.add(second)
        held = Order.objects.create(
            tenant=self.tenant, outlet=second, created_by=self.user,
            table_label="Return with blue bag", currency="UGX",
        )
        # Newer unrelated baskets occupy the default first page of held cards.
        for idx in range(51):
            Order.objects.create(
                tenant=self.tenant, outlet=self.outlet, created_by=self.user,
                table_label=f"Queued shopper {idx:02}", currency="UGX",
            )
        session = self.client.session
        from apps.staff.middleware import STAFF_SESSION_OUTLET_ALL
        session[STAFF_SESSION_OUTLET_KEY] = STAFF_SESSION_OUTLET_ALL
        session.save()
        response = self.client.get(reverse("staff-orders"), {"q": "Return with blue bag"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, held.table_label)
        self.assertContains(response, str(held.pk))
        self.assertEqual(len(response.context["held_tabs"]), 1)

    def test_customer_monitor_shows_brief_thanks_after_full_payment_without_items(self):
        """Full settlement acknowledges purchase without leaving customer data visible."""
        import uuid
        from apps.pos.models import OrderLine
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("5000"), total=Decimal("5000"),
        )
        OrderLine.objects.create(
            order=sale, label="Private basket item",
            quantity=Decimal("1"), unit_price=Decimal("5000"),
            line_total=Decimal("5000"),
        )
        cashier = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        screen = reverse("staff-retail-customer-display", kwargs={"order_id": sale.pk})
        self.assertEqual(self.client.get(cashier).status_code, 200)
        self.assertContains(self.client.get(screen), "Private basket item")
        paid = self.client.post(cashier, {
            "action": "record_payment", "amount": "5000", "method": "cash",
            "payment_request_key": str(uuid.uuid4()),
        })
        self.assertEqual(paid.status_code, 302)
        sale.refresh_from_db()
        self.assertTrue(sale.is_paid)
        self.assertEqual(sale.status, "closed")
        screen_after = self.client.get(screen)
        self.assertEqual(screen_after.status_code, 200)
        self.assertContains(screen_after, "Payment complete. Thank you")
        self.assertNotContains(screen_after, "Private basket item")
        self.assertNotContains(screen_after, "5000")
        # Completed sale must never become an active checkout again on GET.
        self.client.get(cashier)
        self.assertContains(self.client.get(screen), 'data-active-order=""')
        session = self.client.session
        key = next(key for key in session.keys()
                   if key.startswith("customer_screen_active:") and key.endswith(":completed"))
        session[key] = {"order": str(sale.pk), "until": 1}
        session.save()
        expired = self.client.get(screen)
        self.assertNotContains(expired, "Payment complete. Thank you")
        self.assertContains(expired, "Welcome! Your basket will appear here")

    def test_customer_monitor_refuses_stale_held_basket_pointer(self):
        """A held basket stays hidden even if its old session pointer survives."""
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("5000"), total=Decimal("5000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        monitor = reverse("staff-retail-customer-display", kwargs={"order_id": sale.pk})
        # Loading the cashier activates this basket in its register session.
        self.assertEqual(self.client.get(url).status_code, 200)
        live = self.client.get(monitor)
        self.assertEqual(live.status_code, 200)
        self.assertContains(live, 'data-active-order="' + str(sale.pk) + '"')
        # Simulate a stale pointer after the basket is parked in the database.
        Order.objects.filter(pk=sale.pk).update(table_label="Returning shopper")
        parked = self.client.get(monitor)
        self.assertEqual(parked.status_code, 200)
        self.assertContains(parked, 'data-active-order=""')
        self.assertNotContains(parked, 'data-active-order="' + str(sale.pk) + '"')
        # Ordinary GET on a parked basket must not reactivate it.
        self.client.get(url)
        still_parked = self.client.get(monitor)
        self.assertContains(still_parked, 'data-active-order=""')
        # Explicit cashier POST resumes the original basket and its display.
        resumed = self.client.post(url, {"action": "resume_order"})
        self.assertEqual(resumed.status_code, 302)
        self.assertEqual(self.client.get(url).status_code, 200)
        active_again = self.client.get(monitor)
        self.assertContains(active_again, 'data-active-order="' + str(sale.pk) + '"')

    def test_held_sale_is_protected_at_shared_service_boundary(self):
        """Direct API/service callers cannot bypass the cashier's hold state."""
        from rest_framework.exceptions import ValidationError
        from apps.pos.models import OrderLine, Payment
        from apps.pos.services import (
            adjust_open_order_line_quantity, record_order_payment,
            apply_supermarket_line_discount,
        )

        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            table_label="Shopper collecting balance", currency="UGX",
            subtotal=Decimal("6000"), total=Decimal("6000"),
        )
        line = OrderLine.objects.create(
            order=sale, label="Service", quantity=Decimal("2"),
            unit_price=Decimal("3000"), line_total=Decimal("6000"),
        )
        with self.assertRaises(ValidationError):
            adjust_open_order_line_quantity(
                order=sale, line=line, quantity=Decimal("3"), user=self.user,
            )
        with self.assertRaises(ValidationError):
            apply_supermarket_line_discount(
                order=sale, line=line, discount_amount=Decimal("500"),
                user=self.user,
            )
        with self.assertRaises(ValidationError):
            record_order_payment(
                order=sale, user=self.user, amount=Decimal("1000"),
                method="cash", idempotency_key="parked-direct-payment",
            )
        self.assertFalse(Payment.objects.filter(order=sale).exists())
        line.refresh_from_db()
        sale.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(sale.total, Decimal("6000"))

    def test_discount_nullable_service_line_avoids_postgresql_outer_join_lock(self):
        from apps.pos.models import OrderLine
        from apps.pos.services import apply_supermarket_line_discount
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("6000"), total=Decimal("6000"),
        )
        line = OrderLine.objects.create(
            order=order, menu_item=None, label="Service",
            quantity=Decimal("2"), unit_price=Decimal("3000"),
            line_total=Decimal("6000"),
        )
        with CaptureQueriesContext(connection) as queries:
            discounted = apply_supermarket_line_discount(
                order=order, line=line, user=self.user,
                discount_amount=Decimal("500"),
            )
        if connection.vendor == "postgresql":
            line_locks = [
                q["sql"].upper() for q in queries
                if "FOR UPDATE" in q["sql"].upper() and "POS_ORDERLINE" in q["sql"].upper()
            ]
            self.assertTrue(line_locks)
            self.assertTrue(all("LEFT OUTER JOIN" not in sql for sql in line_locks))
        self.assertEqual(discounted.line_total, Decimal("5500"))
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("5500"))

    def test_held_sale_denies_payment_and_quantity_edit_until_resumed(self):
        """A parked basket is inactive even when an old checkout tab remains open."""
        from apps.pos.models import OrderLine, Payment
        import uuid

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("6000"), total=Decimal("6000"),
            table_label="Customer fetching an item",
        )
        line = OrderLine.objects.create(
            order=order, label="Laundry service", quantity=Decimal("2"),
            unit_price=Decimal("3000"), line_total=Decimal("6000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        before_payments = Payment.objects.filter(order=order).count()
        blocked_payment = self.client.post(url, {
            "action": "record_payment", "amount": "3000", "method": "cash",
            "payment_request_key": str(uuid.uuid4()),
        })
        self.assertEqual(blocked_payment.status_code, 302)
        self.assertEqual(blocked_payment["Location"], reverse("staff-orders"))
        self.assertEqual(Payment.objects.filter(order=order).count(), before_payments)
        blocked_qty = self.client.post(
            url, {"action": "adjust_line_qty", "line_id": str(line.pk),
                  "quantity": "3"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(blocked_qty.status_code, 409)
        self.assertFalse(blocked_qty.json()["ok"])
        self.assertIn("Resume", blocked_qty.json()["message"])
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("2"))

        resumed = self.client.post(url, {"action": "resume_order"})
        self.assertEqual(resumed.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.table_label, "")
        updated = self.client.post(
            url, {"action": "adjust_line_qty", "line_id": str(line.pk),
                  "quantity": "3"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["ok"])
        self.assertEqual(Decimal(updated.json()["total"]), Decimal("9000"))

    def test_held_partial_basket_resume_reuses_original_order_and_tenders(self):
        """Parking must free the register; resuming cannot create another sale."""
        from apps.pos.models import Payment
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("35000"), total=Decimal("35000"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=sale, amount=Decimal("15000"),
            method="cash", idempotency_key="hold-resume-preserve-deposit",
            recorded_by=self.user,
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        held = self.client.post(url, {"action": "hold_order", "hold_label": "Returned shopper"})
        self.assertEqual(held.status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.table_label, "Returned shopper")
        # The cashier can serve another shopper without changing this basket.
        other = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX",
        )
        list_page = self.client.get(reverse("staff-orders"))
        self.assertEqual(list_page.status_code, 200)
        self.assertContains(list_page, "Returned shopper")
        self.assertContains(list_page, 'name="action" value="resume_order"')
        count_before = Order.objects.filter(tenant=self.tenant).count()
        resumed = self.client.post(url, {"action": "resume_order"})
        self.assertEqual(resumed.status_code, 302)
        self.assertEqual(resumed["Location"], url)
        sale.refresh_from_db()
        self.assertEqual(sale.table_label, "")
        self.assertEqual(sale.status, "open")
        self.assertFalse(sale.is_paid)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), count_before)
        self.assertTrue(Order.objects.filter(pk=other.pk).exists())
        self.assertEqual(Payment.objects.get(order=sale).amount, Decimal("15000"))
        checkout = self.client.get(url)
        self.assertEqual(checkout.status_code, 200)
        self.assertEqual(checkout.context["balance_due"], Decimal("20000"))
        # Replaying resume is harmless; it cannot erase or duplicate a tender.
        self.client.post(url, {"action": "resume_order"})
        self.assertEqual(Payment.objects.filter(order=sale).count(), 1)

    def test_resume_rejected_for_completed_or_other_tenant_basket(self):
        another = Tenant.objects.create(name="Another Seller", slug="other-resume-tenant")
        other_site = Site.objects.create(tenant=another, name="Second shop")
        other_outlet = Outlet.objects.create(
            site=other_site, name="Other till", outlet_type=OutletType.SUPERMARKET,
        )
        foreign = Order.objects.create(
            tenant=another, outlet=other_outlet, table_label="Other shopper",
            currency="UGX",
        )
        foreign_url = reverse("staff-order-detail", kwargs={"order_id": foreign.pk})
        denied = self.client.post(foreign_url, {"action": "resume_order"})
        self.assertEqual(denied.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.table_label, "Other shopper")

        settled = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            table_label="No longer held", status="closed", is_paid=True,
            currency="UGX",
        )
        settled_url = reverse("staff-order-detail", kwargs={"order_id": settled.pk})
        denied = self.client.post(settled_url, {"action": "resume_order"})
        self.assertEqual(denied.status_code, 302)
        settled.refresh_from_db()
        self.assertEqual(settled.table_label, "No longer held")

    def test_partial_cash_hold_resume_and_mixed_payment_closes_one_sale(self):
        """One basket retains its deposit and closes only when all tenders settle."""
        import uuid
        from apps.pos.models import Payment

        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("35000.00"), total=Decimal("35000.00"),
            currency="UGX",
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})

        def pay(amount, method):
            return self.client.post(url, {
                "action": "record_payment", "amount": str(amount),
                "method": method, "payment_request_key": str(uuid.uuid4()),
            })

        first = pay("15000.00", "cash")
        self.assertEqual(first.status_code, 302)
        sale.refresh_from_db()
        self.assertFalse(sale.is_paid)
        self.assertEqual(sale.status, "open")
        self.assertEqual(
            sum(Payment.objects.filter(order=sale).values_list("amount", flat=True), Decimal("0")),
            Decimal("15000.00"),
        )

        held = self.client.post(url, {"action": "hold_order"})
        self.assertEqual(held.status_code, 302)
        self.assertEqual(held["Location"], reverse("staff-retail-pos-entry"))
        sale.refresh_from_db()
        self.assertTrue(sale.table_label)
        self.assertFalse(sale.is_paid)

        # A GET may inspect the parked basket, but must not resume it.
        parked = self.client.get(url)
        self.assertEqual(parked.status_code, 200)
        self.assertTrue(Order.objects.get(pk=sale.pk).table_label)
        # Explicitly resume the original basket, not a new sale.
        activation = self.client.post(url, {"action": "resume_order"})
        self.assertEqual(activation.status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.table_label, "")
        resumed = self.client.get(url)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.context["balance_due"], Decimal("20000.00"))

        last = pay("20000.00", "mobile_money")
        self.assertEqual(last.status_code, 302)
        sale.refresh_from_db()
        self.assertTrue(sale.is_paid)
        self.assertEqual(sale.status, "closed")
        self.assertEqual(Payment.objects.filter(order=sale).count(), 2)
        self.assertEqual(
            set(Payment.objects.filter(order=sale).values_list("method", flat=True)),
            {"cash", "mobile_money"},
        )
        receipt = self.client.get(reverse("staff-order-print", kwargs={"order_id": sale.pk}))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, "35000.00")
        # Small thermal receipts must identify each part of the mixed tender,
        # not hide the ledger behind the A4-only print class.
        self.assertContains(receipt, "Cash")
        self.assertContains(receipt, "Mobile money")
        self.assertContains(receipt, "Net paid UGX 35000.00")
        self.assertContains(receipt, "Balance UGX 0.00")
        self.assertContains(receipt, "Paid in full")
        self.assertNotContains(receipt, "Payment outstanding")
        self.assertContains(receipt, "Tax UGX")
        from pathlib import Path
        print_template = (Path(__file__).resolve().parents[1] /
                          "apps/staff/templates/staff/order_print.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="Recorded payments"', print_template)
        self.assertNotIn('<div class="a4only">\\n      <h2 class="muted">Payments', print_template)


    def test_repeated_partial_payment_key_never_double_charges(self):
        import uuid
        from apps.pos.models import Payment
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("35000"), total=Decimal("35000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        payload = {
            "action": "record_payment", "amount": "15000", "method": "cash",
            "payment_request_key": str(uuid.uuid4()),
        }
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(Payment.objects.filter(order=sale).count(), 1)
        sale.refresh_from_db()
        self.assertFalse(sale.is_paid)

    def test_overpayment_cannot_be_booked_as_extra_revenue(self):
        """50,000 tender for a 35,000 basket must record at most 35,000."""
        import uuid
        from apps.pos.models import Payment
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("35000.00"), total=Decimal("35000.00"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        response = self.client.post(url, {
            "action": "record_payment", "amount": "50000.00",
            "method": "cash", "payment_request_key": str(uuid.uuid4()),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Payment.objects.filter(order=sale).exists())
        sale.refresh_from_db()
        self.assertFalse(sale.is_paid)
        accepted = self.client.post(url, {
            "action": "record_payment", "amount": "35000.00",
            "method": "cash", "payment_request_key": str(uuid.uuid4()),
        })
        self.assertEqual(accepted.status_code, 302)
        sale.refresh_from_db()
        self.assertTrue(sale.is_paid)
        self.assertEqual(Payment.objects.get(order=sale).amount, Decimal("35000.00"))

    def test_resumed_partial_sale_shows_balance_and_next_payment_guidance(self):
        from apps.pos.models import Payment
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("35000.00"), total=Decimal("35000.00"),
            table_label="Held " + "returning shopper",
        )
        Payment.objects.create(
            tenant=self.tenant, order=sale, amount=Decimal("15000.00"),
            method="cash", idempotency_key="resumed-payment-guidance",
            recorded_by=self.user,
        )
        url = reverse("staff-order-detail", kwargs={"order_id": sale.pk})
        parked = self.client.get(url)
        self.assertEqual(parked.status_code, 200)
        self.assertTrue(parked.context["retail_held"])
        self.assertFalse(parked.context["can_record_payment"])
        self.assertFalse(parked.context["can_modify_open_order"])
        self.assertEqual(parked.context["balance_due"], Decimal("20000.00"))
        self.assertContains(parked, "This basket is on hold.")
        self.assertContains(parked, "Resume this basket")
        self.assertContains(parked, 'name="action" value="resume_order"')
        self.assertNotContains(parked, '<form method="post" class="row g-2 align-items-end" data-pos-payment-form>')
        self.assertNotContains(parked, '<form method="post" class="fizo-retail-stepper" data-fizo-qty-form')
        self.assertEqual(self.client.post(url, {"action": "resume_order"}).status_code, 302)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["retail_held"])
        if response.context["can_record_payment"]:
            self.assertContains(response, "Paid UGX 15000.00")
            self.assertContains(response, "Due UGX 20000.00")
            self.assertContains(response, "reference-partial-payment")
            self.assertEqual(response.context["payment_form"].initial["amount"], Decimal("20000.00"))

    def test_part_paid_receipt_identifies_balance_without_marking_sale_paid(self):
        from apps.pos.models import Payment
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("35000.00"),
            total=Decimal("35000.00"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, amount=Decimal("15000.00"),
            method="cash", idempotency_key="receipt-part-paid-test",
            recorded_by=self.user,
        )
        response = self.client.get(reverse("staff-order-print", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Net paid UGX 15000.00")
        self.assertContains(response, "Balance UGX 20000.00")
        self.assertContains(response, "Payment outstanding")
        self.assertNotContains(response, "Paid in full")
        order.refresh_from_db()
        self.assertEqual(order.status, "open")
        self.assertFalse(order.is_paid)

    def test_held_partial_payment_visible_in_lanes_and_searchable(self):
        """Cashier sees outstanding balance and can locate an older parked sale."""
        from apps.pos.models import Payment
        sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("35000"), total=Decimal("35000"),
            table_label="Customer collecting balance",
        )
        Payment.objects.create(
            tenant=self.tenant, order=sale, amount=Decimal("15000"),
            method="cash", idempotency_key="held-deposit-test",
            recorded_by=self.user,
        )
        url = reverse("staff-orders") + "?q=Customer%20collecting%20balance"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer collecting balance")
        self.assertContains(response, "20000.00")
        self.assertContains(response, "15000.00")
        self.assertContains(response, 'name="action" value="resume_order"')
        self.assertContains(response, "Resume basket")

    def test_quick_create_idempotency_returns_same_basket_on_retry(self):
        import uuid

        url = reverse("staff-order-quick-create")
        token = str(uuid.uuid4())
        first = self.client.post(url, {"quick_create_key": token})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 1)
        second = self.client.post(url, {"quick_create_key": token})
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(first["Location"], second["Location"])
        held = self.client.post(url, {"quick_create_key": str(uuid.uuid4()), "mode": "hold"})
        self.assertEqual(held.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 2)

    def test_held_basket_note_is_single_line_and_whitespace_normalized(self):
        response = self.client.post(reverse("staff-order-quick-create"), {
            "mode": "hold",
            "hold_label": "  Sarah  \n  counter   2  ",
            "quick_create_key": str(__import__("uuid").uuid4()),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get(tenant=self.tenant).table_label, "Sarah counter 2")

    def test_held_basket_rejects_oversize_reference_without_creating_order(self):
        response = self.client.post(reverse("staff-order-quick-create"), {
            "mode": "hold",
            "hold_label": "X" * 65,
            "quick_create_key": str(__import__("uuid").uuid4()),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)

    def test_legacy_walkin_action_starts_unlabeled_sale(self):
        response = self.client.post(reverse("staff-order-quick-create"), {
            "mode": "walkin",
            "quick_create_key": str(__import__("uuid").uuid4()),
        })
        self.assertEqual(response.status_code, 302)
        sale = Order.objects.get(tenant=self.tenant)
        self.assertEqual(sale.table_label, "")
        self.assertIn(str(sale.pk), response["Location"])

    def test_quick_create_rejects_unsupported_action_without_opening_sale(self):
        url = reverse("staff-order-quick-create")
        response = self.client.post(url, {"mode": "settle", "quick_create_key": str(__import__("uuid").uuid4())})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)

    def test_quick_create_rejects_malformed_request_key(self):
        response = self.client.post(reverse("staff-order-quick-create"), {
            "quick_create_key": "not-a-uuid"
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.filter(tenant=self.tenant).count(), 0)

    def test_stock_quantity_service_never_silently_rounds_excess_precision(self):
        from rest_framework.exceptions import ValidationError
        from apps.pos.services.orders import normalize_supermarket_quantity

        category = MenuCategory.objects.create(tenant=self.tenant, name="Precision test")
        item = MenuItem.objects.create(
            tenant=self.tenant, category=category, name="Whole unit item",
            unit_price=Decimal("1500"),
        )
        self.assertEqual(
            normalize_supermarket_quantity(menu_item=item, quantity=Decimal("2")),
            Decimal("2.000"),
        )
        for quantity in (Decimal("1.5"), Decimal("1.0004")):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                normalize_supermarket_quantity(menu_item=item, quantity=quantity)
        SupermarketSkuProfile.objects.create(
            tenant=self.tenant, menu_item=item, allow_fractional_quantity=True,
        )
        self.assertEqual(
            normalize_supermarket_quantity(menu_item=item, quantity=Decimal("1.125")),
            Decimal("1.125"),
        )
        with self.assertRaises(ValidationError):
            normalize_supermarket_quantity(menu_item=item, quantity=Decimal("1.1255"))


    def test_supermarket_order_list_uses_basket_labels(self):
        page = self.client.get(reverse("staff-orders"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Held baskets")
        # A cashier cannot create a held basket until the register shift is open.
        self.assertContains(page, "Open shift first")
        self.assertNotContains(page, ">Hold basket</button>")

    def test_retail_tender_guard_is_independent_of_scan_input(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("4500"), total=Decimal("4500"),
        )
        response = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert response.status_code == 200
        if response.context["can_record_payment"]:
            assert b"data-retail-cash-panel" in response.content
            assert b"data-retail-cash-received" in response.content
            assert b"Number.isSafeInteger(cents)" in response.content
            assert b"Enter a valid cash amount." in response.content
        if response.context["scan_add_form"]:
            assert b"at most three decimal places" in response.content
            assert b"data-retail-scan-form" in response.content

    def test_retail_payment_form_has_stable_key_and_double_submit_guard(self):
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            total=Decimal("5000"), subtotal=Decimal("5000"),
        )
        page = self.client.get(reverse("staff-order-detail", kwargs={"order_id": order.pk}))
        assert page.status_code == 200
        if page.context["can_record_payment"]:
            assert b"data-pos-payment-form" in page.content
            assert b'name="payment_request_key"' in page.content
            assert b"paymentPending" in page.content
            assert b"Recording payment" in page.content

    def test_invalid_async_quantity_returns_explanation_not_redirect(self):
        from apps.pos.models import OrderLine
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            total=Decimal("1500"), subtotal=Decimal("1500"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Bottled Water", quantity=Decimal("1"),
            unit_price=Decimal("1500"), line_total=Decimal("1500"),
        )
        response = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": order.pk}),
            {"action": "adjust_line_qty", "line_id": str(line.pk), "quantity": "invalid"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertFalse(response.json()["ok"])
        self.assertTrue(response.json()["message"])
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("1"))

    def test_retail_return_rejects_a_line_from_another_tenant(self):
        """Never apply a different tenant's line to the current tenant's order."""
        from apps.pos.models import OrderLine, SupermarketLineReturn
        from apps.pos.services import process_supermarket_line_return

        other = Tenant.objects.create(name="Other Shop", slug="other-shop-return")
        other_site = Site.objects.create(tenant=other, name="Other Site")
        other_outlet = Outlet.objects.create(
            site=other_site, name="Other Till", outlet_type=OutletType.SUPERMARKET,
        )
        our_order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", total=Decimal("12000"),
            subtotal=Decimal("12000"), status="closed", is_paid=True,
        )
        other_order = Order.objects.create(
            tenant=other, outlet=other_outlet, currency="UGX",
            total=Decimal("12000"), subtotal=Decimal("12000"),
            status="closed", is_paid=True,
        )
        foreign_line = OrderLine.objects.create(
            order=other_order, label="Foreign service", quantity=Decimal("1"),
            unit_price=Decimal("12000"), line_total=Decimal("12000"),
        )
        with self.assertRaises(OrderLine.DoesNotExist):
            process_supermarket_line_return(
                order=our_order, line=foreign_line, quantity=Decimal("1"),
                reason="Cross-tenant probe", restock=False, user=self.user,
            )
        self.assertFalse(
            SupermarketLineReturn.objects.filter(order=our_order).exists()
        )

    def test_closed_service_line_return_does_not_lock_nullable_product_join(self):
        """A non-stock service return must work on PostgreSQL without LEFT JOIN locks."""
        from apps.pos.models import OrderLine, SupermarketLineReturn
        from apps.pos.services import process_supermarket_line_return

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("24000"), total=Decimal("24000"),
            status="closed", is_paid=True,
        )
        line = OrderLine.objects.create(
            order=order, menu_item=None, label="Laundry Service",
            quantity=Decimal("2"), unit_price=Decimal("12000"),
            line_total=Decimal("24000"),
        )
        with CaptureQueriesContext(connection) as queries:
            returned = process_supermarket_line_return(
                order=order, line=line, quantity=Decimal("1"),
                reason="Customer service adjustment", restock=False, user=self.user,
            )
        if connection.vendor == "postgresql":
            line_locks = [
                q["sql"].upper() for q in queries
                if "FOR UPDATE" in q["sql"].upper() and "POS_ORDERLINE" in q["sql"].upper()
            ]
            self.assertTrue(line_locks, "Expected PostgreSQL return-line row lock")
            self.assertTrue(all("LEFT OUTER JOIN" not in sql for sql in line_locks))
        self.assertEqual(returned.tenant_id, self.tenant.pk)
        self.assertEqual(returned.order_line_id, line.pk)
        self.assertEqual(returned.quantity, Decimal("1"))
        self.assertFalse(returned.restocked)
        self.assertEqual(
            SupermarketLineReturn.objects.filter(order=order, order_line=line).count(), 1
        )

    def test_quantity_service_locks_nullable_product_line_without_outer_join(self):
        """PostgreSQL must not FOR UPDATE a nullable menu_item LEFT JOIN."""
        from apps.pos.models import OrderLine
        from apps.pos.services import adjust_open_order_line_quantity

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("12000"), total=Decimal("12000"),
        )
        line = OrderLine.objects.create(
            order=order, menu_item=None, label="Laundry Service",
            quantity=Decimal("1"), unit_price=Decimal("12000"),
            line_total=Decimal("12000"),
        )
        with CaptureQueriesContext(connection) as queries:
            changed = adjust_open_order_line_quantity(
                order=order, line=line, quantity=Decimal("2"), user=self.user,
            )
        if connection.vendor == "postgresql":
            line_locks = [
                q["sql"].upper() for q in queries
                if "FOR UPDATE" in q["sql"].upper() and "POS_ORDERLINE" in q["sql"].upper()
            ]
            self.assertTrue(line_locks, "Expected PostgreSQL order-line row lock")
            self.assertTrue(all("LEFT OUTER JOIN" not in sql for sql in line_locks))
        changed.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(changed.quantity, Decimal("2"))
        self.assertEqual(changed.line_total, Decimal("24000"))
        self.assertEqual(order.total, Decimal("24000"))

    def test_ajax_quantity_update_recalculates_due_after_partial_payment(self):
        """Retail edit response must distinguish gross sale and unpaid balance."""
        from apps.pos.models import OrderLine, Payment
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("6000"), total=Decimal("6000"),
        )
        line = OrderLine.objects.create(
            order=order, label="Laundry", quantity=Decimal("2"),
            unit_price=Decimal("3000"), line_total=Decimal("6000"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, recorded_by=self.user,
            amount=Decimal("2000"), idempotency_key="ajax-quantity-partial",
        )
        response = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": order.pk}),
            {"action": "adjust_line_qty", "line_id": str(line.pk), "quantity": "3"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["currency"], "UGX")
        self.assertEqual(Decimal(data["quantity"]), Decimal("3"))
        self.assertEqual(Decimal(data["line_total"]), Decimal("9000"))
        self.assertEqual(Decimal(data["subtotal"]), Decimal("9000"))
        self.assertEqual(Decimal(data["total"]), Decimal("9000"))
        self.assertEqual(Decimal(data["paid"]), Decimal("2000"))
        self.assertEqual(Decimal(data["due"]), Decimal("7000"))
        order.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(order.total, Decimal("9000"))
        self.assertEqual(line.quantity, Decimal("3"))

    def test_quantity_ajax_response_updates_without_redirect(self):
        from apps.pos.models import OrderLine
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("3000"), total=Decimal("3000"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Bottled Water", quantity=Decimal("2"),
            unit_price=Decimal("1500"), line_total=Decimal("3000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        for quantity, total in (("3", "4500.00"), ("1", "1500.00")):
            response = self.client.post(
                url, {"action": "adjust_line_qty", "line_id": str(line.pk),
                      "quantity": quantity},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertTrue(response.json()["ok"])
            self.assertEqual(Decimal(response.json()["total"]), Decimal(total))
            self.assertEqual(Decimal(response.json()["quantity"]), Decimal(quantity))

    def test_quantity_increase_and_decrease_render_checkout_after_redirect(self):
        from apps.pos.models import OrderLine
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("3000"), total=Decimal("3000"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Bottled Water", quantity=Decimal("2"),
            unit_price=Decimal("1500"), line_total=Decimal("3000"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        for quantity, expected_total in (("3", Decimal("4500")), ("1", Decimal("1500"))):
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    url,
                    {"action": "adjust_line_qty", "line_id": str(line.pk),
                     "quantity": quantity},
                    follow=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Bottled Water")
                line.refresh_from_db()
                order.refresh_from_db()
                self.assertEqual(line.quantity, Decimal(quantity))
                self.assertEqual(order.total, expected_total)

    def test_part_paid_quantity_reduction_surfaces_error_not_http_500(self):
        from apps.pos.models import OrderLine, Payment
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("3000"), total=Decimal("3000"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Bottled Water", quantity=Decimal("2"),
            unit_price=Decimal("1500"), line_total=Decimal("3000"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, recorded_by=self.user,
            amount=Decimal("2500"), idempotency_key="quantity-http-safety",
        )
        response = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": order.pk}),
            {"action": "adjust_line_qty", "line_id": str(line.pk), "quantity": "1"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Refund UGX 1000.00 before applying this reduction")
        self.assertNotContains(response, "ErrorDetail(")
        line.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(order.total, Decimal("3000"))

    def test_refunded_partial_tender_allows_quantity_reduction_and_full_cancel(self):
        from apps.pos.models import OrderLine, Payment, Refund, OrderStatus
        from apps.pos.services import (
            adjust_open_order_line_quantity, cancel_open_unpaid_order,
        )
        from apps.staff.services.orders_display import order_payment_totals

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("3000"), total=Decimal("3000"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Bottled Water", quantity=Decimal("2"),
            unit_price=Decimal("1500"), line_total=Decimal("3000"),
        )
        payment = Payment.objects.create(
            tenant=self.tenant, order=order, amount=Decimal("2500"),
            recorded_by=self.user, idempotency_key="cancel-partpay-p",
        )
        Refund.objects.create(
            tenant=self.tenant, order=order, payment=payment,
            amount=Decimal("1500"), recorded_by=self.user,
            idempotency_key="cancel-partpay-r1",
        )
        adjust_open_order_line_quantity(
            order=order, line=line, quantity=Decimal("1"), user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("1500"))
        self.assertEqual(order_payment_totals(order), (Decimal("1000"), Decimal("500")))
        with self.assertRaises(Exception):
            cancel_open_unpaid_order(order=order, user=self.user)
        Refund.objects.create(
            tenant=self.tenant, order=order, payment=payment,
            amount=Decimal("1000"), recorded_by=self.user,
            idempotency_key="cancel-partpay-r2",
        )
        cancel_open_unpaid_order(order=order, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(order.payments.count(), 1)
        self.assertEqual(order.refunds.count(), 2)

    def test_quantity_reduction_cannot_drop_below_money_already_taken(self):
        from rest_framework.exceptions import ValidationError
        from apps.pos.models import OrderLine, Payment
        from apps.pos.services import adjust_open_order_line_quantity

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("3000"), total=Decimal("3000"), currency="UGX",
        )
        line = OrderLine.objects.create(
            order=order, label="Water", quantity=Decimal("2"),
            unit_price=Decimal("1500"), line_total=Decimal("3000"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, recorded_by=self.user,
            amount=Decimal("2500"), idempotency_key="part-paid-quantity-test",
        )
        with self.assertRaises(ValidationError):
            adjust_open_order_line_quantity(
                order=order, line=line, quantity=Decimal("1"), user=self.user,
            )
        line.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(order.total, Decimal("3000"))
        self.assertEqual(order.payments.count(), 1)

    def test_part_paid_basket_can_be_held_but_not_voided(self):
        from rest_framework.exceptions import ValidationError
        from apps.pos.models import Payment, OrderStatus
        from apps.pos.services import hold_open_order, cancel_open_unpaid_order

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("10000"), total=Decimal("10000"), currency="UGX",
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, amount=Decimal("4000"),
            idempotency_key="partial-payment-cannot-cancel",
            recorded_by=self.user,
        )
        held = hold_open_order(order=order, hold_label="Customer returning", user=self.user)
        self.assertEqual(held.table_label, "Customer returning")
        self.assertEqual(held.status, OrderStatus.OPEN)
        self.assertFalse(held.is_paid)
        with self.assertRaises(ValidationError):
            cancel_open_unpaid_order(order=order, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.OPEN)
        self.assertEqual(
            Payment.objects.filter(order=order).count(), 1,
        )

    def test_successful_retail_void_redirects_to_fresh_pos_entry(self):
        import uuid
        from apps.pos.models import OrderStatus
        from apps.staff.terminal import set_member_pin

        manager_user = User.objects.create_user(
            email="void-approver@test.local", password="TestPass9!",
        )
        approver = Membership.objects.create(
            user=manager_user, tenant=self.tenant, role=MembershipRole.OUTLET_MANAGER,
        )
        approver.sites.add(self.outlet.site)
        approver.outlets.add(self.outlet)
        set_member_pin(approver, "573951")
        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            subtotal=Decimal("2500"), total=Decimal("2500"), currency="UGX",
        )
        response = self.client.post(
            reverse("staff-order-detail", kwargs={"order_id": order.pk}),
            {
                "action": "void_order",
                "void_request_key": str(uuid.uuid4()),
                "reason": "Customer changed their mind",
                "approver_id": str(approver.pk),
                "approver_pin": "573951",
            },
        )
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertRedirects(
            response, reverse("staff-retail-pos-entry"), fetch_redirect_response=False,
        )

    def test_next_sale_is_post_only(self):
        url = reverse("staff-order-quick-create")
        before = Order.objects.filter(tenant=self.tenant).count()
        response = self.client.get(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before
        response = self.client.post(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before + 1


    def test_unpaid_basket_line_removal_ajax_updates_without_redirect(self):
        from apps.pos.models import OrderLine

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        keep = OrderLine.objects.create(
            order=order, label="Keep item", quantity=Decimal("1"),
            unit_price=Decimal("7000.00"), line_total=Decimal("7000.00"),
        )
        remove = OrderLine.objects.create(
            order=order, label="Remove item", quantity=Decimal("1"),
            unit_price=Decimal("3000.00"), line_total=Decimal("3000.00"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        page = self.client.get(url)
        self.assertContains(page, "data-retail-void-line-form")
        self.assertContains(page, "data-retail-basket-mutation-status")

        response = self.client.post(
            url,
            {"action": "void_line", "line_id": str(remove.pk), "reason": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        remove.refresh_from_db()
        keep.refresh_from_db()
        order.refresh_from_db()
        self.assertTrue(remove.is_voided)
        self.assertFalse(keep.is_voided)
        self.assertEqual(order.total, Decimal("7000.00"))

    def test_part_paid_ajax_line_removal_requires_refund_before_reducing_total(self):
        from apps.pos.models import OrderLine, Payment, PaymentMethod

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        OrderLine.objects.create(
            order=order, label="Keep item", quantity=Decimal("1"),
            unit_price=Decimal("7000.00"), line_total=Decimal("7000.00"),
        )
        remove = OrderLine.objects.create(
            order=order, label="Remove item", quantity=Decimal("1"),
            unit_price=Decimal("3000.00"), line_total=Decimal("3000.00"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=order, amount=Decimal("8000.00"),
            method=PaymentMethod.CASH, idempotency_key="part-paid-void-guard",
            recorded_by=self.user,
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        response = self.client.post(
            url,
            {"action": "void_line", "line_id": str(remove.pk), "reason": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["refund_required"])
        self.assertIn("Refund UGX 1000.00", body["message"])
        remove.refresh_from_db()
        order.refresh_from_db()
        self.assertFalse(remove.is_voided)
        self.assertEqual(order.total, Decimal("10000.00"))


    def test_physical_return_ajax_is_idempotent_and_rejects_changed_retry(self):
        import uuid
        from apps.pos.models import OrderLine, OrderStatus, SupermarketLineReturn

        order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", status=OrderStatus.CLOSED, is_paid=True,
            subtotal=Decimal("10000.00"), total=Decimal("10000.00"),
        )
        line = OrderLine.objects.create(
            order=order, label="Returned pack", quantity=Decimal("2.000"),
            unit_price=Decimal("5000.00"), line_total=Decimal("10000.00"),
        )
        url = reverse("staff-order-detail", kwargs={"order_id": order.pk})
        key = str(uuid.uuid4())
        payload = {
            "action": "line_return",
            "line_return_request_key": key,
            "line_id": str(line.pk),
            "quantity": "1.000",
            "reason": "Exchange without cash refund",
        }

        first = self.client.post(
            url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["ok"])
        self.assertIn("next_request_key", first.json())
        self.assertEqual(
            SupermarketLineReturn.objects.filter(
                tenant=self.tenant, idempotency_key=key,
            ).count(),
            1,
        )

        replay = self.client.post(
            url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertIn("already recorded", replay.json()["message"].lower())
        self.assertEqual(
            SupermarketLineReturn.objects.filter(
                tenant=self.tenant, idempotency_key=key,
            ).count(),
            1,
        )

        changed = dict(payload)
        changed["quantity"] = "0.500"
        rejected = self.client.post(
            url, changed, HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertFalse(rejected.json()["ok"])
        self.assertIn("different details", rejected.json()["message"].lower())
        self.assertEqual(
            SupermarketLineReturn.objects.filter(order=order).count(),
            1,
        )
