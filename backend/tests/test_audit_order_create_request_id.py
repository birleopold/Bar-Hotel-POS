from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.catalog.models import MenuCategory, MenuItem
from apps.tenants.models import Outlet, OutletType, Site, Tenant, TenantSettings

User = get_user_model()


@pytest.mark.django_db
def test_order_create_audit_payload_has_request_id_and_source_api(api_client):
    tenant = Tenant.objects.create(name="Audit POS", slug="audit-pos-tenant")
    TenantSettings.objects.get_or_create(tenant=tenant)
    site = Site.objects.create(tenant=tenant, name="Main")
    outlet = Outlet.objects.create(site=site, name="Bar", outlet_type=OutletType.BAR)
    cat = MenuCategory.objects.create(tenant=tenant, name="Drinks")
    item = MenuItem.objects.create(
        tenant=tenant,
        category=cat,
        name="Beer",
        unit_price=Decimal("5.00"),
    )
    user = User.objects.create_user(email="audpos@test.local", password="TestPass9!")
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.SERVER)
    assert api_client.login(username=user.email, password="TestPass9!")
    r = api_client.post(
        "/api/v1/orders/",
        {
            "outlet": str(outlet.id),
            "lines": [{"menu_item": str(item.id), "quantity": "1"}],
        },
        format="json",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert r.status_code == 201, r.content
    ev = AuditEvent.objects.filter(action="order.created").order_by("-created_at").first()
    assert ev is not None
    assert ev.payload.get("source") == "api"
    rid = ev.payload.get("request_id")
    assert rid
    assert r["X-Request-ID"] == rid
