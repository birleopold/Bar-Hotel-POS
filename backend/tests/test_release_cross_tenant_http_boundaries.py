"""P15 HTTP-level negative tests for cross-tenant record isolation."""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.lodging.models import Reservation
from apps.pos.models import Order
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings


@pytest.mark.django_db
def test_retail_operator_cannot_open_another_tenants_order(client):
    ours = Tenant.objects.create(name="Release Retail A", slug="release-retail-a")
    other = Tenant.objects.create(name="Release Retail B", slug="release-retail-b")
    TenantSettings.objects.create(
        tenant=ours, business_lines=["supermarket"], default_currency="UGX",
    )
    TenantSettings.objects.create(
        tenant=other, business_lines=["supermarket"], default_currency="KES",
    )
    our_site = Site.objects.create(tenant=ours, name="Our store")
    other_site = Site.objects.create(tenant=other, name="Other store")
    our_outlet = Outlet.objects.create(
        site=our_site, name="Our till", outlet_type=OutletType.SUPERMARKET,
    )
    other_outlet = Outlet.objects.create(
        site=other_site, name="Other till", outlet_type=OutletType.SUPERMARKET,
    )
    user = get_user_model().objects.create_user(
        email="release-retail-boundary@example.test", password="SafePass!2026",
    )
    membership = Membership.objects.create(
        user=user, tenant=ours, role=MembershipRole.OUTLET_MANAGER,
    )
    membership.sites.add(our_site)
    membership.outlets.add(our_outlet)
    foreign_order = Order.objects.create(
        tenant=other, outlet=other_outlet, currency="KES",
    )

    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(ours.pk)
    session[STAFF_SESSION_OUTLET_KEY] = str(our_outlet.pk)
    session.save()

    response = client.get(
        reverse("staff-order-detail", kwargs={"order_id": foreign_order.pk}),
    )
    assert response.status_code == 404
    assert foreign_order.bill_reference.encode() not in response.content


@pytest.mark.django_db
def test_hotel_operator_cannot_open_another_tenants_reservation(client):
    ours = Tenant.objects.create(name="Release Hotel A", slug="release-hotel-a")
    other = Tenant.objects.create(name="Release Hotel B", slug="release-hotel-b")
    TenantSettings.objects.create(
        tenant=ours, business_lines=["lodging"], default_currency="UGX",
    )
    TenantSettings.objects.create(
        tenant=other, business_lines=["lodging"], default_currency="KES",
    )
    our_site = Site.objects.create(tenant=ours, name="Our property")
    other_site = Site.objects.create(tenant=other, name="Other property")
    Outlet.objects.create(
        site=our_site, name="Reception", outlet_type=OutletType.LODGING_FRONT_DESK,
    )
    Outlet.objects.create(
        site=other_site, name="Reception", outlet_type=OutletType.LODGING_FRONT_DESK,
    )
    user = get_user_model().objects.create_user(
        email="release-hotel-boundary@example.test", password="SafePass!2026",
    )
    membership = Membership.objects.create(
        user=user, tenant=ours, role=MembershipRole.OWNER,
    )
    membership.sites.add(our_site)
    foreign_reservation = Reservation.objects.create(
        tenant=other,
        site=other_site,
        guest_name="Foreign Guest",
        check_in=date.today(),
        check_out=date.today() + timedelta(days=1),
    )

    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(ours.pk)
    session[STAFF_SESSION_SITE_KEY] = str(our_site.pk)
    session.save()

    response = client.get(
        reverse(
            "staff-lodging-reservation-detail",
            kwargs={"reservation_id": foreign_reservation.pk},
        ),
    )
    assert response.status_code == 404
    assert b"Foreign Guest" not in response.content
