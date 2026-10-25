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

    def test_disabling_outlet_stops_new_orders_but_not_existing_delivery(self):
        from apps.pos.services.deliveries import transition_order_delivery
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        delivery, _ = self._register()
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=False, user=self.user, membership=self.member,
        )
        self.assertFalse(OutletDeliverySettings.objects.get(
            outlet=self.outlet).is_enabled)
        another_order = Order.objects.create(
            tenant=self.tenant, outlet=self.outlet, created_by=self.user,
            status=OrderStatus.CLOSED, is_paid=True,
            total=Decimal("3000"), subtotal=Decimal("3000"),
        )
        Payment.objects.create(
            tenant=self.tenant, order=another_order,
            amount=Decimal("3000"), method=PaymentMethod.CASH,
            idempotency_key="outlet-disabled-delivery-test", recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            self._register(order=another_order)
        existing, replay = transition_order_delivery(
            delivery=delivery, target_status="accepted",
            user=self.user, membership=self.member,
        )
        self.assertFalse(replay)
        self.assertEqual(existing.status, "accepted")

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

    def test_hotel_room_delivery_requires_own_checked_in_folio_and_room(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.lodging.models import (
            RoomType, Room, Reservation, ReservationStatus, Folio,
        )
        # This tenant's normal fixture enables supermarket only. Hotel access
        # must be explicitly provisioned, not bypassed by the delivery service.
        # Membership has the same Tenant object cached from setUp, including
        # its reverse settings relation. Update that instance, not a second
        # stale/uncached Settings object.
        settings = self.tenant.settings
        settings.business_lines = ["supermarket", "lodging"]
        settings.save(update_fields=["business_lines"])
        hotel = Outlet.objects.create(
            site=self.site, name="Hotel reception",
            outlet_type=OutletType.LODGING_FRONT_DESK,
        )
        self.member.outlets.add(hotel)
        set_outlet_delivery_enabled(
            outlet=hotel, enabled=True, user=self.user, membership=self.member,
        )
        room_type = RoomType.objects.create(
            tenant=self.tenant, site=self.site, name="Standard",
        )
        room = Room.objects.create(room_type=room_type, name="204")
        reservation = Reservation.objects.create(
            tenant=self.tenant, site=self.site, guest_name="Guest",
            room=room, status=ReservationStatus.CHECKED_IN,
            check_in=timezone.localdate() - timedelta(days=1),
            check_out=timezone.localdate() + timedelta(days=2),
        )
        folio = Folio.objects.create(
            tenant=self.tenant, site=self.site, guest_name="Guest",
            reservation=reservation, currency="UGX",
        )
        room_sale = Order.objects.create(
            tenant=self.tenant, outlet=hotel, created_by=self.user,
            folio=folio, currency="UGX", total=Decimal("5000"),
            subtotal=Decimal("5000"), is_paid=True,
            status=OrderStatus.CLOSED,
        )
        Payment.objects.create(
            tenant=self.tenant, order=room_sale,
            amount=Decimal("5000"), method=PaymentMethod.CASH,
            idempotency_key="hotel-room-delivery", recorded_by=self.user,
        )
        args = dict(
            order=room_sale, user=self.user, membership=self.member,
            destination_type="room",
        )
        with self.assertRaises(ValidationError):
            register_paid_order_delivery(**args, room_reference="205")
        registered, replay = register_paid_order_delivery(
            **args, room_reference="204",
        )
        self.assertFalse(replay)
        self.assertEqual(registered.destination_type, "room")
        self.assertEqual(registered.room_reference, "204")
        self.assertEqual(registered.tenant_id, self.tenant.pk)
        reservation.status = ReservationStatus.CHECKED_OUT
        reservation.save(update_fields=["status"])
        other_sale = Order.objects.create(
            tenant=self.tenant, outlet=hotel, created_by=self.user,
            folio=folio, currency="UGX", total=Decimal("5000"),
            subtotal=Decimal("5000"), is_paid=True,
            status=OrderStatus.CLOSED,
        )
        Payment.objects.create(
            tenant=self.tenant, order=other_sale,
            amount=Decimal("5000"), method=PaymentMethod.CASH,
            idempotency_key="hotel-room-after-checkout", recorded_by=self.user,
        )
        with self.assertRaises(ValidationError):
            register_paid_order_delivery(
                order=other_sale, user=self.user, membership=self.member,
                destination_type="room", room_reference="204",
            )

    def test_staff_delivery_queue_opt_in_and_register_paid_sale(self):
        from django.urls import reverse
        from apps.staff.middleware import (
            STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        url = reverse("staff-deliveries")
        view = self.client.get(url)
        self.assertEqual(view.status_code, 200)
        self.assertContains(view, "Enable delivery")
        self.assertNotContains(view, 'value="' + str(self.sale.pk) + '">')
        enabled = self.client.post(url, {
            "action":"configure", "outlet_id":str(self.outlet.pk),
            "enabled":"true",
        })
        self.assertEqual(enabled.status_code, 302)
        self.assertTrue(OutletDeliverySettings.objects.get(
            outlet=self.outlet).is_enabled)
        view = self.client.get(url)
        self.assertContains(view, str(self.sale.pk))
        registered = self.client.post(url, {
            "action":"register", "order_id":str(self.sale.pk),
            "destination_type":"address",
            "recipient_name":"Jane customer",
            "contact_phone":"0700000000",
            "address":"Kampala",
        })
        self.assertEqual(registered.status_code, 302)
        self.assertEqual(OrderDelivery.objects.filter(order=self.sale).count(), 1)
        queue = self.client.get(url)
        self.assertContains(queue, self.sale.bill_reference)
        self.assertContains(queue, "Jane customer")
        self.assertEqual(Payment.objects.filter(order=self.sale).count(), 1)
        self.assertFalse(StockMovement.objects.filter(order=self.sale).exists())

    def test_initial_staff_delivery_ui_does_not_enable_unfinished_bar_workflow(self):
        from django.urls import reverse
        from apps.staff.middleware import (
            STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
        )
        bar = Outlet.objects.create(
            site=self.site, name="Bar awaiting legal controls",
            outlet_type=OutletType.BAR,
        )
        self.member.outlets.add(bar)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        url = reverse("staff-deliveries")
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Bar awaiting legal controls")
        denied = self.client.post(url, {
            "action":"configure", "outlet_id":str(bar.pk),
            "enabled":"true",
        })
        self.assertEqual(denied.status_code, 404)
        self.assertFalse(OutletDeliverySettings.objects.filter(outlet=bar).exists())

    def test_packing_slip_uses_existing_order_and_never_exposes_other_tenant(self):
        from django.urls import reverse
        from apps.pos.models import OrderLine
        from apps.staff.middleware import (
            STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
        )
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        delivery, _ = self._register()
        OrderLine.objects.create(
            order=self.sale, label="Keep packed", quantity=Decimal("2"),
            unit_price=Decimal("4500"), line_total=Decimal("9000"),
        )
        OrderLine.objects.create(
            order=self.sale, label="Voided product", quantity=Decimal("1"),
            unit_price=Decimal("0"), line_total=Decimal("0"),
            is_voided=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        url = reverse("staff-delivery-packing-slip", kwargs={"delivery_id":delivery.pk})
        count_before = Payment.objects.filter(order=self.sale).count()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keep packed")
        self.assertNotContains(response, "Voided product")
        self.assertContains(response, "Central Kampala")
        self.assertContains(response, "Fulfillment document only")
        self.assertEqual(
            set(part.strip() for part in response["Cache-Control"].split(",")),
            {"no-store", "private"},
        )
        self.assertEqual(Payment.objects.filter(order=self.sale).count(), count_before)
        self.assertFalse(StockMovement.objects.filter(order=self.sale).exists())
        self.assertEqual(OrderDelivery.objects.get(pk=delivery.pk).status, "requested")
        self.member.role = MembershipRole.SERVER
        self.member.save(update_fields=["role"])
        denied = self.client.get(url)
        self.assertNotEqual(denied.status_code, 200)
        self.assertNotIn(b"Central Kampala", denied.content)

    def test_packing_slip_denies_unassigned_foreign_outlet(self):
        from django.urls import reverse
        from apps.staff.middleware import (
            STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
        )
        set_outlet_delivery_enabled(
            outlet=self.outlet, enabled=True, user=self.user, membership=self.member,
        )
        delivery, _ = self._register()
        self.member.outlets.set([self.other_outlet])
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.other_outlet.pk)
        session.save()
        url = reverse("staff-delivery-packing-slip", kwargs={"delivery_id":delivery.pk})
        denied = self.client.get(url)
        self.assertNotEqual(denied.status_code, 200)
        self.assertNotIn(b"Central Kampala", denied.content)

    def test_nonmanager_cannot_read_or_change_delivery_queue(self):
        from django.urls import reverse
        from apps.staff.middleware import (
            STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY,
        )
        self.member.role = MembershipRole.SERVER
        self.member.save(update_fields=["role"])
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        url = reverse("staff-deliveries")
        # The shared navigation guard may redirect nonmanagers before the
        # view's explicit 403, but can never disclose the delivery queue.
        self.assertNotEqual(self.client.get(url).status_code, 200)
        self.assertNotEqual(self.client.post(url, {
            "action":"configure", "outlet_id":str(self.outlet.pk), "enabled":"true",
        }).status_code, 200)
        self.assertFalse(OutletDeliverySettings.objects.exists())

    def test_delivery_requires_manager_role(self):
        self.member.role = MembershipRole.SERVER
        self.member.save(update_fields=["role"])
        with self.assertRaises(ValidationError):
            set_outlet_delivery_enabled(
                outlet=self.outlet, enabled=True,
                user=self.user, membership=self.member,
            )
