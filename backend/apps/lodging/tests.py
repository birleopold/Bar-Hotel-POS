from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Membership, MembershipRole, User
from apps.tenants.models import Site, Tenant

from .models import Reservation, Room, RoomType
from .serializers import ReservationSerializer


class ReservationConstraintTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="Lodging Tenant", slug="lodging-tenant")
        self.site = Site.objects.create(tenant=self.tenant, name="Main")
        self.room_type = RoomType.objects.create(
            tenant=self.tenant,
            site=self.site,
            name="Standard",
            max_occupancy=2,
        )
        self.room = Room.objects.create(room_type=self.room_type, name="101")

    def test_reservation_rejects_checkout_before_checkin_at_db_level(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    tenant=self.tenant,
                    site=self.site,
                    guest_name="Guest",
                    check_in=date(2026, 6, 5),
                    check_out=date(2026, 6, 4),
                    room=self.room,
                )


class ReservationSerializerScopeTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.tenant = Tenant.objects.create(name="Tenant Scope", slug="tenant-scope-lodging")
        self.allowed_site = Site.objects.create(tenant=self.tenant, name="Allowed Site")
        self.blocked_site = Site.objects.create(tenant=self.tenant, name="Blocked Site")
        self.user = User.objects.create_user(email="lodging-scope@test.local", password="TestPass9!")
        self.membership = Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=MembershipRole.SITE_MANAGER,
        )
        self.membership.sites.add(self.allowed_site)

    def _request(self):
        request = self.factory.post("/api/v1/lodging/reservations/")
        request.user = self.user
        request.tenant = self.tenant
        request.tenant_membership = self.membership
        return request

    def test_serializer_rejects_site_outside_membership_scope(self) -> None:
        check_in = date.today() + timedelta(days=1)
        check_out = check_in + timedelta(days=1)
        serializer = ReservationSerializer(
            data={
                "site": str(self.blocked_site.id),
                "guest_name": "Blocked Guest",
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
            },
            context={"request": self._request()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("site", serializer.errors)
