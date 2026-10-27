from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, Promotion
from apps.customers.models import Customer
from apps.pos.models import Order, Payment, PaymentMethod
from apps.pos.services.orders import (
    add_line_to_open_order,
    apply_promotion_to_order,
    apply_supermarket_line_discount,
    remove_promotion_from_order,
)
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.staff.services import promotions_selectable_for_order
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class TargetedPromotionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Targeted promos", slug="targeted-promos")
        TenantSettings.objects.create(
            tenant=self.tenant,
            business_lines=["supermarket"],
            enabled_staff_modules=["pos", "promotions", "workspace"],
            default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site,
            name="Checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.user = User.objects.create_user(
            email="targeted-promos@test.local",
            password="Password9!",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=MembershipRole.OWNER,
        )
        self.membership.sites.add(self.site)
        self.membership.outlets.add(self.outlet)
        self.food = MenuCategory.objects.create(
            tenant=self.tenant,
            name="Food",
        )
        self.home = MenuCategory.objects.create(
            tenant=self.tenant,
            name="Home",
        )
        self.family = ProductFamily.objects.create(
            tenant=self.tenant,
            category=self.food,
            name="Cooking oils",
        )
        self.oil = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.food,
            product_family=self.family,
            name="Cooking Oil",
            brand="Acme",
            sku="OIL-1",
            unit_price=Decimal("10000"),
            track_inventory=False,
        )
        self.soap = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.home,
            name="Soap",
            brand="CleanCo",
            sku="SOAP-1",
            unit_price=Decimal("20000"),
            track_inventory=False,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def _order(self):
        return Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            currency="UGX",
        )

    def _promotion(self, **kwargs):
        defaults = {
            "tenant": self.tenant,
            "name": "Offer",
            "discount_percent": Decimal("10"),
            "starts_at": timezone.now() - timedelta(minutes=1),
            "ends_at": timezone.now() + timedelta(days=1),
            "is_active": True,
        }
        defaults.update(kwargs)
        return Promotion.objects.create(**defaults)

    def test_product_percent_promotion_discounts_only_matching_line_subtotal(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(menu_item=self.oil)

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()

        self.assertEqual(order.subtotal, Decimal("30000.00"))
        self.assertEqual(order.discount_amount, Decimal("1000.00"))
        self.assertEqual(order.total, Decimal("29000.00"))

    def test_category_fixed_promotion_caps_discount_to_matching_lines(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Food fixed",
            discount_percent=None,
            discount_amount=Decimal("15000"),
            category=self.food,
        )

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()

        self.assertEqual(order.discount_amount, Decimal("10000.00"))
        self.assertEqual(order.total, Decimal("20000.00"))

    def test_family_and_brand_targets_match_case_insensitively(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        family_offer = self._promotion(
            name="Family",
            product_family=self.family,
            discount_percent=Decimal("5"),
        )
        brand_offer = self._promotion(
            name="Brand",
            brand="acme",
            discount_percent=Decimal("7"),
        )

        selectable_ids = set(
            promotions_selectable_for_order(order).values_list("id", flat=True)
        )
        self.assertIn(family_offer.pk, selectable_ids)
        self.assertIn(brand_offer.pk, selectable_ids)

    def test_nonmatching_target_is_not_selectable_and_fails_closed_at_apply_time(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Soap only",
            menu_item=self.soap,
        )

        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

    def test_whole_basket_promotion_keeps_existing_behavior(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Whole basket")

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()

        self.assertEqual(order.discount_amount, Decimal("3000.00"))
        self.assertEqual(order.total, Decimal("27000.00"))

    def test_manual_line_discount_blocks_order_promotion_and_hides_it_from_selector(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="No stacking")
        apply_supermarket_line_discount(
            order=order,
            line=line,
            user=self.user,
            discount_percent=Decimal("5"),
        )

        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

    def test_applied_targeted_percent_recalculates_when_matching_quantity_changes(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Live target", menu_item=self.oil)
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("1000.00"))

        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        order.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("2"))
        self.assertEqual(order.subtotal, Decimal("20000.00"))
        self.assertEqual(order.discount_amount, Decimal("2000.00"))
        self.assertEqual(order.total, Decimal("18000.00"))

    def test_applied_targeted_offer_drops_to_zero_when_target_is_voided(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Target removed", menu_item=self.oil)
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        from apps.pos.services.orders import void_open_order_line
        void_open_order_line(
            order=order,
            line=line,
            reason="Customer changed mind",
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("0.00"))
        self.assertEqual(order.applied_promotion, promo)

    def test_manual_discount_cannot_be_added_after_promotion(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Promo first")
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        with self.assertRaises(ValidationError):
            apply_supermarket_line_discount(
                order=order,
                line=line,
                user=self.user,
                discount_percent=Decimal("5"),
            )

    def test_offer_can_be_removed_and_reapplied_before_payment(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Reversible")

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("1000.00"))
        self.assertEqual(order.applied_promotion, promo)

        remove_promotion_from_order(order=order, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertIsNone(order.applied_promotion_id)
        self.assertEqual(order.total, Decimal("10000.00"))

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("1000.00"))
        self.assertEqual(order.applied_promotion, promo)

    def test_async_remove_offer_updates_checkout_without_page_refresh_contract(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Async removable")
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)

        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {"action": "remove_promotion"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["discount"], "0.00")
        order.refresh_from_db()
        self.assertIsNone(order.applied_promotion_id)

    def test_payment_start_freezes_promotion_changes(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Frozen after tender")
        Payment.objects.create(
            tenant=self.tenant,
            order=order,
            amount=Decimal("1000"),
            method=PaymentMethod.CASH,
            idempotency_key="promo-freeze-apply",
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

        second = self._order()
        add_line_to_open_order(
            order=second,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        apply_promotion_to_order(order=second, promotion=promo, user=self.user)
        Payment.objects.create(
            tenant=self.tenant,
            order=second,
            amount=Decimal("1000"),
            method=PaymentMethod.CASH,
            idempotency_key="promo-freeze-remove",
            recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            remove_promotion_from_order(order=second, user=self.user)
        second.refresh_from_db()
        self.assertEqual(second.applied_promotion, promo)
        self.assertEqual(second.discount_amount, Decimal("1000.00"))

    def test_manager_form_rejects_multiple_targets(self):
        response = self.client.post(
            reverse("staff-promotion-create"),
            {
                "name": "Bad scope",
                "menu_item": str(self.oil.pk),
                "product_family": "",
                "category": str(self.food.pk),
                "brand": "",
                "discount_percent": "10",
                "discount_amount": "",
                "min_order_subtotal": "",
                "starts_at": (timezone.localtime() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose only one promotion target")
        self.assertFalse(
            Promotion.objects.filter(tenant=self.tenant, name="Bad scope").exists()
        )


    def test_minimum_target_quantity_controls_selector_and_apply(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Buy two oils",
            menu_item=self.oil,
            min_target_quantity=Decimal("2"),
        )
        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertTrue(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("2000.00"))

    def test_coupon_offer_is_hidden_from_dropdown_and_requires_matching_code(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Secret coupon",
            coupon_code="SAVE10",
        )
        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(
                order=order,
                promotion=promo,
                user=self.user,
                coupon_code="WRONG",
            )
        apply_promotion_to_order(
            order=order,
            promotion=promo,
            user=self.user,
            coupon_code="save10",
        )
        order.refresh_from_db()
        self.assertEqual(order.applied_promotion, promo)
        self.assertEqual(order.discount_amount, Decimal("1000.00"))

    def test_async_checkout_accepts_coupon_code_without_exposing_coupon_offer(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Code only",
            coupon_code="CODEONLY",
        )
        page = self.client.get(reverse("staff-order-detail", args=[order.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="coupon_code"')
        self.assertNotContains(page, f'value="{promo.pk}"')

        response = self.client.post(
            reverse("staff-order-detail", args=[order.pk]),
            {
                "action": "apply_promotion",
                "promotion": "",
                "coupon_code": "codeonly",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        order.refresh_from_db()
        self.assertEqual(order.applied_promotion, promo)

    def test_global_paid_redemption_limit_blocks_future_use(self):
        promo = self._promotion(
            name="One redemption",
            max_redemptions=1,
        )
        used = self._order()
        used.applied_promotion = promo
        used.is_paid = True
        used.save(update_fields=["applied_promotion", "is_paid", "updated_at"])

        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

    def test_per_customer_paid_limit_does_not_block_anonymous_customer(self):
        promo = self._promotion(
            name="Once per customer",
            max_redemptions_per_customer=1,
        )
        customer = Customer.objects.create(
            tenant=self.tenant,
            name="Known shopper",
            created_by=self.user,
        )
        used = self._order()
        used.customer = customer
        used.applied_promotion = promo
        used.is_paid = True
        used.save(update_fields=["customer", "applied_promotion", "is_paid", "updated_at"])

        same_customer = self._order()
        same_customer.customer = customer
        same_customer.save(update_fields=["customer", "updated_at"])
        add_line_to_open_order(
            order=same_customer,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertFalse(
            promotions_selectable_for_order(same_customer).filter(pk=promo.pk).exists()
        )

        anonymous = self._order()
        add_line_to_open_order(
            order=anonymous,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertTrue(
            promotions_selectable_for_order(anonymous).filter(pk=promo.pk).exists()
        )


    def test_buy_x_get_y_same_category_makes_cheapest_qualifying_unit_free(self):
        cheaper = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.food,
            name="Small Oil",
            brand="Acme",
            sku="OIL-SMALL",
            unit_price=Decimal("5000"),
            track_inventory=False,
        )
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=cheaper,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Food BOGO",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            category=self.food,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=1,
            get_quantity=1,
        )

        self.assertTrue(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()

        self.assertEqual(order.subtotal, Decimal("15000.00"))
        self.assertEqual(order.discount_amount, Decimal("5000.00"))
        self.assertEqual(order.total, Decimal("10000.00"))

    def test_buy_x_get_y_requires_complete_set_and_whole_units(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Oil BOGO",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=1,
            get_quantity=1,
        )
        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

    def test_buy_x_get_y_respects_max_uses_per_order(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("4"),
            user=self.user,
        )
        promo = self._promotion(
            name="One BOGO set only",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=1,
            get_quantity=1,
            max_uses_per_order=1,
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("10000.00"))
        self.assertEqual(order.total, Decimal("30000.00"))

    def test_manager_form_rejects_buy_x_get_y_without_specific_target(self):
        response = self.client.post(
            reverse("staff-promotion-create"),
            {
                "name": "Bad BOGO",
                "offer_type": Promotion.OfferType.BUY_X_GET_Y,
                "menu_item": "",
                "product_family": "",
                "category": "",
                "brand": "",
                "discount_percent": "",
                "discount_amount": "",
                "min_order_subtotal": "",
                "min_target_quantity": "",
                "coupon_code": "",
                "max_redemptions": "",
                "max_redemptions_per_customer": "",
                "buy_quantity": "1",
                "get_quantity": "1",
                "max_uses_per_order": "",
                "starts_at": (timezone.localtime() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Buy X Get Y requires exactly one")
        self.assertFalse(
            Promotion.objects.filter(tenant=self.tenant, name="Bad BOGO").exists()
        )
