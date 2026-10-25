"""D01 delivery persistence / tenant authorization; no dispatch or UI yet."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.catalog.models import MenuCategory, MenuItem
from apps.pos.models import (
    Order, OrderDelivery, OrderStatus, OutletDeliverySettings,
    Payment, PaymentMethod, RetailPickup,
)
from apps.pos.services.deliveries import (
    register_paid_order_delivery, set_outlet_delivery_enabled,
)
from apps.pos.services.pickups import register_paid_pickup
from apps.inventory.models import StockMovement
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class DeliveryPersistenceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Delivery Test Company", slug="delivery-company")
        TenantSettings.objects.create(
            tenant=self.tenant, business_lines=["supermarket"], default_currency="UGX",
        )
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.outlet = Outlet.objects.create(
            site=self.site, name="Till", outlet_type=OutletType.SUPERMARKET,
        )
        self.other_outlet = Outlet.objects.create(
            site=self.site, name="Second till", outlet_type=OutletType.RETAIL,
        )
        self.user = User.objects.create_user(
            email="delivery-manager@tests.local", password="TestPass9!",
        )
        self.member = Membership.objects.create(
            tenant=self.tenant, user=self.user, role=MembershipRole.OUTLET_MANAGER,
        )
        self.member.sites.add(self.site)
        self.member.outlets.add(self.outlet)
        self.sale = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            currency="UGX", subtotal=Decimal("9000"),
            total=Decimal("9000"), status=OrderStatus.CLOSED, is_paid=True,
        )
        Payment.objects.create(
            tenant=self.tenant, order=self.sale, recorded_by=self.user,
            method=PaymentMethod.CASH, amount=Decimal("9000"),
            idempotency_key="delivery-source-payment",
        )

    def _register(self, **overrides):
        params = dict(
            order=self.sale, user=self.user, membership=self.member,
            destination_type="address", recipient_name="Recipient",
            contact_phone="+256700123456", address="Central Kampala",
        )
        params.update(overrides)
        return register_paid_order_delivery(**params)

    def test_disabled_default_cannot_register_delivery_or_mutate_ledger(self):
        with self.assertRaises(ValidationError):
            self._register()
        self.assertFalse(OrderDelivery.objects.exists())
        self.assertFalse(OutletDeliverySettings.objects.exists())
        self.assertEqual(Payment.objects.filter(order=self.sale).count(), 1)
        self.assertFalse(StockMovement.objects.filter(order=self.sale).exists())

    def test_enabled_paid_delivery_registers_once_without_financial_reposting(self):
        setting = set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        self.assertTrue(setting.is_enabled)
        self.assertFalse(OutletDeliverySettings.objects.filter(
            outlet=self.other_outlet, is_enabled=True,
        ).exists())
        delivery, replay = self._register()
        self.assertFalse(replay)
        self.assertEqual(delivery.tenant_id, self.tenant.pk)
        self.assertEqual(delivery.outlet_id, self.outlet.pk)
        self.assertEqual(delivery.currency, "UGX")
        self.assertEqual(delivery.fee, Decimal("0"))
        self.assertEqual(delivery.status, "requested")
        again, replay = self._register()
        self.assertTrue(replay)
        self.assertEqual(again.pk, delivery.pk)
        self.assertEqual(OrderDelivery.objects.filter(order=self.sale).count(), 1)
        self.assertEqual(Payment.objects.filter(order=self.sale).count(), 1)
        self.assertFalse(StockMovement.objects.filter(order=self.sale).exists())
        with self.assertRaises(ValidationError):
            self._register(address="Changed destination after submission")
        from apps.customers.models import Customer
        buyer = Customer.objects.create(tenant=self.tenant, name="Pickup buyer")
        self.sale.customer = buyer
        self.sale.save(update_fields=["customer"])
        with self.assertRaises(ValidationError) as blocked_pickup:
            register_paid_pickup(
                order=self.sale, expected_on=__import__("datetime").date.today(),
                note="Person at shop", user=self.user, membership=self.member,
            )
        self.assertIn("assigned for delivery", str(blocked_pickup.exception))

    def test_cannot_create_delivery_against_pickup_or_underpaid_sale(self):
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        self.sale.is_paid = False
        self.sale.status = OrderStatus.OPEN
        self.sale.save(update_fields=["is_paid", "status"])
        with self.assertRaises(ValidationError):
            self._register()
        self.sale.is_paid = True
        self.sale.status = OrderStatus.CLOSED
        self.sale.save(update_fields=["is_paid", "status"])
        Payment.objects.filter(order=self.sale).delete()
        with self.assertRaises(ValidationError):
            self._register()
        Payment.objects.create(
            tenant=self.tenant, order=self.sale,
            amount=Decimal("9000"), method=PaymentMethod.CASH,
            idempotency_key="restored-source-payment", recorded_by=self.user,
        )
        RetailPickup.objects.create(
            tenant=self.tenant, order=self.sale,
            expected_on=__import__("datetime").date.today(), created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            self._register()
        self.assertFalse(OrderDelivery.objects.exists())

    def test_other_outlet_and_foreign_tenant_cannot_register(self):
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        other_tenant = Tenant.objects.create(
            name="Foreign tenant", slug="delivery-foreign-company",
        )
        foreign_site = Site.objects.create(tenant=other_tenant, name="Foreign site")
        foreign_outlet = Outlet.objects.create(
            site=foreign_site, name="Foreign till", outlet_type=OutletType.RETAIL,
        )
        foreign_sale = Order.objects.create(
            tenant=other_tenant, outlet=foreign_outlet, created_by=self.user,
            status=OrderStatus.CLOSED, is_paid=True, total=Decimal("100"),
        )
        with self.assertRaises(ValidationError):
            self._register(order=foreign_sale)
        with self.assertRaises(ValidationError):
            set_outlet_delivery_enabled(
                outlet=self.other_outlet, enabled=True,
                user=self.user, membership=self.member,
            )
        self.assertFalse(OrderDelivery.objects.exists())

    def test_driver_assignment_and_dispatch_are_audited_without_double_payment(self):
        from apps.pos.services.deliveries import (
            assign_delivery_driver, transition_order_delivery,
        )
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        delivery, replay = self._register()
        self.assertFalse(replay)
        # A driver is a worker in this tenant with outlet access, not a
        # free-text recipient or worker from another tenant.
        driver = User.objects.create_user(
            email="rider-delivery@tests.local", password="TestPass9!",
        )
        driver_member = Membership.objects.create(
            tenant=self.tenant, user=driver, role=MembershipRole.STOREKEEPER,
        )
        driver_member.sites.add(self.site)
        driver_member.outlets.add(self.outlet)
        with self.assertRaises(ValidationError):
            from apps.pos.services.deliveries import transition_order_delivery
            transition_order_delivery(
                delivery=delivery, target_status="delivered",
                user=self.user, membership=self.member,
            )
        for stage in ("accepted", "preparing", "ready"):
            delivery, replay = transition_order_delivery(
                delivery=delivery, target_status=stage,
                user=self.user, membership=self.member,
            )
            self.assertFalse(replay)
        with self.assertRaises(ValidationError):
            transition_order_delivery(
                delivery=delivery, target_status="dispatched",
                user=self.user, membership=self.member,
            )
        delivery, replay = assign_delivery_driver(
            delivery=delivery, driver=driver, user=self.user, membership=self.member,
        )
        self.assertFalse(replay)
        delivery, replay = assign_delivery_driver(
            delivery=delivery, driver=driver, user=self.user, membership=self.member,
        )
        self.assertTrue(replay)
        delivery, replay = transition_order_delivery(
            delivery=delivery, target_status="dispatched",
            user=self.user, membership=self.member,
        )
        self.assertFalse(replay)
        self.assertIsNotNone(delivery.dispatched_at)
        delivery, replay = transition_order_delivery(
            delivery=delivery, target_status="delivered",
            user=self.user, membership=self.member,
        )
        self.assertIsNotNone(delivery.delivered_at)
        with self.assertRaises(ValidationError):
            transition_order_delivery(
                delivery=delivery, target_status="dispatched",
                user=self.user, membership=self.member,
            )
        self.assertEqual(Payment.objects.filter(order=self.sale).count(), 1)
        self.assertFalse(StockMovement.objects.filter(order=self.sale).exists())

    def test_unassigned_or_other_tenant_worker_cannot_dispatch(self):
        from apps.pos.services.deliveries import (
            assign_delivery_driver, transition_order_delivery,
        )
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        delivery, _ = self._register()
        foreign = User.objects.create_user(
            email="outsider@tests.local", password="TestPass9!",
        )
        with self.assertRaises(ValidationError):
            assign_delivery_driver(
                delivery=delivery, driver=foreign,
                user=self.user, membership=self.member,
            )
        for stage in ("accepted", "preparing", "ready"):
            delivery, _ = transition_order_delivery(
                delivery=delivery, target_status=stage,
                user=self.user, membership=self.member,
            )
        with self.assertRaises(ValidationError):
            transition_order_delivery(
                delivery=delivery, target_status="dispatched",
                user=self.user, membership=self.member,
            )
        self.assertEqual(delivery.status, "ready")

    def test_delivery_requires_manager_role(self):
        self.member.role = MembershipRole.SERVER
        self.member.save(update_fields=["role"])
        with self.assertRaises(ValidationError):
            set_outlet_delivery_enabled(
                outlet=self.outlet, enabled=True,
                user=self.user, membership=self.member,
            )
