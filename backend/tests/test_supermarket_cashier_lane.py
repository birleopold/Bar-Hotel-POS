"""Staff supermarket cashier flow: scan and POST-only next basket."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, SupermarketSkuProfile
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

    def test_cashier_manager_does_not_get_owner_administration_dashboard(self):
        page = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'class="owner-home"')
        self.assertContains(page, "staff-dash-hero--modern")

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
        self.assertContains(response, "grocery-owner-console.css")
        self.assertContains(response, "grocery-console-body")
        self.assertContains(response, "grocery-console-top")
        self.assertContains(response, "grocery-console-links")
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
        self.assertContains(page, "grocery-owner-console.css")
        self.assertContains(page, "grocery-setup__layout")

    def test_owner_administration_shell_persists_after_navigation(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        for name in ("staff-dashboard", "staff-menu", "staff-inventory-balances", "staff-orders"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "owner-topbar__brand")
                self.assertContains(response, "owner-side-nav")
                self.assertContains(response, "grocery-owner-body")
                self.assertContains(response, "owner-side-nav")

    def test_grocery_owner_products_page_uses_retail_language(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        page = self.client.get(reverse("staff-menu"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Product catalogue")
        self.assertContains(page, "owner-topbar__brand")

    def test_owner_dashboard_has_guided_setup_and_actual_sections(self):
        membership = Membership.objects.get(tenant=self.tenant, user=self.user)
        membership.role = MembershipRole.OWNER
        membership.save(update_fields=["role"])
        page = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Here's your store at a glance.")
        self.assertContains(page, "Set up your store")
        self.assertContains(page, "owner-home__banner")
        self.assertContains(page, "Good afternoon!")
        self.assertContains(page, "owner-topbar__brand")
        self.assertContains(page, "owner-side-nav")
        self.assertContains(page, "owner-global-search")
        self.assertContains(page, "Common actions")
        self.assertContains(page, reverse("console-org-menu-item-create"))
        self.assertContains(page, "Needs your attention")
        self.assertContains(page, "Business activity")
        self.assertNotContains(page, "staff-dash-hero--modern")
        self.assertContains(page, "Configure payments and tills")
        self.assertContains(page, "Next recommended step:")
        self.assertContains(page, "owner-home__step-status")
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
        self.assertContains(page, "grocery-checkout.css")
        self.assertContains(page, "grocery-checkout.js")
        self.assertContains(page, "staff-pos-order-layout")
        self.assertContains(page, "data-retail-scan-form")
        self.assertContains(page, "staff-pos-order-side")

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
            assert "Cash payment · calculate change".encode("utf-8") in response.content
            assert b"data-retail-cash-received" in response.content
            assert b"data-balance-due" in response.content
            assert b"Record the due amount, not the cash tendered" in response.content

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
        assert page.status_code == 200
        assert b"Hold basket" in page.content
        assert b"Held baskets" in page.content

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
            assert b"at most two decimal places" in response.content
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

    def test_next_sale_is_post_only(self):
        url = reverse("staff-order-quick-create")
        before = Order.objects.filter(tenant=self.tenant).count()
        response = self.client.get(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before
        response = self.client.post(url)
        assert response.status_code == 302
        assert Order.objects.filter(tenant=self.tenant).count() == before + 1
