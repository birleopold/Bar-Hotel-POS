from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Membership, MembershipRole, User
from apps.tenants.models import Site, Tenant

from .models import EventBooking, EventSpace
from .serializers import EventBookingSerializer, EventSpaceSerializer


class EventBookingConstraintTests(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="Events Tenant", slug="events-tenant")
        self.site = Site.objects.create(tenant=self.tenant, name="Events Site")
        self.space = EventSpace.objects.create(tenant=self.tenant, site=self.site, name="Hall A")

    def test_event_booking_rejects_end_before_start_at_db_level(self) -> None:
        start_at = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EventBooking.objects.create(
                    tenant=self.tenant,
                    space=self.space,
                    title="Invalid Event",
                    customer_name="Customer",
                    start_at=start_at,
                    end_at=start_at - timedelta(hours=1),
                )


class EventSerializerScopeTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.tenant = Tenant.objects.create(name="Scope Tenant", slug="scope-tenant-events")
        self.allowed_site = Site.objects.create(tenant=self.tenant, name="Allowed Site")
        self.blocked_site = Site.objects.create(tenant=self.tenant, name="Blocked Site")
        self.allowed_space = EventSpace.objects.create(
            tenant=self.tenant,
            site=self.allowed_site,
            name="Allowed Hall",
        )
        self.blocked_space = EventSpace.objects.create(
            tenant=self.tenant,
            site=self.blocked_site,
            name="Blocked Hall",
        )
        self.user = User.objects.create_user(email="events-scope@test.local", password="TestPass9!")
        self.membership = Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=MembershipRole.SITE_MANAGER,
        )
        self.membership.sites.add(self.allowed_site)

    def _request(self):
        request = self.factory.post("/api/v1/events/bookings/")
        request.user = self.user
        request.tenant = self.tenant
        request.tenant_membership = self.membership
        return request

    def test_event_space_serializer_rejects_site_outside_scope(self) -> None:
        serializer = EventSpaceSerializer(
            data={"site": str(self.blocked_site.id), "name": "New Hall", "capacity": 25},
            context={"request": self._request()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("site", serializer.errors)

    def test_event_booking_serializer_rejects_space_outside_scope(self) -> None:
        start_at = timezone.now() + timedelta(days=1)
        end_at = start_at + timedelta(hours=2)
        serializer = EventBookingSerializer(
            data={
                "space": str(self.blocked_space.id),
                "title": "Blocked Site Event",
                "customer_name": "Guest",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "headcount": 20,
            },
            context={"request": self._request()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("space", serializer.errors)

    def test_event_booking_serializer_accepts_space_within_scope(self) -> None:
        start_at = timezone.now() + timedelta(days=2)
        end_at = start_at + timedelta(hours=2)
        serializer = EventBookingSerializer(
            data={
                "space": str(self.allowed_space.id),
                "title": "Allowed Event",
                "customer_name": "Guest",
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "headcount": 30,
            },
            context={"request": self._request()},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
