"""P15 HTTP-level role boundaries for operational staff workspaces."""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.lodging.models import Reservation, Room, RoomType
from apps.staff.middleware import STAFF_SESSION_SITE_KEY, STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


@pytest.mark.django_db
def test_housekeeper_can_open_housekeeping_but_not_front_desk_reservation(client):
    tenant = Tenant.objects.create(name="Release Hotel Roles", slug="release-hotel-roles")
    TenantSettings.objects.create(
        tenant=tenant,
        business_lines=["lodging"],
        default_currency="UGX",
        enabled_staff_modules=["lodging", "workspace"],
    )
    site = Site.objects.create(tenant=tenant, name="Main property")
    Outlet.objects.create(
        site=site,
        name="Reception",
        outlet_type=OutletType.LODGING_FRONT_DESK,
    )
    room_type = RoomType.objects.create(
        tenant=tenant,
        site=site,
        name="Standard",
    )
    user = get_user_model().objects.create_user(
        email="release-housekeeper@example.test",
        password="SafePass!2026",
    )
    membership = Membership.objects.create(
        user=user,
        tenant=tenant,
        role=MembershipRole.CLEANER,
    )
    membership.sites.add(site)
    room = Room.objects.create(
        room_type=room_type,
        name="101",
        status="dirty",
        assigned_housekeeper=user,
    )
    reservation = Reservation.objects.create(
        tenant=tenant,
        site=site,
        room=room,
        guest_name="Front Desk Only Guest",
        check_in=date.today(),
        check_out=date.today() + timedelta(days=1),
    )

    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
    session[STAFF_SESSION_SITE_KEY] = str(site.pk)
    session.save()

    housekeeping = client.get(reverse("staff-lodging-housekeeping"))
    assert housekeeping.status_code == 200
    assert room.name.encode() in housekeeping.content

    reservation_page = client.get(
        reverse(
            "staff-lodging-reservation-detail",
            kwargs={"reservation_id": reservation.pk},
        ),
    )
    assert reservation_page.status_code == 302
    assert reservation_page["Location"] == reverse("staff-dashboard")
    assert b"Front Desk Only Guest" not in reservation_page.content
