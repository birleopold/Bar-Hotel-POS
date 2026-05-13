import pytest
from django.contrib.auth import get_user_model
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Membership, MembershipRole
from apps.tenants.models import Tenant, TenantSettings

User = get_user_model()


@pytest.mark.django_db
def test_invite_create_throttled_after_limit(api_client, monkeypatch):
    """ScopedRateThrottle reads ``THROTTLE_RATES`` from a class attribute; patch it for a strict limit."""
    base = dict(ScopedRateThrottle.THROTTLE_RATES)
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**base, "invite_create": "2/minute"},
    )
    tenant = Tenant.objects.create(name="Inv Throttle", slug="invite-throttle-tenant")
    TenantSettings.objects.get_or_create(tenant=tenant)
    user = User.objects.create_user(email="invthr@test.local", password="TestPass9!")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER)
    assert api_client.login(username=user.email, password="TestPass9!")
    for i in range(2):
        resp = api_client.post(
            "/api/v1/invites/",
            {"email": f"e{i}@x.test"},
            format="json",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        assert resp.status_code == 201, resp.content
    blocked = api_client.post(
        "/api/v1/invites/",
        {"email": "e3@x.test"},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert blocked.status_code == 429
