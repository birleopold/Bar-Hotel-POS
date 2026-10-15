"""Night-audit posting, duplicates, scope, close and folio reconciliation."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.lodging.models import (
    Folio, FolioLine, PropertyNightAudit, Reservation, ReservationStatus,
    Room, RoomRateWindow, RoomType,
)
from apps.lodging.night_audit import (
    close_night_audit, night_audit_snapshot, post_missing_room_night,
)
from apps.tenants.business_date import business_date_for
from apps.tenants.models import Tenant, Site


class NightAuditWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Night Audit Demo", slug="night-audit-demo-test")
        self.site = Site.objects.create(tenant=self.tenant, name="Hotel")
        self.night = business_date_for(tenant=self.tenant, site=self.site) - timedelta(days=1)
        self.room_type = RoomType.objects.create(tenant=self.tenant, site=self.site, name="Standard")
        self.room = Room.objects.create(room_type=self.room_type, name="101")
        self.reservation = Reservation.objects.create(
            tenant=self.tenant, site=self.site, guest_name="Jane Doe",
            status=ReservationStatus.CHECKED_IN, room=self.room,
            check_in=self.night, check_out=self.night + timedelta(days=2),
        )
        self.folio = Folio.objects.create(
            tenant=self.tenant, site=self.site, reservation=self.reservation,
            guest_name="Jane Doe", currency="UGX",
        )
        self.rate = RoomRateWindow.objects.create(
            room_type=self.room_type, valid_from=self.night - timedelta(days=1),
            nightly_amount=Decimal("100000"),
        )
    
    def post(self):
        return post_missing_room_night(
            tenant=self.tenant, site=self.site, night=self.night,
            reservation_id=self.reservation.pk, user=None,
        )

    def test_reconciles_missing_night_once_and_records_close(self):
        snapshot = night_audit_snapshot(tenant=self.tenant, site=self.site, night=self.night)
        self.assertEqual(len(snapshot["missing"]), 1)
        with self.assertRaises(ValidationError):
            close_night_audit(
                tenant=self.tenant, site=self.site, night=self.night,
                user=None, note="", confirm_cash=True, confirm_folios=True,
            )
        self.assertTrue(self.post())
        self.assertFalse(self.post())
        self.assertEqual(self.folio.lines.count(), 1)
        updated = night_audit_snapshot(tenant=self.tenant, site=self.site, night=self.night)
        self.assertFalse(updated["blockers"])
        close, replay = close_night_audit(
            tenant=self.tenant, site=self.site, night=self.night,
            user=None, note="Registers reconciled", confirm_cash=True, confirm_folios=True,
        )
        self.assertFalse(replay)
        close_again, replayed = close_night_audit(
            tenant=self.tenant, site=self.site, night=self.night,
            user=None, note="", confirm_cash=True, confirm_folios=True,
        )
        self.assertTrue(replayed)
        self.assertEqual(close.pk, close_again.pk)
        self.assertEqual(PropertyNightAudit.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.post()

    def test_recognizes_historical_prepaid_stay_room_line(self):
        FolioLine.objects.create(
            tenant=self.tenant, folio=self.folio,
            description=f"Room night {self.night.isoformat()} ({self.room.name})",
            amount=Decimal("100000"),
        )
        snapshot = night_audit_snapshot(tenant=self.tenant, site=self.site, night=self.night)
        self.assertEqual(snapshot["missing"], [])
        self.assertFalse(self.post())
        self.assertEqual(self.folio.lines.count(), 1)

    def test_duplicate_room_charges_block_close(self):
        for _ in range(2):
            FolioLine.objects.create(
                tenant=self.tenant, folio=self.folio,
                description=f"Room night {self.night.isoformat()} ({self.room.name})",
                amount=Decimal("100000"),
            )
        snapshot = night_audit_snapshot(tenant=self.tenant, site=self.site, night=self.night)
        self.assertEqual(len(snapshot["duplicates"]), 1)
        with self.assertRaises(ValidationError):
            close_night_audit(
                tenant=self.tenant, site=self.site, night=self.night,
                user=None, note="", confirm_cash=True, confirm_folios=True,
            )
        self.assertFalse(PropertyNightAudit.objects.exists())

    def test_cannot_post_another_property_reservation(self):
        other_site = Site.objects.create(tenant=self.tenant, name="Another Hotel")
        with self.assertRaises(ValidationError):
            post_missing_room_night(
                tenant=self.tenant, site=other_site, night=self.night,
                reservation_id=self.reservation.pk, user=None,
            )
        self.assertFalse(self.folio.lines.exists())

    def test_missing_manager_confirmations_prevent_close(self):
        self.post()
        with self.assertRaises(ValidationError):
            close_night_audit(
                tenant=self.tenant, site=self.site, night=self.night,
                user=None, note="", confirm_cash=False, confirm_folios=True,
            )
        self.assertFalse(PropertyNightAudit.objects.exists())
