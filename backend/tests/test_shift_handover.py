from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.pos.models import PosShift, ShiftHandover, Workstation
from apps.pos.services import (
    accept_shift_handover, approve_shift_handover, open_pos_shift,
    submit_shift_handover, verify_shift_handover,
)
from apps.staff.middleware import STAFF_SESSION_OUTLET_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant


class ShiftHandoverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Handover", slug="handover-test")
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(site=cls.site, name="Bar", outlet_type=OutletType.BAR)
        cls.station = Workstation.objects.create(tenant=cls.tenant, outlet=cls.outlet, name="Till", code="handover-till")
        cls.workers = {}
        for label, role in (("closing", MembershipRole.SERVER), ("verifier", MembershipRole.BARTENDER),
                            ("manager", MembershipRole.OUTLET_MANAGER), ("incoming", MembershipRole.SERVER),
                            ("viewer", MembershipRole.ACCOUNTANT)):
            user = User.objects.create_user(email=f"{label}@handover.test", password="TestPass9!")
            cls.workers[label] = (user, Membership.objects.create(tenant=cls.tenant, user=user, role=role))

    def shift(self):
        return open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet,
            user=self.workers["closing"][0], opening_cash=Decimal("50"), workstation=self.station)

    def submit(self, shift, counted="50", explanation=""):
        user, membership = self.workers["closing"]
        return submit_shift_handover(shift=shift, user=user, membership=membership,
            counted_cash=counted, explanation=explanation, workstation_id=self.station.pk)

    def test_full_handover_requires_independent_count_and_separate_manager(self):
        shift = self.shift()
        with self.assertRaises(ValidationError):
            self.submit(shift, "48")
        self.assertEqual(ShiftHandover.objects.count(), 0)
        handover = self.submit(shift, "48", "Two units short at close")
        with self.assertRaises(ValidationError):
            self.submit(shift, "48", "Repeat")
        with self.assertRaises(ValidationError):
            open_pos_shift(tenant_id=self.tenant.pk, outlet=self.outlet,
                user=self.workers["incoming"][0], opening_cash=Decimal("48"), workstation=self.station)
        with self.assertRaises(ValidationError):
            verify_shift_handover(handover=handover, user=self.workers["closing"][0],
                membership=self.workers["closing"][1], counted_cash="48")
        verifier, verifier_membership = self.workers["verifier"]
        with self.assertRaises(ValidationError):
            verify_shift_handover(handover=handover, user=verifier, membership=verifier_membership, counted_cash="47")
        verify_shift_handover(handover=handover, user=verifier, membership=verifier_membership,
            counted_cash="47", note="One more unit missing on recount")
        manager, manager_membership = self.workers["manager"]
        with self.assertRaises(ValidationError):
            approve_shift_handover(handover=handover, user=verifier, membership=verifier_membership, note="Approve")
        with self.assertRaises(ValidationError):
            approve_shift_handover(handover=handover, user=manager, membership=manager_membership)
        approve_shift_handover(handover=handover, user=manager, membership=manager_membership, note="Investigate variance")
        incoming, incoming_membership = self.workers["incoming"]
        with self.assertRaises(ValidationError):
            accept_shift_handover(handover=handover, user=incoming, membership=incoming_membership,
                opening_cash="48", workstation_id=self.station.pk)
        with self.assertRaises(ValidationError):
            accept_shift_handover(handover=handover, user=manager, membership=manager_membership,
                opening_cash="47", workstation_id=self.station.pk)
        accepted = accept_shift_handover(handover=handover, user=incoming, membership=incoming_membership,
            opening_cash="47", workstation_id=self.station.pk)
        self.assertEqual(accepted.status, ShiftHandover.Status.ACCEPTED)
        self.assertEqual(accepted.next_shift.opening_cash, Decimal("47"))
        self.assertEqual(accepted.next_shift.opened_by, incoming)
        with self.assertRaises(ValidationError):
            accept_shift_handover(handover=handover, user=incoming, membership=incoming_membership,
                opening_cash="47", workstation_id=self.station.pk)
        self.assertEqual(PosShift.objects.count(), 2)

    def test_scope_and_accountant_cannot_transition(self):
        handover = self.submit(self.shift())
        viewer, membership = self.workers["viewer"]
        with self.assertRaises(ValidationError):
            verify_shift_handover(handover=handover, user=viewer, membership=membership, counted_cash="50")
        verifier, membership = self.workers["verifier"]
        other = Outlet.objects.create(site=self.site, name="Other", outlet_type=OutletType.BAR)
        membership.outlets.add(other)
        with self.assertRaises(ValidationError):
            verify_shift_handover(handover=handover, user=verifier, membership=membership, counted_cash="50")
        handover.refresh_from_db()
        self.assertEqual(handover.status, ShiftHandover.Status.SUBMITTED)

    def test_staff_submission_and_pending_screen(self):
        shift = self.shift()
        user, _ = self.workers["closing"]
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
        session.save()
        self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk})
        response = self.client.post(reverse("staff-pos-shifts"), {
            "action": "close_shift", "shift_id": str(shift.pk), "counted_cash": "50", "note": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ShiftHandover.objects.get(shift=shift).status, ShiftHandover.Status.SUBMITTED)
        page = self.client.get(reverse("staff-pos-shifts"))
        self.assertContains(page, "Awaiting independent count")
        self.assertNotContains(page, "Start a register shift")

        handover = ShiftHandover.objects.get(shift=shift)
        def sign_in(label):
            self.client.force_login(self.workers[label][0])
            session = self.client.session
            session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
            session[STAFF_SESSION_OUTLET_KEY] = str(self.outlet.pk)
            session.save()
            self.client.post(reverse("staff-workstations"), {"workstation_id": self.station.pk})

        sign_in("verifier")
        response = self.client.post(reverse("staff-pos-shifts"), {
            "action": "verify_handover", "handover_id": str(handover.pk), "counted_cash": "50", "note": "",
        })
        self.assertEqual(response.status_code, 302)
        handover.refresh_from_db()
        self.assertEqual(handover.status, ShiftHandover.Status.VERIFIED)
        sign_in("manager")
        response = self.client.post(reverse("staff-pos-shifts"), {
            "action": "approve_handover", "handover_id": str(handover.pk), "note": "",
        })
        self.assertEqual(response.status_code, 302)
        handover.refresh_from_db()
        self.assertEqual(handover.status, ShiftHandover.Status.APPROVED)
        sign_in("incoming")
        response = self.client.post(reverse("staff-pos-shifts"), {
            "action": "accept_handover", "handover_id": str(handover.pk), "opening_cash": "50",
        })
        self.assertEqual(response.status_code, 302)
        handover.refresh_from_db()
        self.assertEqual(handover.status, ShiftHandover.Status.ACCEPTED)
        self.assertContains(self.client.get(reverse("staff-pos-shifts")), "Current shift")
