from decimal import Decimal
import uuid
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from apps.accounts.models import User, Membership, MembershipRole
from apps.finance.models import CashbookEntry
from apps.pos.models import CashDrawerMovement, Order, Payment, PosShift, Workstation
from apps.pos.services import open_pos_shift, close_pos_shift, record_order_payment, record_order_refund, record_cash_drawer_movement, shift_cash_snapshot
from apps.pos.services.offline import process_offline_queue_entry
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class RegisterAttributionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Tills", slug="till-attribution")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Shop", outlet_type=OutletType.RETAIL)
        cls.other = Outlet.objects.create(site=cls.site, name="Other", outlet_type=OutletType.RETAIL)
        cls.a = Workstation.objects.create(tenant=cls.tenant, outlet=cls.outlet, name="Till A", code="till-a")
        cls.b = Workstation.objects.create(tenant=cls.tenant, outlet=cls.outlet, name="Till B", code="till-b")
        cls.wrong = Workstation.objects.create(tenant=cls.tenant, outlet=cls.other, name="Other till", code="other-till")
        cls.user = User.objects.create_user(email="till@test.local", password="TestPass9!")
        cls.membership = Membership.objects.create(tenant=cls.tenant, user=cls.user, role=MembershipRole.OWNER)

    def open(self, station, cash="10"):
        return open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.user, opening_cash=Decimal(cash), workstation=station)

    def order(self):
        return Order.objects.create(tenant=self.tenant, outlet=self.outlet, total=Decimal("100"), currency="UGX")

    def pay(self, order=None, station=None, **extra):
        return record_order_payment(order=order or self.order(), user=self.user, amount=Decimal("100"), method=extra.pop("method", "cash"), idempotency_key=extra.pop("key", str(uuid.uuid4())), workstation_id=station.pk if station else None, **extra)[0]

    def test_two_tills_and_refund_drawer(self):
        a, b = self.open(self.a, "20"), self.open(self.b, "30")
        payment = self.pay(station=self.a)
        self.pay(station=self.b); self.pay(station=self.b, method="card")
        refund, _ = record_order_refund(order=payment.order, user=self.user, amount=Decimal("15"), reason="Return", idempotency_key="cross-till", restock=False, workstation_id=self.b.pk)
        self.assertEqual(payment.shift_id, a.pk); self.assertEqual(refund.shift_id, b.pk)
        self.assertEqual(shift_cash_snapshot(shift=a)["expected"], Decimal("120"))
        self.assertEqual(shift_cash_snapshot(shift=b)["expected"], Decimal("115"))
        close_pos_shift(shift=a, user=self.user, counted_cash=Decimal("120"))
        close_pos_shift(shift=b, user=self.user, counted_cash=Decimal("115"))
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.expected_cash, Decimal("120")); self.assertEqual(b.expected_cash, Decimal("115"))

    def test_cash_movement_ledger_replay_scope_and_close(self):
        a, b = self.open(self.a, "20"), self.open(self.b, "30")
        args = dict(shift=a, membership=self.membership, user=self.user, workstation_id=self.a.pk)
        def move(direction, amount, key):
            return record_cash_drawer_movement(**args, direction=direction, amount=amount, reason="Drawer reconciliation", idempotency_key=key)
        entry, repeated = move("float_add", "15.00", "one")
        self.assertFalse(repeated)
        self.assertEqual(move("float_add", "15", "one"), (entry, True))
        self.pay(station=self.a)
        move("drop", "40", "two")
        move("payout", "5", "three")
        self.assertEqual(shift_cash_snapshot(shift=a)["expected"], Decimal("90"))
        self.assertEqual(shift_cash_snapshot(shift=b)["expected"], Decimal("30"))
        with self.assertRaises(ValidationError): move("drop", "91", "overdraw")
        with self.assertRaises(ValidationError): move("float_add", "16", "one")
        with self.assertRaises(ValidationError): record_cash_drawer_movement(**{**args, "workstation_id": self.b.pk}, direction="float_add", amount="1", reason="Wrong register", idempotency_key="wrong")
        self.assertEqual(CashDrawerMovement.objects.count(), 3)
        close_pos_shift(shift=a, user=self.user, counted_cash=Decimal("90"))
        self.assertEqual(move("float_add", "15", "one"), (entry, True))
        with self.assertRaises(ValidationError): move("drop", "1", "late")
        a.refresh_from_db()
        self.assertEqual(a.expected_cash, Decimal("90"))

    def test_ambiguous_register_rolls_back(self):
        self.open(self.a); self.open(self.b)
        with self.assertRaises(ValidationError): self.pay()
        self.assertEqual(Payment.objects.count(), 0); self.assertEqual(CashbookEntry.objects.count(), 0)

    def test_automatic_single_and_no_shift_compatibility(self):
        self.assertIsNone(self.pay().shift_id)
        a = self.open(self.a)
        self.assertEqual(self.pay().shift_id, a.pk)
        self.assertEqual(shift_cash_snapshot(shift=a)["cash_payments"], Decimal("100"))

    def test_invalid_and_closed_registers(self):
        with self.assertRaises(ValidationError): self.pay(station=self.a)
        a = self.open(self.a)
        for extra in ({"station": self.wrong}, {"station": self.a, "shift_id": uuid.uuid4()}, {"station": self.a, "shift_id": "bad"}):
            with self.assertRaises(ValidationError): self.pay(**extra)
        close_pos_shift(shift=a, user=self.user, counted_cash=Decimal("10"))
        with self.assertRaises(ValidationError): self.pay(station=self.a, shift_id=a.pk)
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_replay_keeps_original_closed_shift(self):
        a = self.open(self.a); order = self.order()
        original = self.pay(order, self.a, key="stable", shift_id=a.pk)
        close_pos_shift(shift=a, user=self.user, counted_cash=Decimal("110"))
        new = self.open(self.a)
        args = dict(order=order, user=self.user, amount=Decimal("100"), method="cash", idempotency_key="stable")
        replay, repeated = record_order_payment(**args, workstation_id=self.a.pk, shift_id=a.pk)
        self.assertTrue(repeated); self.assertEqual(replay.pk, original.pk)
        self.assertEqual(shift_cash_snapshot(shift=new)["cash_payments"], Decimal("0"))
        for kwargs in ({"workstation_id": self.b.pk}, {"shift_id": new.pk}):
            with self.assertRaises(ValidationError): record_order_payment(**args, **kwargs)

    def test_refund_replay_cannot_move_register(self):
        a, b = self.open(self.a), self.open(self.b)
        payment = self.pay(station=self.a)
        args = dict(order=payment.order, user=self.user, amount=Decimal("5"), reason="Return", idempotency_key="refund", restock=False)
        refund, _ = record_order_refund(**args, shift_id=b.pk)
        close_pos_shift(shift=b, user=self.user, counted_cash=Decimal("5"))
        replay, repeat = record_order_refund(**args, shift_id=b.pk)
        self.assertTrue(repeat); self.assertEqual(refund.pk, replay.pk)
        with self.assertRaises(ValidationError): record_order_refund(**args, shift_id=a.pk)

    def test_legacy_shift_blocks_other_tills_and_keeps_old_totals(self):
        legacy = PosShift.objects.create(tenant=self.tenant, outlet=self.outlet, workstation=self.a, cash_attribution=False)
        with self.assertRaises(ValidationError): self.open(self.b)
        payment = self.pay(station=self.a)
        Payment.objects.filter(pk=payment.pk).update(shift=None)
        self.assertEqual(shift_cash_snapshot(shift=legacy)["cash_payments"], Decimal("100"))
        close_pos_shift(shift=legacy, user=self.user, counted_cash=Decimal("100"))
        self.open(self.a); self.open(self.b)
        with self.assertRaises(ValidationError):
            open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.user, opening_cash=Decimal("0"))

    def test_offline_origin_shift_required_and_late_tender_rejected(self):
        a = self.open(self.a); order = self.order()
        payload = {"order_id": str(order.pk), "amount": "100", "method": "cash", "idempotency_key": "offline"}
        args = dict(tenant_id=self.tenant.pk, membership=self.membership, outlet=self.outlet, user=self.user, client_mutation_id="origin", operation_type="order_payment")
        with self.assertRaises(ValidationError): process_offline_queue_entry(**args, payload=payload)
        payload["shift_id"] = str(a.pk)
        obj, _ = process_offline_queue_entry(**args, payload=payload)
        self.assertEqual(Payment.objects.get(pk=obj.applied_payment_id).shift_id, a.pk)
        close_pos_shift(shift=a, user=self.user, counted_cash=Decimal("110"))
        new = self.open(self.a)
        replay, repeated = process_offline_queue_entry(**args, payload=payload)
        self.assertTrue(repeated); self.assertEqual(replay.pk, obj.pk)
        payload.update(order_id=str(self.order().pk), idempotency_key="late")
        args["client_mutation_id"] = "late"
        with self.assertRaises(ValidationError): process_offline_queue_entry(**args, payload=payload)
        self.assertEqual(shift_cash_snapshot(shift=new)["cash_payments"], Decimal("0"))

    def test_api_shift_discovery_and_outlet_scope(self):
        a = self.open(self.a)
        other = open_pos_shift(tenant_id=self.tenant.pk, outlet=self.other, user=self.user, opening_cash=Decimal("0"), workstation=self.wrong)
        api = APIClient(); self.assertTrue(api.login(username=self.user.email, password="TestPass9!"))
        response = api.get("/api/v1/pos/shifts/", {"outlet": str(self.outlet.pk), "status": "open"}, HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["id"] for r in rows], [str(a.pk)])
        order = self.order()
        response = api.post(f"/api/v1/orders/{order.pk}/payments/", {"amount": "100", "method": "cash", "shift_id": str(a.pk)}, format="json", HTTP_X_TENANT_ID=str(self.tenant.pk), HTTP_IDEMPOTENCY_KEY="api-shift")
        self.assertEqual(response.status_code, 201); self.assertEqual(response.data["shift_id"], str(a.pk))
        self.membership.outlets.add(self.outlet)
        self.assertEqual(api.get(f"/api/v1/pos/shifts/{other.pk}/", HTTP_X_TENANT_ID=str(self.tenant.pk)).status_code, 404)

    def test_staff_selected_register_and_close_scope(self):
        a, b = self.open(self.a), self.open(self.b)
        self.client.force_login(self.user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk); session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk); session.save()
        self.client.post(reverse("staff-workstations"), {"workstation_id": self.a.pk})
        page = self.client.get(reverse("staff-pos-shifts"))
        self.assertEqual(page.context["open_shift"].pk, a.pk); self.assertContains(page, "Other open registers")
        order = self.order()
        response = self.client.post(reverse("staff-order-detail", args=[order.pk]), {"action": "record_payment", "amount": "100", "method": "cash"})
        self.assertEqual(response.status_code, 302); self.assertEqual(Payment.objects.get(order=order).shift_id, a.pk)
        self.client.post(reverse("staff-pos-shifts"), {"action": "close_shift", "shift_id": b.pk, "counted_cash": "10"})
        b.refresh_from_db(); self.assertEqual(b.status, "open")

    def test_linked_return_refund_uses_selected_drawer(self):
        from apps.pos.models import OrderLine, SupermarketLineReturn
        from apps.pos.services import refund_retail_line
        a, b = self.open(self.a), self.open(self.b)
        order = self.order()
        line = OrderLine.objects.create(order=order, label="Returned product", quantity=Decimal("1"), unit_price=Decimal("100"), line_total=Decimal("100"))
        self.pay(order, self.a)
        args = dict(order=order, line=line, quantity=Decimal("1"), amount=Decimal("20"), reason="Return", restock=False, user=self.user, idempotency_key="linked-drawer")
        with self.assertRaises(ValidationError):
            refund_retail_line(**args)
        self.assertFalse(SupermarketLineReturn.objects.exists())
        ret, replay = refund_retail_line(**args, shift_id=b.pk)
        self.assertFalse(replay)
        self.assertEqual(ret.refund.shift_id, b.pk)
        self.assertEqual(shift_cash_snapshot(shift=a)["cash_refunds"], Decimal("0"))
        self.assertEqual(shift_cash_snapshot(shift=b)["cash_refunds"], Decimal("20"))

    def test_disabled_station_and_duplicate_open_are_rejected(self):
        self.open(self.a)
        with self.assertRaises(ValidationError): self.open(self.a)
        Workstation.objects.filter(pk=self.a.pk).update(is_active=False)
        with self.assertRaises(ValidationError): self.pay(station=self.a)
        with self.assertRaises(ValidationError): self.pay()
