from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, Promotion
from apps.customers.models import Customer
from apps.inventory.models import StockBalance
from apps.pos.models import (
    CustomerPriceBookAssignment,
    Order,
    PriceBook,
    PriceBookRule,
    WholesalePriceRule,
)
from apps.pos.services.orders import (
    add_line_to_open_order,
    adjust_open_order_line_quantity,
    apply_promotion_to_order,
    apply_supermarket_line_discount,
)
from apps.pos.services.price_books import reprice_open_retail_order_for_customer
from apps.pos.services.wholesale import apply_wholesale_tier
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class CustomerPriceBookTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Price Book Shop", slug="price-book-shop")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "customers", "promotions", "workspace"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Checkout", outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(email="pricebooks@test.local", password="Password9!")
        self.membership = Membership.objects.create(
            user=self.user, tenant=self.tenant, role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.category = MenuCategory.objects.create(tenant=self.tenant, name="General")
        self.item = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Cooking Oil",
            sku="OIL-1",
            unit_price=Decimal("10000"),
            track_inventory=False,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="VIP Customer",
            phone="0700000000",
            created_by=self.user,
        )
        self.book = PriceBook.objects.create(
            tenant=self.tenant,
            name="VIP",
            code="VIP",
            is_active=True,
        )
        self.rule_one = PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            menu_item=self.item,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9000"),
        )
        self.rule_five = PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            menu_item=self.item,
            minimum_quantity=Decimal("5"),
            unit_price=Decimal("8000"),
        )
        CustomerPriceBookAssignment.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            price_book=self.book,
            assigned_by=self.user,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _order(self, customer=None):
        return Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            customer=customer,
            created_by=self.user,
            currency="UGX",
        )

    def test_assigned_customer_gets_price_book_on_normal_retail_add(self):
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order,
            menu_item=self.item,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9000"))
        self.assertEqual(line.price_book_rule, self.rule_one)
        self.assertEqual(line.price_book_base_unit_price, Decimal("10000"))
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("9000.00"))

    def test_rapid_add_merge_crosses_quantity_tier_on_same_basket_line(self):
        order = self._order(self.customer)
        first = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        for _ in range(4):
            add_line_to_open_order(
                order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
            )
        first.refresh_from_db()
        self.assertEqual(order.lines.filter(is_voided=False).count(), 1)
        self.assertEqual(first.quantity, Decimal("5"))
        self.assertEqual(first.unit_price, Decimal("8000"))
        self.assertEqual(first.price_book_rule, self.rule_five)
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("40000.00"))

    def test_quantity_minus_reverts_to_lower_customer_tier(self):
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("5"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("8000"))
        adjust_open_order_line_quantity(
            order=order,
            line=line,
            quantity=Decimal("4"),
            user=self.user,
        )
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("4"))
        self.assertEqual(line.unit_price, Decimal("9000"))
        self.assertEqual(line.price_book_rule, self.rule_one)

    def test_removing_customer_from_open_unpaid_basket_restores_base_price(self):
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("2"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9000"))
        order.customer = None
        order.save(update_fields=["customer", "updated_at"])
        changed, frozen = reprice_open_retail_order_for_customer(order=order, user=self.user)
        self.assertFalse(frozen)
        self.assertEqual(changed, 1)
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("10000"))
        self.assertIsNone(line.price_book_rule_id)
        self.assertIsNone(line.price_book_base_unit_price)

    def test_promotion_and_manual_discount_do_not_stack_with_customer_price_book(self):
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        promo = Promotion.objects.create(
            tenant=self.tenant,
            name="Weekend",
            discount_percent=Decimal("10"),
            starts_at=timezone.now(),
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        with self.assertRaises(ValidationError):
            apply_supermarket_line_discount(
                order=order,
                line=line,
                user=self.user,
                discount_percent=Decimal("5"),
            )

    def test_wholesale_override_clears_customer_book_and_lower_quantity_restores_it(self):
        WholesalePriceRule.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            minimum_quantity=Decimal("10"),
            unit_price=Decimal("7000"),
            is_active=True,
            created_by=self.user,
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order,
            menu_item=self.item,
            quantity=Decimal("10"),
            user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("8000"))
        self.assertEqual(line.price_book_rule, self.rule_five)

        line, _already = apply_wholesale_tier(
            order=order,
            line_id=line.pk,
            membership=self.membership,
            user=self.user,
        )
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("7000"))
        self.assertEqual(line.pricing_source, "wholesale")
        self.assertIsNone(line.price_book_rule_id)
        self.assertIsNone(line.price_book_base_unit_price)

        adjust_open_order_line_quantity(
            order=order,
            line=line,
            quantity=Decimal("4"),
            user=self.user,
        )
        line.refresh_from_db()
        self.assertEqual(line.pricing_source, "menu")
        self.assertEqual(line.unit_price, Decimal("9000"))
        self.assertEqual(line.price_book_rule, self.rule_one)
        self.assertEqual(line.price_book_base_unit_price, Decimal("10000"))

    def test_category_rule_prices_product_without_sku_rule(self):
        category_rule = PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            category=self.category,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9500"),
        )
        self.rule_one.is_active = False
        self.rule_one.save(update_fields=["is_active"])
        self.rule_five.is_active = False
        self.rule_five.save(update_fields=["is_active"])
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9500"))
        self.assertEqual(line.price_book_rule, category_rule)

    def test_brand_rule_beats_category_rule(self):
        self.item.brand = "Acme"
        self.item.save(update_fields=["brand"])
        self.rule_one.is_active = False
        self.rule_one.save(update_fields=["is_active"])
        self.rule_five.is_active = False
        self.rule_five.save(update_fields=["is_active"])
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            category=self.category,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9600"),
        )
        brand_rule = PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            brand="acme",
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9400"),
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9400"))
        self.assertEqual(line.price_book_rule, brand_rule)

    def test_family_rule_beats_brand_and_category_rule(self):
        family = ProductFamily.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Cooking oils",
        )
        self.item.product_family = family
        self.item.brand = "Acme"
        self.item.save(update_fields=["product_family", "brand"])
        self.rule_one.is_active = False
        self.rule_one.save(update_fields=["is_active"])
        self.rule_five.is_active = False
        self.rule_five.save(update_fields=["is_active"])
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            category=self.category,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9700"),
        )
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            brand="ACME",
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9600"),
        )
        family_rule = PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            product_family=family,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("9300"),
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9300"))
        self.assertEqual(line.price_book_rule, family_rule)

    def test_sku_rule_beats_all_broader_targets_even_if_broader_price_is_lower(self):
        family = ProductFamily.objects.create(
            tenant=self.tenant,
            category=self.category,
            name="Cooking oils",
        )
        self.item.product_family = family
        self.item.brand = "Acme"
        self.item.save(update_fields=["product_family", "brand"])
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            category=self.category,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("5000"),
        )
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            brand="Acme",
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("6000"),
        )
        PriceBookRule.objects.create(
            tenant=self.tenant,
            price_book=self.book,
            product_family=family,
            minimum_quantity=Decimal("1"),
            unit_price=Decimal("7000"),
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9000"))
        self.assertEqual(line.price_book_rule, self.rule_one)

    def test_scoped_rule_admin_requires_exactly_one_target(self):
        response = self.client.post(
            reverse("console-org-price-book-rule-create", args=[self.book.pk]),
            {
                "menu_item": str(self.item.pk),
                "category": str(self.category.pk),
                "product_family": "",
                "brand": "",
                "minimum_quantity": "2",
                "unit_price": "8500",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose exactly one target")
        self.assertFalse(
            PriceBookRule.objects.filter(
                price_book=self.book,
                minimum_quantity=Decimal("2"),
            ).exists()
        )

    def test_price_book_outlet_scope_falls_back_to_base_price_elsewhere(self):
        other = Outlet.objects.create(
            site=self.site, name="Branch 2", outlet_type=OutletType.SUPERMARKET,
        )
        self.book.outlets.add(self.outlet)
        other_order = Order.objects.create(
            tenant=self.tenant,
            outlet=other,
            customer=self.customer,
            created_by=self.user,
            currency="UGX",
        )
        line = add_line_to_open_order(
            order=other_order,
            menu_item=self.item,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("10000"))
        self.assertIsNone(line.price_book_rule_id)

    def test_price_book_admin_ui_creates_tier_and_moves_customer_assignment(self):
        second_book = PriceBook.objects.create(
            tenant=self.tenant, name="Employee", code="EMP", is_active=True,
        )
        detail = self.client.get(reverse("console-org-price-book-detail", args=[second_book.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Assigned customers")

        assign = self.client.post(
            reverse("console-org-price-book-assignment", args=[second_book.pk]),
            {
                "action": "assign",
                "customer": str(self.customer.pk),
                "price_book": str(second_book.pk),
            },
        )
        self.assertEqual(assign.status_code, 302)
        assignment = CustomerPriceBookAssignment.objects.get(customer=self.customer)
        self.assertEqual(assignment.price_book, second_book)

        tier = self.client.post(
            reverse("console-org-price-book-rule-create", args=[second_book.pk]),
            {
                "menu_item": str(self.item.pk),
                "minimum_quantity": "2",
                "unit_price": "8500",
                "is_active": "on",
            },
        )
        self.assertEqual(tier.status_code, 302)
        self.assertTrue(
            PriceBookRule.objects.filter(
                price_book=second_book,
                menu_item=self.item,
                minimum_quantity=Decimal("2"),
                unit_price=Decimal("8500"),
            ).exists()
        )

    def test_used_price_rule_remove_deactivates_instead_of_breaking_history(self):
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order, menu_item=self.item, quantity=Decimal("1"), user=self.user,
        )
        self.assertEqual(line.price_book_rule, self.rule_one)
        response = self.client.post(
            reverse(
                "console-org-price-book-rule-delete",
                args=[self.book.pk, self.rule_one.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.rule_one.refresh_from_db()
        self.assertFalse(self.rule_one.is_active)
        line.refresh_from_db()
        self.assertEqual(line.price_book_rule, self.rule_one)

    def test_hospitality_only_workspace_cannot_open_price_book_admin(self):
        other = Tenant.objects.create(name="Restaurant prices", slug="restaurant-prices")
        TenantSettings.objects.create(
            tenant=other,
            business_lines=["restaurant"],
            enabled_staff_modules=["pos"],
        )
        user = User.objects.create_user(email="restaurant-pricebook@test.local", password="Password9!")
        Membership.objects.create(user=user, tenant=other, role=MembershipRole.OWNER)
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(other.pk)
        session.save()
        response = self.client.get(reverse("console-org-price-books"))
        self.assertEqual(response.status_code, 404)

    def test_customer_price_book_falls_back_when_trusted_margin_floor_would_be_breached(self):
        settings_obj = self.tenant.settings
        settings_obj.retail_min_margin_percent = Decimal("20")
        settings_obj.save(update_fields=["retail_min_margin_percent", "updated_at"])
        self.item.track_inventory = True
        self.item.save(update_fields=["track_inventory", "updated_at"])
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("10"),
            average_unit_cost=Decimal("7500"),
            cost_basis_complete=True,
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order,
            menu_item=self.item,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("10000"))
        self.assertIsNone(line.price_book_rule_id)
        self.assertIsNone(line.price_book_base_unit_price)

    def test_customer_price_book_is_not_blocked_by_incomplete_cost_basis(self):
        settings_obj = self.tenant.settings
        settings_obj.retail_min_margin_percent = Decimal("20")
        settings_obj.save(update_fields=["retail_min_margin_percent", "updated_at"])
        self.item.track_inventory = True
        self.item.save(update_fields=["track_inventory", "updated_at"])
        StockBalance.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.item,
            quantity=Decimal("10"),
            average_unit_cost=None,
            cost_basis_complete=False,
        )
        order = self._order(self.customer)
        line = add_line_to_open_order(
            order=order,
            menu_item=self.item,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertEqual(line.unit_price, Decimal("9000"))
        self.assertEqual(line.price_book_rule, self.rule_one)

