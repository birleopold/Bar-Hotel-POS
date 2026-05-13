"""Staff UI for POS offline sync monitoring."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.pos.services.catalog_version import catalog_version_payload
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_staff_offline_queue_lists_catalog_fingerprints_for_accessible_outlets():
    """Page context includes server catalog pins so staff can compare to device payloads."""
    a = _seed_tenant_bundle(
        name="Staff OQ",
        slug="staff-oq",
        user_email="staffoq@test.local",
    )
    client = Client()
    assert client.login(username=a["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(a["tenant"].id)
    session.save()

    url = reverse("staff-offline-queue")
    r = client.get(url)
    assert r.status_code == 200, r.content[:500]
    ctx = r.context
    if isinstance(ctx, list):
        ctx = ctx[-1]
    catalog_by_outlet = ctx["catalog_by_outlet"]
    oid = str(a["outlet"].id)
    assert oid in catalog_by_outlet
    snap = catalog_by_outlet[oid]
    assert len(snap["catalog_version"]) == 32
    assert snap["catalog_version"] == catalog_version_payload(
        tenant_id=a["tenant"].id, outlet_id=a["outlet"].id
    )["catalog_version"]
