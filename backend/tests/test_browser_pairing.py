from decimal import Decimal
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.pos.models import Workstation, WorkstationPairing, PosShift, Payment, Order
from apps.pos.services import open_pos_shift
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY, STAFF_SESSION_OUTLET_KEY
from apps.staff.terminal import set_member_pin
from apps.staff.workstations import PAIR_COOKIE
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class BrowserPairingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Browser tests", slug="browser-pairings")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Counter", outlet_type=OutletType.RETAIL)
        cls.station = Workstation.objects.create(tenant=cls.tenant, outlet=cls.outlet, name="Till", code="till", requires_pairing=True)
        cls.owner = User.objects.create_user(email="pair-owner@test.local", password="OwnerPass9!")
        cls.worker = User.objects.create_user(email="pair-worker@test.local", password="WorkerPass9!")
        cls.owner_member = Membership.objects.create(tenant=cls.tenant, user=cls.owner, role=MembershipRole.OWNER)
        cls.worker_member = Membership.objects.create(tenant=cls.tenant, user=cls.worker, role=MembershipRole.SERVER)
        cls.worker_member.outlets.add(cls.outlet)

    def login(self, user=None, client=None):
        client = client or self.client
        client.force_login(user or self.owner)
        session = client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        return client

    def approve(self, password="OwnerPass9!"):
        return self.client.post(reverse("staff-workstation-pair", args=[self.station.pk]), {"label": "Counter tablet", "password": password})

    def test_password_approval_and_secret_storage(self):
        self.login()
        self.assertEqual(self.approve("wrong").status_code, 400)
        self.assertFalse(WorkstationPairing.objects.exists())
        response = self.approve()
        self.assertEqual(response.status_code, 302)
        pair = WorkstationPairing.objects.get()
        self.assertEqual(pair.approved_by, self.owner)
        self.assertEqual(len(pair.token_hash), 64)
        self.assertNotIn(pair.token_hash, response.cookies[PAIR_COOKIE].value)
        self.assertTrue(response.cookies[PAIR_COOKIE]["httponly"])
        self.assertEqual(response.cookies[PAIR_COOKIE]["samesite"], "Strict")
        self.assertTrue(AuditEvent.objects.filter(action="workstation.browser_approved").exists())
        self.assertContains(self.client.get(reverse("staff-workstations")), "Approved browser")

    def test_worker_cannot_approve_or_bypass_required_device(self):
        self.login(self.worker)
        self.assertEqual(self.approve().status_code, 403)
        self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk})
        response = self.client.post(reverse("staff-pos-shifts"), {"action": "open_shift", "opening_cash": "10"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PosShift.objects.exists())
        order = Order.objects.create(tenant=self.tenant, outlet=self.outlet, total=Decimal("10"))
        self.client.post(reverse("staff-order-detail", args=[order.pk]), {"action": "record_payment", "amount": "10", "method": "cash"})
        self.assertFalse(Payment.objects.exists())

    def test_pairing_survives_pin_handoff_then_revocation_invalidates_session(self):
        self.login(); self.approve()
        pair = WorkstationPairing.objects.get()
        set_member_pin(self.worker_member, "681347")
        self.client.post(reverse("staff-terminal-lock"))
        self.assertContains(self.client.get(reverse("staff-terminal")), self.worker.email)
        response = self.client.post(reverse("staff-terminal"), {"worker": self.worker_member.pk, "pin": "681347"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["staff_pin_pairing"], str(pair.pk))
        admin = self.login(client=Client())
        url = reverse("staff-workstation-pair", args=[self.station.pk])
        self.assertEqual(admin.post(url, {"action": "revoke", "pairing_id": pair.pk, "reason": "Lost tablet", "password": "bad"}).status_code, 400)
        pair.refresh_from_db(); self.assertIsNone(pair.revoked_at)
        self.assertEqual(admin.post(url, {"action": "revoke", "pairing_id": pair.pk, "reason": "Lost tablet", "password": "OwnerPass9!"}).status_code, 302)
        self.client.get(reverse("staff-orders"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(list(self.client.get(reverse("staff-terminal")).context["workers"]), [])
        self.assertTrue(AuditEvent.objects.filter(action="workstation.browser_revoked").exists())

    def test_expiry_tampering_and_detach(self):
        self.login(); self.approve()
        pair = WorkstationPairing.objects.get()
        self.client.cookies[PAIR_COOKIE] = "tampered"
        self.assertIsNone(self.client.get(reverse("staff-pos-shifts")).context["selected_station"])
        self.approve()
        latest = WorkstationPairing.objects.latest("created_at")
        WorkstationPairing.objects.filter(pk=latest.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(self.client.get(reverse("staff-pos-shifts")).context["selected_station"])
        self.approve()
        live = WorkstationPairing.objects.latest("created_at")
        self.client.post(reverse("staff-workstations"), {"action": "forget"})
        live.refresh_from_db(); self.assertIsNotNone(live.revoked_at)
        self.assertEqual(self.client.cookies[PAIR_COOKIE].value, "")

    def test_open_shift_blocks_policy_change_and_disable_revokes_after_close(self):
        self.login(); self.approve()
        shift = open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.owner, opening_cash=Decimal("0"), workstation=self.station)
        url = reverse("staff-workstation-edit", args=[self.station.pk])
        data = {"name": "Till", "code": "till", "outlet": self.outlet.pk, "is_active": "on"}
        self.assertEqual(self.client.post(url, data).status_code, 400)
        self.station.refresh_from_db(); self.assertTrue(self.station.requires_pairing)
        from apps.pos.services import close_pos_shift
        close_pos_shift(shift=shift, user=self.owner, counted_cash=Decimal("0"))
        data.update(is_active="", requires_pairing="on")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertFalse(WorkstationPairing.objects.filter(revoked_at__isnull=True).exists())

    def test_foreign_pairing_and_pin_admin_denied(self):
        self.login(); self.approve()
        other_tenant = Tenant.objects.create(name="Other", slug="pair-other")
        site = Site.objects.create(tenant=other_tenant, name="Other")
        outlet = Outlet.objects.create(site=site, name="Other")
        station = Workstation.objects.create(tenant=other_tenant, outlet=outlet, name="Other", code="other")
        self.assertEqual(self.client.get(reverse("staff-workstation-pair", args=[station.pk])).status_code, 404)
        session = self.client.session
        session["staff_pin_authenticated"] = True
        session.save()
        self.assertEqual(self.client.get(reverse("staff-workstation-pair", args=[self.station.pk])).status_code, 403)
