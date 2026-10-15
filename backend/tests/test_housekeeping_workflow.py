"""Mobile housekeeping assignments, controlled transitions and tenant scope."""
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership, MembershipRole, User
from apps.lodging.housekeeping import change_housekeeping_room
from apps.lodging.models import (
    MaintenanceStatus, Room, RoomHousekeepingEvent, RoomMaintenanceRequest,
    RoomStatus, RoomType,
)
from apps.tenants.models import Tenant, Site


class HousekeepingWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Housekeeping Team", slug="housekeeping-team-test")
        self.site = Site.objects.create(tenant=self.tenant, name="Main Hotel")
        room_type = RoomType.objects.create(tenant=self.tenant, site=self.site, name="Standard")
        self.room = Room.objects.create(room_type=room_type, name="105", status=RoomStatus.DIRTY)
        self.manager = User.objects.create_user(email="housekeeping.manager@example.com")
        self.cleaner = User.objects.create_user(email="housekeeping.cleaner@example.com")
        self.other = User.objects.create_user(email="housekeeping.other@example.com")
        self.manager_membership = Membership.objects.create(
            tenant=self.tenant, user=self.manager, role=MembershipRole.SITE_MANAGER,
        )
        self.cleaner_membership = Membership.objects.create(
            tenant=self.tenant, user=self.cleaner, role=MembershipRole.CLEANER,
        )
        self.other_membership = Membership.objects.create(
            tenant=self.tenant, user=self.other, role=MembershipRole.CLEANER,
        )
        for membership in (self.manager_membership, self.cleaner_membership, self.other_membership):
            membership.sites.add(self.site)

    def move(self, action, membership, user, **kwargs):
        return change_housekeeping_room(
            tenant=self.tenant, site=self.site, room_id=self.room.pk,
            membership=membership, action=action, user=user, **kwargs,
        )

    def test_assign_start_finish_and_inspect_end_to_end(self):
        self.move("assign", self.manager_membership, self.manager,
                  assigned_user_id=self.cleaner.pk)
        self.room.refresh_from_db()
        self.assertEqual(self.room.assigned_housekeeper_id, self.cleaner.pk)
        self.move("start", self.cleaner_membership, self.cleaner)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.CLEANING)
        self.move("finish", self.cleaner_membership, self.cleaner)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.CLEAN)
        self.assertIsNotNone(self.room.housekeeping_finished_at)
        self.move("inspect", self.manager_membership, self.manager)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.INSPECTED)
        self.assertIsNotNone(self.room.housekeeping_inspected_at)
        self.assertEqual(RoomHousekeepingEvent.objects.filter(room=self.room).count(), 4)

    def test_unassigned_worker_can_claim_dirty_room(self):
        self.move("claim", self.cleaner_membership, self.cleaner)
        self.room.refresh_from_db()
        self.assertEqual(self.room.assigned_housekeeper_id, self.cleaner.pk)
        with self.assertRaises(ValidationError):
            self.move("start", self.other_membership, self.other)
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_cleaner_cannot_inspect_or_assign(self):
        with self.assertRaises(ValidationError):
            self.move("inspect", self.cleaner_membership, self.cleaner)
        with self.assertRaises(ValidationError):
            self.move("assign", self.cleaner_membership, self.cleaner, assigned_user_id=self.other.pk)

    def test_open_repair_prevents_marking_ready(self):
        RoomMaintenanceRequest.objects.create(
            tenant=self.tenant, room=self.room, title="Door lock",
            status=MaintenanceStatus.OPEN,
        )
        self.move("start", self.cleaner_membership, self.cleaner)
        with self.assertRaises(ValidationError):
            self.move("finish", self.cleaner_membership, self.cleaner)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.CLEANING)

    def test_rejected_cross_property_action_changes_nothing(self):
        other_site = Site.objects.create(tenant=self.tenant, name="Other Hotel")
        with self.assertRaises(ValidationError):
            change_housekeeping_room(
                tenant=self.tenant, site=other_site, room_id=self.room.pk,
                membership=self.cleaner_membership, action="start", user=self.cleaner,
            )
        self.assertFalse(RoomHousekeepingEvent.objects.exists())
