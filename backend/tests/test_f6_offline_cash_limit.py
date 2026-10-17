"""F6 offline cash ceiling: actual server replay enforcement and owner UI."""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.pos.models import Order, Payment
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import TenantSettings
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle, _create_open_order


@pytest.mark.django_db
def test_offline_cash_above_owner_limit_is_not_posted(api_client):
    data = _seed_tenant_bundle(name="F6 Offline Ceiling", slug="f6-offline-ceiling", user_email="f6-offline@example.test")
    settings, _ = TenantSettings.objects.get_or_create(tenant=data["tenant"])
    settings.default_currency = "USD"
    settings.offline_cash_payment_limit = Decimal("5.00")
    settings.save(update_fields=["default_currency", "offline_cash_payment_limit"])
    order = _create_open_order(tenant=data["tenant"], outlet=data["outlet"], total="10.00")
    assert api_client.login(username=data["user"].email, password="TestPass9!")
    response = api_client.post(
        "/api/v1/pos/offline-sync/",
        {
            "outlet": str(data["outlet"].pk),
            "client_mutation_id": "f6-over-cap-1",
            "operation_type": "order_payment",
            "payload": {
                "order_id": str(order.pk), "amount": "6.00", "method": "cash",
                "idempotency_key": "f6-exceeds-cash-ceiling",
            },
        },
        format="json", HTTP_X_TENANT_ID=str(data["tenant"].pk),
    )
    assert response.status_code == 400, response.content
    assert not Payment.objects.filter(order=order).exists()
    assert Order.objects.get(pk=order.pk).is_paid is False


@pytest.mark.django_db
def test_offline_cash_ceiling_rejects_different_currency_without_exchange_rate(api_client):
    data = _seed_tenant_bundle(name="F6 Cash Currency", slug="f6-cash-currency", user_email="f6-currency@example.test")
    settings, _ = TenantSettings.objects.get_or_create(tenant=data["tenant"])
    settings.default_currency = "UGX"
    settings.offline_cash_payment_limit = Decimal("500000")
    settings.save(update_fields=["default_currency", "offline_cash_payment_limit"])
    order = _create_open_order(tenant=data["tenant"], outlet=data["outlet"], total="10.00")
    assert api_client.login(username=data["user"].email, password="TestPass9!")
    response = api_client.post(
        "/api/v1/pos/offline-sync/",
        {
            "outlet": str(data["outlet"].pk),
            "client_mutation_id": "f6-cross-currency",
            "operation_type": "order_payment",
            "payload": {
                "order_id": str(order.pk), "amount": "4.00", "method": "cash",
                "idempotency_key": "f6-cross-currency-cash",
            },
        },
        format="json", HTTP_X_TENANT_ID=str(data["tenant"].pk),
    )
    assert response.status_code == 400, response.content
    assert not Payment.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_owner_can_set_limit_in_existing_offline_monitor_and_invalid_limit_rejected():
    data = _seed_tenant_bundle(name="F6 Offline Policy", slug="f6-offline-policy", user_email="f6-offline-owner@example.test")
    client = Client()
    assert client.login(username=data["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(data["tenant"].pk)
    session.save()
    url = reverse("staff-offline-queue")
    page = client.get(url)
    assert page.status_code == 200
    assert b"Offline cash payment limit" in page.content
    allowed = client.post(url, {"action": "cash_limit", "cash_limit": "500000.00"})
    assert allowed.status_code == 302
    settings = TenantSettings.objects.get(tenant=data["tenant"])
    assert settings.offline_cash_payment_limit == Decimal("500000.00")
    for invalid in ("NaN", "-1", "500000.001", "1000000000000"):
        result = client.post(url, {"action": "cash_limit", "cash_limit": invalid})
        assert result.status_code == 302
        settings.refresh_from_db()
        assert settings.offline_cash_payment_limit == Decimal("500000.00")
    member = Membership.objects.get(user=data["user"], tenant=data["tenant"])
    member.role = MembershipRole.STOREKEEPER
    member.save(update_fields=["role"])
    blocked = client.post(url, {"action": "cash_limit", "cash_limit": "100"})
    assert blocked.status_code in (403, 302)
    settings.refresh_from_db()
    assert settings.offline_cash_payment_limit == Decimal("500000.00")


@pytest.mark.django_db
def test_offline_cash_exact_replay_does_not_fail_after_limit_is_reduced(api_client):
    data = _seed_tenant_bundle(
        name="F6 Offline Replay Policy", slug="f6-replay-policy",
        user_email="f6-policy-replay@example.test",
    )
    settings, _ = TenantSettings.objects.get_or_create(tenant=data["tenant"])
    settings.default_currency = "USD"
    settings.offline_cash_payment_limit = Decimal("12.00")
    settings.save(update_fields=["default_currency", "offline_cash_payment_limit"])
    order = _create_open_order(tenant=data["tenant"], outlet=data["outlet"], total="10")
    assert api_client.login(username=data["user"].email, password="TestPass9!")
    payload = {
        "outlet": str(data["outlet"].pk),
        "client_mutation_id": "offline-policy-replay-1",
        "operation_type": "order_payment",
        "payload": {
            "order_id": str(order.pk), "amount": "10.00", "method": "cash",
            "idempotency_key": "offline-policy-replay-payment",
        },
    }
    kwargs = {"format": "json", "HTTP_X_TENANT_ID": str(data["tenant"].pk)}
    first = api_client.post("/api/v1/pos/offline-sync/", payload, **kwargs)
    assert first.status_code == 201, first.content
    assert Payment.objects.filter(order=order).count() == 1
    settings.offline_cash_payment_limit = Decimal("5")
    settings.save(update_fields=["offline_cash_payment_limit"])
    replay = api_client.post("/api/v1/pos/offline-sync/", payload, **kwargs)
    assert replay.status_code == 200, replay.content
    assert Payment.objects.filter(order=order).count() == 1
    next_order = _create_open_order(tenant=data["tenant"], outlet=data["outlet"], total="10")
    new_payload = {
        **payload,
        "client_mutation_id": "offline-policy-replay-2",
        "payload": {**payload["payload"], "order_id": str(next_order.pk),
                    "idempotency_key": "offline-policy-new-payment"},
    }
    rejected = api_client.post("/api/v1/pos/offline-sync/", new_payload, **kwargs)
    assert rejected.status_code == 400, rejected.content
    assert not Payment.objects.filter(order=next_order).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-1", "0", "2.123", "not-money"])
def test_offline_cash_invalid_amount_fails_without_financial_posting(api_client, invalid):
    data = _seed_tenant_bundle(
        name="F6 Invalid Money " + invalid, slug="f6-invalid-money-" + str(abs(hash(invalid))),
        user_email="f6-invalid-" + str(abs(hash(invalid))) + "@example.test",
    )
    order = _create_open_order(tenant=data["tenant"], outlet=data["outlet"], total="10")
    assert api_client.login(username=data["user"].email, password="TestPass9!")
    result = api_client.post("/api/v1/pos/offline-sync/", {
        "outlet": str(data["outlet"].pk),
        "client_mutation_id": "f6-invalid-" + str(abs(hash(invalid))),
        "operation_type": "order_payment",
        "payload": {
            "order_id": str(order.pk), "amount": invalid, "method": "cash",
            "idempotency_key": "f6-invalid-" + str(abs(hash(invalid))),
        },
    }, format="json", HTTP_X_TENANT_ID=str(data["tenant"].pk))
    assert result.status_code == 400, result.content
    assert not Payment.objects.filter(order=order).exists()
