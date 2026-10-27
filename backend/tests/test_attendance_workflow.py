from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    AttendanceBreak,
    AttendanceShift,
    AttendanceShiftStatus,
    Membership,
    MembershipRole,
    User,
)
from apps.audit.models import AuditEvent
from apps.pos.models import PosShift
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


class AttendanceWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Attendance", slug="attendance-tests")
        TenantSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={"business_lines": ["supermarket"]},
        )
        cls.site = Site.objects.create(tenant=cls.tenant, name="Main")
        cls.outlet = Outlet.objects.create(
            site=cls.site,
            name="Checkout",
            outlet_type=OutletType.SUPERMARKET,
        )
        cls.other_site = Site.objects.create(tenant=cls.tenant, name="Other")
        cls.other_outlet = Outlet.objects.create(
            site=cls.other_site,
            name="Private",
            outlet_type=OutletType.SUPERMARKET,
        )

        cls.worker = User.objects.create_user(
            email="attendance-worker@test.local",
            password="Password9!",
        )
        cls.worker_membership = Membership.objects.create(
            tenant=cls.tenant,
            user=cls.worker,
            role=MembershipRole.SERVER,
        )
        cls.worker_membership.sites.add(cls.site)
        cls.worker_membership.outlets.add(cls.outlet)

        cls.manager = User.objects.create_user(
            email="attendance-manager@test.local",
            password="Password9!",
        )
        cls.manager_membership = Membership.objects.create(
            tenant=cls.tenant,
            user=cls.manager,
            role=MembershipRole.OUTLET_MANAGER,
        )
        cls.manager_membership.sites.add(cls.site)
        cls.manager_membership.outlets.add(cls.outlet)

        cls.other_worker = User.objects.create_user(
            email="attendance-other@test.local",
            password="Password9!",
        )
        cls.other_membership = Membership.objects.create(
            tenant=cls.tenant,
            user=cls.other_worker,
            role=MembershipRole.SERVER,
        )
        cls.other_membership.sites.add(cls.other_site)
        cls.other_membership.outlets.add(cls.other_outlet)

    def login(self, user, site=None, outlet=None):
        self.client.force_login(user)
        session = self.client.session
        session[STAFF_SESSION_TENANT_KEY] = str(self.tenant.pk)
        session[STAFF_SESSION_SITE_KEY] = str((site or self.site).pk)
        session[STAFF_SESSION_OUTLET_KEY] = str((outlet or self.outlet).pk)
        session.save()

    def test_worker_clock_break_clockout_is_separate_from_pos_shift(self):
        self.login(self.worker)
        self.assertEqual(PosShift.objects.count(), 0)

        response = self.client.post(
            reverse("staff-attendance"),
            {"action": "clock_in", "note": "Opening shift"},
        )
        self.assertEqual(response.status_code, 302)
        shift = AttendanceShift.objects.get(
            membership=self.worker_membership,
            status=AttendanceShiftStatus.OPEN,
        )
        self.assertEqual(shift.site_id, self.site.pk)
        self.assertEqual(shift.outlet_id, self.outlet.pk)
        self.assertEqual(PosShift.objects.count(), 0)

        self.client.post(
            reverse("staff-attendance"),
            {"action": "start_break", "note": "Lunch"},
        )
        item = AttendanceBreak.objects.get(shift=shift, ended_at__isnull=True)
        self.assertEqual(item.note, "Lunch")

        blocked = self.client.post(
            reverse("staff-attendance"),
            {"action": "clock_out", "note": ""},
            follow=True,
        )
        shift.refresh_from_db()
        self.assertEqual(shift.status, AttendanceShiftStatus.OPEN)
        self.assertContains(blocked, "End the current break before clocking out")

        self.client.post(
            reverse("staff-attendance"),
            {"action": "end_break", "note": ""},
        )
        item.refresh_from_db()
        self.assertIsNotNone(item.ended_at)

        response = self.client.post(
            reverse("staff-attendance"),
            {"action": "clock_out", "note": "Finished"},
        )
        self.assertEqual(response.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.status, AttendanceShiftStatus.PENDING)
        self.assertIsNotNone(shift.clock_out_at)
        self.assertEqual(PosShift.objects.count(), 0)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="attendance.clocked_in",
                entity_id=str(shift.pk),
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="attendance.clocked_out",
                entity_id=str(shift.pk),
            ).exists()
        )

    def test_manager_reviews_corrects_and_exports_scoped_timesheets(self):
        now = timezone.now()
        shift = AttendanceShift.objects.create(
            tenant=self.tenant,
            membership=self.worker_membership,
            site=self.site,
            outlet=self.outlet,
            status=AttendanceShiftStatus.PENDING,
            clock_in_at=now - timedelta(hours=8),
            clock_out_at=now,
        )
        AttendanceBreak.objects.create(
            shift=shift,
            started_at=now - timedelta(hours=5),
            ended_at=now - timedelta(hours=4, minutes=30),
        )
        hidden = AttendanceShift.objects.create(
            tenant=self.tenant,
            membership=self.other_membership,
            site=self.other_site,
            outlet=self.other_outlet,
            status=AttendanceShiftStatus.PENDING,
            clock_in_at=now - timedelta(hours=7),
            clock_out_at=now,
        )

        self.login(self.manager)
        page = self.client.get(reverse("staff-timesheets"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.worker.email)
        self.assertNotContains(page, self.other_worker.email)
        self.assertContains(page, "7.5 h")

        approve = self.client.post(
            reverse("staff-timesheets"),
            {
                "shift_id": str(shift.pk),
                "action": "approve",
                "clock_in_at": "",
                "clock_out_at": "",
                "review_note": "Checked",
            },
        )
        self.assertEqual(approve.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.status, AttendanceShiftStatus.APPROVED)
        self.assertEqual(shift.reviewed_by_id, self.manager.pk)

        corrected_in = now - timedelta(hours=8, minutes=15)
        corrected_out = now - timedelta(minutes=5)
        correct = self.client.post(
            reverse("staff-timesheets"),
            {
                "shift_id": str(shift.pk),
                "action": "correct",
                "clock_in_at": timezone.localtime(corrected_in).strftime("%Y-%m-%dT%H:%M"),
                "clock_out_at": timezone.localtime(corrected_out).strftime("%Y-%m-%dT%H:%M"),
                "review_note": "Worker forgot exact start time",
            },
        )
        self.assertEqual(correct.status_code, 302)
        shift.refresh_from_db()
        self.assertEqual(shift.status, AttendanceShiftStatus.APPROVED)
        self.assertEqual(shift.review_note, "Worker forgot exact start time")
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action="attendance.timesheet_corrected",
                entity_id=str(shift.pk),
            ).exists()
        )

        exported = self.client.get(
            reverse("staff-timesheets"),
            {"export": "csv"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported["Content-Type"], "text/csv; charset=utf-8")
        body = exported.content.decode()
        self.assertIn(self.worker.email, body)
        self.assertNotIn(self.other_worker.email, body)
        self.assertIn("worked_hours", body)

        hidden_post = self.client.post(
            reverse("staff-timesheets"),
            {
                "shift_id": str(hidden.pk),
                "action": "approve",
                "review_note": "No access",
            },
        )
        self.assertEqual(hidden_post.status_code, 404)

    def test_correction_rejects_overlap_and_break_outside_range(self):
        now = timezone.now()
        target = AttendanceShift.objects.create(
            tenant=self.tenant,
            membership=self.worker_membership,
            site=self.site,
            outlet=self.outlet,
            status=AttendanceShiftStatus.PENDING,
            clock_in_at=now - timedelta(hours=8),
            clock_out_at=now - timedelta(hours=4),
        )
        AttendanceBreak.objects.create(
            shift=target,
            started_at=now - timedelta(hours=7),
            ended_at=now - timedelta(hours=6, minutes=30),
        )
        AttendanceShift.objects.create(
            tenant=self.tenant,
            membership=self.worker_membership,
            site=self.site,
            outlet=self.outlet,
            status=AttendanceShiftStatus.APPROVED,
            clock_in_at=now - timedelta(hours=3),
            clock_out_at=now - timedelta(hours=1),
        )
        self.login(self.manager)

        overlap = self.client.post(
            reverse("staff-timesheets"),
            {
                "shift_id": str(target.pk),
                "action": "correct",
                "clock_in_at": timezone.localtime(now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M"),
                "clock_out_at": timezone.localtime(now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "review_note": "Corrected end",
            },
            follow=True,
        )
        target.refresh_from_db()
        self.assertContains(overlap, "would overlap another attendance shift")
        self.assertEqual(target.status, AttendanceShiftStatus.PENDING)

        outside_break = self.client.post(
            reverse("staff-timesheets"),
            {
                "shift_id": str(target.pk),
                "action": "correct",
                "clock_in_at": timezone.localtime(now - timedelta(hours=6, minutes=45)).strftime("%Y-%m-%dT%H:%M"),
                "clock_out_at": timezone.localtime(now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
                "review_note": "Shorter shift",
            },
            follow=True,
        )
        target.refresh_from_db()
        self.assertContains(outside_break, "break would fall outside")
        self.assertEqual(target.status, AttendanceShiftStatus.PENDING)

    def test_non_manager_cannot_review_timesheets(self):
        self.login(self.worker)
        self.assertEqual(self.client.get(reverse("staff-timesheets")).status_code, 403)
