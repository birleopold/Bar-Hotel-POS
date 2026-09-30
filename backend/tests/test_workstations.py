from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.pos.models import Workstation
from apps.pos.services import open_pos_shift, close_pos_shift
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.staff.workstations import COOKIE
from apps.tenants.models import Tenant, Site, Outlet, OutletType


class WorkstationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Device tests", slug="device-tests")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Counter", outlet_type=OutletType.RETAIL)
        cls.other = Outlet.objects.create(site=cls.site, name="Other", outlet_type=OutletType.RETAIL)
        cls.foreign_tenant = Tenant.objects.create(name="Foreign", slug="device-foreign")
        cls.foreign_site = Site.objects.create(tenant=cls.foreign_tenant, name="Other")
        cls.foreign_outlet = Outlet.objects.create(site=cls.foreign_site, name="Foreign", outlet_type=OutletType.RETAIL)
        cls.station = Workstation.objects.create(tenant=cls.tenant, outlet=cls.outlet, name="Counter One", code="counter-01")
        cls.foreign_station = Workstation.objects.create(tenant=cls.foreign_tenant, outlet=cls.foreign_outlet, name="Foreign device", code="foreign")
        cls.owner = get_user_model().objects.create_user(email="device-owner@test.local", password="Password9!")
        cls.worker = get_user_model().objects.create_user(email="device-worker@test.local", password="Password9!")
        Membership.objects.create(tenant=cls.tenant, user=cls.owner, role=MembershipRole.OWNER)
        member = Membership.objects.create(tenant=cls.tenant, user=cls.worker, role=MembershipRole.SERVER)
        member.outlets.add(cls.outlet)

    def login(self, user=None):
        self.client.force_login(user or self.owner)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()

    def data(self, **changes):
        return {"name": "Counter One", "code": "counter-01", "outlet": str(self.outlet.pk), "is_active": "on", **changes}

    def test_configuration_unique_code_and_audit(self):
        self.login()
        response = self.client.post(reverse("staff-workstation-create"), self.data(code="NEW-02", name="Counter Two"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Workstation.objects.filter(tenant=self.tenant, code="new-02").exists())
        self.assertTrue(AuditEvent.objects.filter(action="workstation.created").exists())
        response = self.client.post(reverse("staff-workstation-create"), self.data(code="COUNTER-01"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Workstation.objects.filter(tenant=self.tenant).count(), 2)

    def test_permissions_and_scope(self):
        self.login(self.worker)
        self.assertEqual(self.client.get(reverse("staff-workstation-create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("staff-workstation-edit", args=[self.station.pk]), self.data()).status_code, 403)
        hidden = Workstation.objects.create(tenant=self.tenant, outlet=self.other, name="Hidden", code="hidden")
        response = self.client.get(reverse("staff-workstations"))
        self.assertContains(response, "Counter One")
        self.assertNotContains(response, "Foreign device")
        self.assertNotContains(response, "Hidden")
        for identifier in (hidden.pk, self.foreign_station.pk):
            self.assertEqual(self.client.post(reverse("staff-workstations"), {"workstation_id": identifier}).status_code, 404)
        self.assertEqual(self.client.post(reverse("staff-workstations"), {"workstation_id": "bad"}).status_code, 400)

    def test_selection_links_shift_and_survives_lock(self):
        self.login()
        response = self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies[COOKIE]["httponly"])
        self.assertEqual(response.cookies[COOKIE]["samesite"], "Strict")
        response = self.client.post(reverse("staff-pos-shifts"), {"action": "open_shift", "opening_cash": "100"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.station.shifts.get().opened_by, self.owner)
        self.client.post(reverse("staff-terminal-lock"))
        self.login(self.worker)
        self.assertContains(self.client.get(reverse("staff-workstations")), "Selected")
        self.assertContains(self.client.get(reverse("staff-pos-shifts")), "Counter One")

    def test_invalid_and_disabled_cookie(self):
        self.login()
        self.client.cookies[COOKIE] = "forged"
        self.assertIsNone(self.client.get(reverse("staff-pos-shifts")).context["selected_station"])
        self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk})
        Workstation.objects.filter(pk=self.station.pk).update(is_active=False)
        self.assertIsNone(self.client.get(reverse("staff-pos-shifts")).context["selected_station"])
        self.assertEqual(self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk}).status_code, 404)

    def test_open_shift_prevents_disable_or_move(self):
        self.login()
        shift = open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.owner, opening_cash=Decimal("100"), workstation=self.station)
        url = reverse("staff-workstation-edit", args=[self.station.pk])
        self.assertEqual(self.client.post(url, self.data(is_active="")).status_code, 400)
        self.assertEqual(self.client.post(url, self.data(outlet=str(self.other.pk))).status_code, 400)
        self.station.refresh_from_db()
        self.assertTrue(self.station.is_active)
        self.assertEqual(self.station.outlet, self.outlet)
        close_pos_shift(shift=shift, user=self.owner, counted_cash=Decimal("100"))
        self.assertEqual(self.client.post(url, self.data(is_active="")).status_code, 302)

    def test_service_scope_and_single_outlet_shift(self):
        for station in (self.foreign_station, Workstation.objects.create(tenant=self.tenant, outlet=self.other, name="Other", code="other")):
            with self.assertRaises(ValidationError):
                open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.owner, opening_cash=Decimal("0"), workstation=station)
        open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.owner, opening_cash=Decimal("0"), workstation=self.station)
        with self.assertRaises(ValidationError):
            open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet, user=self.owner, opening_cash=Decimal("0"))

    def test_foreign_outlet_model_validation(self):
        with self.assertRaises(ModelValidationError):
            Workstation(tenant=self.tenant, outlet=self.foreign_outlet, name="Bad", code="bad").full_clean()
