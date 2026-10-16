"""Customer REST lookups must match branch-scoped staff permissions."""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole
from apps.customers.models import Customer
from apps.lodging.models import Reservation
from apps.tenants.models import Site, Tenant

User = get_user_model()


@pytest.mark.django_db
def test_customer_api_read_only_and_tenant_branch_isolated():
    tenant = Tenant.objects.create(name="API Guest Scope", slug="api-guest-scope")
    other = Tenant.objects.create(name="Unrelated Guest Scope", slug="api-other-guest")
    local_site = Site.objects.create(tenant=tenant, name="Local")
    other_site = Site.objects.create(tenant=tenant, name="Remote")
    user = User.objects.create_user(email="api-guest-scope@test.local", password="TestPass9!")
    membership = Membership.objects.create(tenant=tenant, user=user, role=MembershipRole.FRONT_DESK)
    membership.sites.add(local_site)
    allowed = Customer.objects.create(tenant=tenant, name="Visible guest")
    hidden = Customer.objects.create(tenant=tenant, name="Private remote guest")
    external = Customer.objects.create(tenant=other, name="Other business guest")
    for site, customer in ((local_site, allowed), (other_site, hidden)):
        Reservation.objects.create(
            tenant=tenant, site=site, customer=customer, guest_name=customer.name,
            check_in=date.today(), check_out=date.today() + timedelta(days=1),
        )
    client = APIClient()
    client.force_authenticate(user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.pk)}
    response = client.get("/api/v1/customers/", **headers)
    assert response.status_code == 200, response.content
    results = response.json()["results"]
    assert [row["id"] for row in results] == [str(allowed.pk)]
    assert not client.get(f"/api/v1/customers/{hidden.pk}/", **headers).status_code == 200
    assert client.get(f"/api/v1/customers/{hidden.pk}/", **headers).status_code == 404
    assert client.get(f"/api/v1/customers/{external.pk}/", **headers).status_code == 404
    assert client.post("/api/v1/customers/", {"name": "Unaudited creation"}, format="json", **headers).status_code == 405
    membership.role = MembershipRole.SERVER
    membership.save(update_fields=["role"])
    assert client.get("/api/v1/customers/", **headers).status_code == 403
