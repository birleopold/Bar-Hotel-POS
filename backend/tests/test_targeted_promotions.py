from types import SimpleNamespace
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, ProductLabelQueueEntry, Promotion
from apps.catalog.recipe_promo_serializers import PromotionSerializer
from apps.customers.models import Customer
from apps.pos.models import Order, Payment, PaymentMethod
from apps.pos.services.orders import (
    add_line_to_open_order,
    apply_promotion_to_order,
    apply_supermarket_line_discount,
    remove_promotion_from_order,
)
from apps.pos.services.payments import record_order_payment
from apps.pos.services.pricing_policy import (
    manual_discount_combination_block_reason,
    pricing_precedence_state,
    promotion_combination_block_reason,
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
        self.assertContains(response, "Quantity deals require exactly one")
        self.assertFalse(
            Promotion.objects.filter(tenant=self.tenant, name="Bad BOGO").exists()
        )


    def test_final_tender_rechecks_redemption_limit_after_offer_was_applied(self):
        promo = self._promotion(
            name="Last redemption",
            max_redemptions=1,
        )
        pending = self._order()
        add_line_to_open_order(
            order=pending,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        apply_promotion_to_order(order=pending, promotion=promo, user=self.user)
        pending.refresh_from_db()
        self.assertEqual(pending.total, Decimal("9000.00"))

        consumed = self._order()
        consumed.applied_promotion = promo
        consumed.is_paid = True
        consumed.status = "closed"
        consumed.save(update_fields=["applied_promotion", "is_paid", "status", "updated_at"])

        with self.assertRaises(ValidationError):
            record_order_payment(
                order=pending,
                user=self.user,
                amount=Decimal("9000.00"),
                method=PaymentMethod.CASH,
                idempotency_key="last-redemption-race",
            )
        self.assertFalse(
            Payment.objects.filter(
                order=pending,
                idempotency_key="last-redemption-race",
            ).exists()
        )
        pending.refresh_from_db()
        self.assertFalse(pending.is_paid)


    def test_buy_x_get_y_recalculates_when_basket_quantity_changes(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        promo = self._promotion(
            name="Live BOGO",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=1,
            get_quantity=1,
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("10000.00"))
        self.assertEqual(order.total, Decimal("10000.00"))

        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("20000.00"))
        self.assertEqual(order.total, Decimal("20000.00"))

        from apps.pos.services.orders import adjust_open_order_line_quantity
        line.refresh_from_db()
        adjust_open_order_line_quantity(
            order=order,
            line=line,
            quantity=Decimal("1"),
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("10000.00"))


    def test_promotion_api_serializer_matches_bogo_and_coupon_management_contract(self):
        payload = {
            "name": "API BOGO coupon",
            "offer_type": Promotion.OfferType.BUY_X_GET_Y,
            "menu_item": str(self.oil.pk),
            "product_family": None,
            "category": None,
            "brand": "",
            "discount_percent": None,
            "discount_amount": None,
            "min_order_subtotal": None,
            "min_target_quantity": "2",
            "coupon_code": "APIBOGO",
            "max_redemptions": 10,
            "max_redemptions_per_customer": 1,
            "buy_quantity": 1,
            "get_quantity": 1,
            "max_uses_per_order": 2,
            "starts_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            "ends_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "is_active": True,
            "outlet_ids": [str(self.outlet.pk)],
        }
        serializer = PromotionSerializer(
            data=payload,
            context={"request": SimpleNamespace(tenant=self.tenant)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        promo = serializer.save()
        self.assertEqual(promo.offer_type, Promotion.OfferType.BUY_X_GET_Y)
        self.assertEqual(promo.coupon_code, "APIBOGO")
        self.assertEqual(promo.buy_quantity, 1)
        self.assertEqual(promo.get_quantity, 1)
        self.assertEqual(promo.max_uses_per_order, 2)
        self.assertEqual(list(promo.outlets.values_list("pk", flat=True)), [self.outlet.pk])

    def test_promotion_api_serializer_rejects_cross_tenant_target(self):
        other = Tenant.objects.create(name="Other promo tenant", slug="other-promo-tenant")
        TenantSettings.objects.create(tenant=other, business_lines=["supermarket"])
        other_category = MenuCategory.objects.create(tenant=other, name="Other")
        other_item = MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Other item",
            unit_price=Decimal("1000"),
        )
        payload = {
            "name": "Cross tenant offer",
            "offer_type": Promotion.OfferType.STANDARD,
            "menu_item": str(other_item.pk),
            "brand": "",
            "discount_percent": "10",
            "discount_amount": None,
            "starts_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            "ends_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "is_active": True,
        }
        serializer = PromotionSerializer(
            data=payload,
            context={"request": SimpleNamespace(tenant=self.tenant)},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("menu_item", serializer.errors)

    def test_x_for_fixed_amount_discounts_complete_same_target_sets(self):
        cheaper = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.food,
            name="Small Oil Fixed",
            brand="Acme",
            sku="OIL-FIXED-SMALL",
            unit_price=Decimal("5000"),
            track_inventory=False,
        )
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=cheaper,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Any three oils for 18000",
            offer_type=Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            category=self.food,
            discount_percent=None,
            discount_amount=None,
            fixed_quantity=3,
            fixed_bundle_amount=Decimal("18000"),
        )

        self.assertTrue(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()

        self.assertEqual(order.subtotal, Decimal("25000.00"))
        self.assertEqual(order.discount_amount, Decimal("7000.00"))
        self.assertEqual(order.total, Decimal("18000.00"))

    def test_x_for_fixed_amount_respects_complete_sets_cap_and_leftovers(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("7"),
            user=self.user,
        )
        promo = self._promotion(
            name="Three oils for 25000 once",
            offer_type=Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            fixed_quantity=3,
            fixed_bundle_amount=Decimal("25000"),
            max_uses_per_order=1,
        )

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal("70000.00"))
        self.assertEqual(order.discount_amount, Decimal("5000.00"))
        self.assertEqual(order.total, Decimal("65000.00"))

    def test_x_for_fixed_amount_recalculates_with_fast_basket_quantity_changes(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("3"),
            user=self.user,
        )
        promo = self._promotion(
            name="Three for 25000 live",
            offer_type=Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            fixed_quantity=3,
            fixed_bundle_amount=Decimal("25000"),
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("5000.00"))

        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("3"),
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("10000.00"))

        from apps.pos.services.orders import adjust_open_order_line_quantity
        line.refresh_from_db()
        self.assertEqual(line.quantity, Decimal("6"))
        adjust_open_order_line_quantity(
            order=order,
            line=line,
            quantity=Decimal("5"),
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("5000.00"))

    def test_promotion_api_serializer_accepts_x_for_fixed_amount_contract(self):
        payload = {
            "name": "API three for fixed",
            "offer_type": Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            "menu_item": str(self.oil.pk),
            "product_family": None,
            "category": None,
            "brand": "",
            "discount_percent": None,
            "discount_amount": None,
            "fixed_quantity": 3,
            "fixed_bundle_amount": "25000.00",
            "max_uses_per_order": 2,
            "starts_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            "ends_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "is_active": True,
            "outlet_ids": [str(self.outlet.pk)],
        }
        serializer = PromotionSerializer(
            data=payload,
            context={"request": SimpleNamespace(tenant=self.tenant)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        promo = serializer.save()
        self.assertEqual(promo.offer_type, Promotion.OfferType.X_FOR_FIXED_AMOUNT)
        self.assertEqual(promo.fixed_quantity, 3)
        self.assertEqual(promo.fixed_bundle_amount, Decimal("25000.00"))
        self.assertEqual(promo.max_uses_per_order, 2)

    def test_x_for_fixed_amount_rejects_whole_basket_and_non_saving_configuration(self):
        invalid = Promotion(
            tenant=self.tenant,
            name="Invalid whole basket fixed",
            offer_type=Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            discount_percent=None,
            discount_amount=None,
            fixed_quantity=3,
            fixed_bundle_amount=Decimal("25000"),
            starts_at=timezone.now() - timedelta(minutes=1),
        )
        with self.assertRaises(DjangoValidationError):
            invalid.full_clean()

        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("3"),
            user=self.user,
        )
        promo = self._promotion(
            name="No fake saving",
            offer_type=Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            menu_item=self.oil,
            discount_percent=None,
            discount_amount=None,
            fixed_quantity=3,
            fixed_bundle_amount=Decimal("35000"),
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

    def test_cross_target_bogo_requires_reward_item_in_basket_and_discounts_reward(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        promo = self._promotion(
            name="Buy two oil get soap",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            reward_menu_item=self.soap,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=2,
            get_quantity=1,
        )

        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError):
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)

        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        self.assertTrue(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("20000.00"))
        self.assertEqual(order.total, Decimal("20000.00"))

    def test_cross_target_bogo_uses_cheapest_reward_unit_and_respects_cap(self):
        reward_small = MenuItem.objects.create(
            tenant=self.tenant,
            category=self.home,
            name="Small Soap Reward",
            brand="CleanCo",
            sku="SOAP-REWARD-SMALL",
            unit_price=Decimal("5000"),
            track_inventory=False,
        )
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("4"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=reward_small,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Buy oil get home reward",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            reward_category=self.home,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=2,
            get_quantity=1,
            max_uses_per_order=1,
        )

        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("5000.00"))

    def test_cross_target_bogo_recalculates_when_qualifying_quantity_drops(self):
        order = self._order()
        qualifying_line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        add_line_to_open_order(
            order=order,
            menu_item=self.soap,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(
            name="Live cross BOGO",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            menu_item=self.oil,
            reward_menu_item=self.soap,
            discount_percent=None,
            discount_amount=None,
            buy_quantity=2,
            get_quantity=1,
        )
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("20000.00"))

        from apps.pos.services.orders import adjust_open_order_line_quantity
        adjust_open_order_line_quantity(
            order=order,
            line=qualifying_line,
            quantity=Decimal("1"),
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("0.00"))

    def test_promotion_api_serializer_accepts_cross_target_bogo_and_rejects_cross_tenant_reward(self):
        payload = {
            "name": "API buy oil get soap",
            "offer_type": Promotion.OfferType.BUY_X_GET_Y,
            "menu_item": str(self.oil.pk),
            "reward_menu_item": str(self.soap.pk),
            "brand": "",
            "reward_brand": "",
            "discount_percent": None,
            "discount_amount": None,
            "buy_quantity": 1,
            "get_quantity": 1,
            "starts_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            "ends_at": (timezone.now() + timedelta(days=1)).isoformat(),
            "is_active": True,
        }
        serializer = PromotionSerializer(
            data=payload,
            context={"request": SimpleNamespace(tenant=self.tenant)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        promo = serializer.save()
        self.assertEqual(promo.reward_menu_item, self.soap)

        other = Tenant.objects.create(name="Other reward tenant", slug="other-reward-tenant")
        TenantSettings.objects.create(tenant=other, business_lines=["supermarket"])
        other_category = MenuCategory.objects.create(tenant=other, name="Other reward category")
        other_item = MenuItem.objects.create(
            tenant=other,
            category=other_category,
            name="Other reward item",
            unit_price=Decimal("1000"),
        )
        payload["name"] = "Bad cross tenant reward"
        payload["reward_menu_item"] = str(other_item.pk)
        serializer = PromotionSerializer(
            data=payload,
            context={"request": SimpleNamespace(tenant=self.tenant)},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("reward_menu_item", serializer.errors)

    def test_cross_target_bogo_overlap_fails_closed(self):
        order = self._order()
        add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        promo = self._promotion(
            name="Unsafe overlapping BOGO",
            offer_type=Promotion.OfferType.BUY_X_GET_Y,
            category=self.food,
            reward_menu_item=self.oil,
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

    def test_unconditional_item_promotion_queues_and_reconciles_markdown_label(self):
        create_url = reverse("staff-promotion-create")
        payload = {
            "name": "Oil shelf markdown",
            "offer_type": Promotion.OfferType.STANDARD,
            "menu_item": str(self.oil.pk),
            "product_family": "",
            "category": "",
            "brand": "",
            "reward_menu_item": "",
            "reward_product_family": "",
            "reward_category": "",
            "reward_brand": "",
            "discount_percent": "10",
            "discount_amount": "",
            "min_order_subtotal": "",
            "min_target_quantity": "",
            "coupon_code": "",
            "max_redemptions": "",
            "max_redemptions_per_customer": "",
            "buy_quantity": "",
            "get_quantity": "",
            "fixed_quantity": "",
            "fixed_bundle_amount": "",
            "max_uses_per_order": "",
            "starts_at": (timezone.localtime() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
            "outlets": [str(self.outlet.pk)],
        }
        response = self.client.post(create_url, payload)
        self.assertEqual(response.status_code, 302)
        promo = Promotion.objects.get(tenant=self.tenant, name="Oil shelf markdown")
        entry = ProductLabelQueueEntry.objects.get(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.oil,
            reason=ProductLabelQueueEntry.Reason.MARKDOWN,
            status=ProductLabelQueueEntry.Status.PENDING,
        )
        self.assertEqual(entry.price_snapshot, Decimal("9000.00"))
        self.assertTrue(entry.note.startswith(f"[promotion:{promo.pk}]"))

        payload["discount_percent"] = "20"
        response = self.client.post(
            reverse("staff-promotion-edit", args=[promo.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        pending = ProductLabelQueueEntry.objects.get(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.oil,
            reason=ProductLabelQueueEntry.Reason.MARKDOWN,
            status=ProductLabelQueueEntry.Status.PENDING,
        )
        self.assertEqual(pending.price_snapshot, Decimal("8000.00"))
        self.assertTrue(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=self.oil,
                reason=ProductLabelQueueEntry.Reason.MARKDOWN,
                status=ProductLabelQueueEntry.Status.DISMISSED,
            ).exists()
        )

        payload.pop("is_active")
        response = self.client.post(
            reverse("staff-promotion-edit", args=[promo.pk]),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                outlet=self.outlet,
                menu_item=self.oil,
                reason=ProductLabelQueueEntry.Reason.MARKDOWN,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).exists()
        )

    def test_conditioned_promotion_does_not_queue_misleading_markdown_label(self):
        response = self.client.post(
            reverse("staff-promotion-create"),
            {
                "name": "Coupon-only shelf unsafe",
                "offer_type": Promotion.OfferType.STANDARD,
                "menu_item": str(self.oil.pk),
                "discount_percent": "10",
                "discount_amount": "",
                "coupon_code": "ONLY10",
                "starts_at": (timezone.localtime() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
                "outlets": [str(self.outlet.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ProductLabelQueueEntry.objects.filter(
                tenant=self.tenant,
                menu_item=self.oil,
                reason=ProductLabelQueueEntry.Reason.MARKDOWN,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).exists()
        )

    def test_promotion_list_shows_paid_performance_and_recent_price_history(self):
        promo = self._promotion(name="Reported offer", menu_item=self.oil)
        Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            applied_promotion=promo,
            is_paid=True,
            status="closed",
            subtotal=Decimal("10000"),
            discount_amount=Decimal("1000"),
            total=Decimal("9000"),
            currency="UGX",
        )
        AuditEvent.objects.create(
            tenant=self.tenant,
            user=self.user,
            action="catalog.unit_price_changed",
            entity_type="menu_item",
            entity_id=str(self.oil.pk),
            payload={
                "item_name": self.oil.name,
                "outlet_id": str(self.outlet.pk),
                "outlet_name": self.outlet.name,
                "before": "9000.00",
                "after": "10000.00",
            },
        )

        response = self.client.get(reverse("staff-promotions"), {"days": "30"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reported offer")
        self.assertContains(response, "1")
        self.assertContains(response, "1000")
        self.assertContains(response, "9000")
        self.assertContains(response, "Recent price changes")
        self.assertContains(response, self.oil.name)

    def test_markdown_label_collision_does_not_overwrite_existing_promotion_task(self):
        first = self._promotion(
            name="First shelf markdown",
            menu_item=self.oil,
            discount_percent=Decimal("10"),
        )
        from apps.catalog.promotion_labels import queue_markdown_labels_for_promotion
        queue_markdown_labels_for_promotion(promotion=first, user=self.user)
        existing = ProductLabelQueueEntry.objects.get(
            tenant=self.tenant,
            outlet=self.outlet,
            menu_item=self.oil,
            reason=ProductLabelQueueEntry.Reason.MARKDOWN,
            status=ProductLabelQueueEntry.Status.PENDING,
        )
        self.assertEqual(existing.price_snapshot, Decimal("9000.00"))

        second = self._promotion(
            name="Second shelf markdown",
            menu_item=self.oil,
            discount_percent=Decimal("20"),
        )
        queued = queue_markdown_labels_for_promotion(promotion=second, user=self.user)
        self.assertEqual(queued, 0)
        existing.refresh_from_db()
        self.assertEqual(existing.price_snapshot, Decimal("9000.00"))
        self.assertTrue(existing.note.startswith(f"[promotion:{first.pk}]"))
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="promotion.markdown_label_conflict",
                entity_id=str(second.pk),
            ).exists()
        )

    def test_shared_pricing_precedence_blocks_wholesale_basket_promotions(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        line.pricing_source = "wholesale"
        line.save(update_fields=["pricing_source", "updated_at"])
        promo = self._promotion(name="Blocked by wholesale")

        state = pricing_precedence_state(order)
        self.assertTrue(state.has_wholesale)
        self.assertEqual(state.active_labels, ("Wholesale",))
        self.assertIn("Wholesale pricing is active", state.promotion_block_reason)
        self.assertEqual(
            promotion_combination_block_reason(order),
            state.promotion_block_reason,
        )
        self.assertFalse(
            promotions_selectable_for_order(order).filter(pk=promo.pk).exists()
        )
        with self.assertRaises(ValidationError) as exc:
            apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        self.assertIn("Wholesale pricing is active", str(exc.exception.detail))

    def test_shared_pricing_precedence_reports_manual_discount_and_promotion_conflict(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("1"),
            user=self.user,
        )
        promo = self._promotion(name="Policy promo")
        apply_promotion_to_order(order=order, promotion=promo, user=self.user)
        order.refresh_from_db()
        line.refresh_from_db()
        self.assertIn(
            "Remove the order promotion",
            manual_discount_combination_block_reason(order, line),
        )

        remove_promotion_from_order(order=order, user=self.user)
        apply_supermarket_line_discount(
            order=order,
            line=line,
            user=self.user,
            discount_percent=Decimal("5"),
        )
        order.refresh_from_db()
        state = pricing_precedence_state(order)
        self.assertTrue(state.has_manual_discount)
        self.assertIn("manual line discount", state.promotion_block_reason.lower())

    def test_checkout_explains_pricing_precedence_when_offer_is_blocked(self):
        order = self._order()
        line = add_line_to_open_order(
            order=order,
            menu_item=self.oil,
            quantity=Decimal("2"),
            user=self.user,
        )
        line.pricing_source = "wholesale"
        line.save(update_fields=["pricing_source", "updated_at"])

        response = self.client.get(reverse("staff-order-detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pricing rules")
        self.assertContains(response, "Active pricing: Wholesale.")
        self.assertContains(response, "Wholesale pricing is active")
        self.assertNotContains(response, "Or enter coupon code")

    def test_promotion_report_filters_by_accessible_outlet_and_exports_csv(self):
        other_outlet = Outlet.objects.create(
            site=self.site,
            name="Second checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        self.membership.outlets.add(other_outlet)
        promo = self._promotion(name="Outlet report offer", menu_item=self.oil)
        Order.objects.create(
            tenant=self.tenant,
            outlet=self.outlet,
            created_by=self.user,
            applied_promotion=promo,
            is_paid=True,
            status="closed",
            subtotal=Decimal("10000"),
            discount_amount=Decimal("1000"),
            total=Decimal("9000"),
            currency="UGX",
        )
        Order.objects.create(
            tenant=self.tenant,
            outlet=other_outlet,
            created_by=self.user,
            applied_promotion=promo,
            is_paid=True,
            status="closed",
            subtotal=Decimal("20000"),
            discount_amount=Decimal("2000"),
            total=Decimal("18000"),
            currency="UGX",
        )

        page = self.client.get(
            reverse("staff-promotions"),
            {"days": "30", "outlet": str(self.outlet.pk)},
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Outlet report offer")
        self.assertContains(page, "UGX 1000")
        self.assertContains(page, "UGX 9000")
        self.assertNotContains(page, "UGX 2000")

        exported = self.client.get(
            reverse("staff-promotions"),
            {
                "days": "30",
                "outlet": str(other_outlet.pk),
                "export": "csv",
            },
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported["Content-Type"], "text/csv")
        body = exported.content.decode("utf-8")
        self.assertIn("Outlet report offer", body)
        self.assertIn("2000", body)
        self.assertIn("18000", body)
        self.assertIn("Second checkout", body)

    def test_promotion_report_ignores_outlet_outside_membership_scope(self):
        outside_site = Site.objects.create(tenant=self.tenant, name="Restricted site")
        outside_outlet = Outlet.objects.create(
            site=outside_site,
            name="Restricted checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        promo = self._promotion(name="Scoped report offer", menu_item=self.oil)
        Order.objects.create(
            tenant=self.tenant,
            outlet=outside_outlet,
            created_by=self.user,
            applied_promotion=promo,
            is_paid=True,
            status="closed",
            subtotal=Decimal("50000"),
            discount_amount=Decimal("5000"),
            total=Decimal("45000"),
            currency="UGX",
        )

        response = self.client.get(
            reverse("staff-promotions"),
            {"days": "30", "outlet": str(outside_outlet.pk), "export": "csv"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("All accessible outlets", body)
        self.assertNotIn("Restricted checkout", body)

