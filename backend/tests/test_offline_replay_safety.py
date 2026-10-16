"""Offline replay safety, user-facing manager review and permission isolation."""
import uuid
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.pos.models import OfflineQueuedOperation, OfflineQueueStatus, Order, Payment
from apps.pos.services.catalog_version import catalog_version_payload
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Site, Outlet, OutletType
from tests.test_phase1_isolation_and_idempotency import (
    _create_open_order, _seed_tenant_bundle,
)


@pytest.mark.django_db
def test_stale_catalog_cannot_write_queue_for_forbidden_outlet(api_client):
    a = _seed_tenant_bundle(name="Sync Permission", slug="sync-permission-v3", user_email="sync-permission@test.local")
    other_site = Site.objects.create(tenant=a["tenant"], name="Forbidden site")
    other = Outlet.objects.create(site=other_site, name="Other", outlet_type=OutletType.BAR)
    member = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    member.sites.add(a["site"])
    api_client.login(username=a["user"].email, password="TestPass9!")
    body = {
        "outlet": str(other.id),
        "client_mutation_id": "scope-stale-1",
        "operation_type": "order_create",
        "payload": {
            "catalog_version": "00000000000000000000000000000000",
            "lines": [{"menu_item": str(a["item"].pk), "quantity": "1"}],
        },
    }
    kwargs = {"format": "json", "HTTP_X_TENANT_ID": str(a["tenant"].pk)}
    single = api_client.post("/api/v1/pos/offline-sync/", body, **kwargs)
    assert single.status_code == 403, single.content
    assert not OfflineQueuedOperation.objects.filter(client_mutation_id="scope-stale-1").exists()
    batch = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {"operations": [dict(body, client_mutation_id="scope-stale-2")]},
        **kwargs,
    )
    assert batch.status_code == 200
    assert batch.json()["results"][0]["status_code"] == 403
    assert not OfflineQueuedOperation.objects.filter(client_mutation_id="scope-stale-2").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["card", "mobile_money", "bank", "other"])
def test_electronic_tenders_are_not_falsely_settled_by_offline_replay(api_client, method):
    a = _seed_tenant_bundle(
        name="Offline Cash", slug="offline-cash-" + method,
        user_email="offline-cash-" + method + "@test.local",
    )
    order = _create_open_order(tenant=a["tenant"], outlet=a["outlet"], total="10")
    api_client.login(username=a["user"].email, password="TestPass9!")
    reply = api_client.post(
        "/api/v1/pos/offline-sync/",
        {
            "outlet": str(a["outlet"].pk),
            "client_mutation_id": "unverified-" + method,
            "operation_type": "order_payment",
            "payload": {
                "order_id": str(order.pk), "amount": "10", "method": method,
                "idempotency_key": "no-electronic-" + method,
            },
        },
        format="json", HTTP_X_TENANT_ID=str(a["tenant"].pk),
    )
    assert reply.status_code == 400, reply.content
    assert not Payment.objects.filter(order=order).exists()
    assert not OfflineQueuedOperation.objects.filter(
        tenant=a["tenant"], client_mutation_id="unverified-" + method,
    ).exists()


@pytest.mark.django_db
def test_catalog_stale_retries_only_allow_new_catalog_version(api_client):
    a = _seed_tenant_bundle(name="Stable Replay", slug="stable-replay", user_email="stable-replay@test.local")
    api_client.login(username=a["user"].email, password="TestPass9!")
    base = {
        "outlet": str(a["outlet"].pk),
        "client_mutation_id": "stale-id-safety-1",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].pk), "quantity": "1"}],
            "catalog_version": "00000000000000000000000000000000",
        },
    }
    kwargs = {"format": "json", "HTTP_X_TENANT_ID": str(a["tenant"].pk)}
    first = api_client.post("/api/v1/pos/offline-sync/", base, **kwargs)
    assert first.status_code == 409
    cv = catalog_version_payload(
        tenant_id=a["tenant"].pk, outlet_id=a["outlet"].pk,
    )["catalog_version"]
    unsafe = {
        **base,
        "payload": {
            "lines": [{"menu_item": str(a["item"].pk), "quantity": "2"}],
            "catalog_version": cv,
        },
    }
    denied = api_client.post("/api/v1/pos/offline-sync/", unsafe, **kwargs)
    assert denied.status_code == 400, denied.content
    assert not Order.objects.filter(tenant=a["tenant"]).exists()
    allowed = {
        **base, "payload": {**base["payload"], "catalog_version": cv},
    }
    accepted = api_client.post("/api/v1/pos/offline-sync/", allowed, **kwargs)
    assert accepted.status_code == 201, accepted.content
    assert Order.objects.filter(tenant=a["tenant"]).count() == 1
    original = OfflineQueuedOperation.objects.get(
        tenant=a["tenant"], client_mutation_id="stale-id-safety-1",
    )
    assert original.status == OfflineQueueStatus.APPLIED
    # The serializer stores decimal quantities at the model's three-place precision.
    assert Decimal(original.payload["lines"][0]["quantity"]) == Decimal("1")
    replay = api_client.post("/api/v1/pos/offline-sync/", allowed, **kwargs)
    assert replay.status_code == 200, replay.content
    assert Order.objects.filter(tenant=a["tenant"]).count() == 1


@pytest.mark.django_db
def test_conflict_review_is_manager_only_and_never_posts_payment():
    a = _seed_tenant_bundle(name="Review Queue", slug="review-offline-queue", user_email="review-q@test.local")
    manager = Membership.objects.get(tenant=a["tenant"], user=a["user"])
    entry = OfflineQueuedOperation.objects.create(
        tenant=a["tenant"], outlet=a["outlet"],
        client_mutation_id="conflict-001", operation_type="order_payment",
        payload={"amount": "999999", "method": "card"},
        status=OfflineQueueStatus.FAILED, error_message="Payment not verified",
    )
    client = Client()
    assert client.login(username=a["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(a["tenant"].pk)
    session.save()
    path = reverse("staff-offline-queue")
    r = client.post(path, {
        "action": "review", "operation_id": str(entry.pk),
        "note": "Checked till, statement and supervisor incident log.",
    })
    assert r.status_code in (301, 302), r.content
    entry.refresh_from_db()
    assert entry.status == OfflineQueueStatus.FAILED
    assert entry.reviewed_at is not None
    assert entry.reviewed_by_id == a["user"].pk
    assert entry.review_note
    assert not Payment.objects.filter(tenant=a["tenant"]).exists()
    manager.role = MembershipRole.SERVER
    manager.save(update_fields=["role"])
    rejected = client.post(path, {
        "action": "review", "operation_id": str(entry.pk),
        "note": "Unexpected edit.",
    })
    assert rejected.status_code in (403, 302)
    entry.refresh_from_db()
    assert "Unexpected" not in entry.review_note
