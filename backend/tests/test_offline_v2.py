"""Offline POS v2: catalog version pin + order_create replay queue."""

import uuid
from decimal import Decimal

import pytest

from apps.pos.models import OfflineQueuedOperation, Order, OrderStatus, PaymentMethod
from apps.pos.services.catalog_version import catalog_version_payload
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_pos_catalog_version_endpoint(api_client):
    a = _seed_tenant_bundle(name="CV Tenant", slug="cv-tenant", user_email="cv@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    r = api_client.get(
        "/api/v1/pos/catalog-version/",
        {"outlet": str(a["outlet"].id)},
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["outlet"] == str(a["outlet"].id)
    assert len(body["catalog_version"]) == 32
    assert "as_of" in body


@pytest.mark.django_db
def test_catalog_version_payload_changes_when_menu_item_updates():
    a = _seed_tenant_bundle(name="CV Chg", slug="cv-chg", user_email="cvchg@test.local")
    v1 = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    a["item"].unit_price = Decimal("9.99")
    a["item"].save(update_fields=["unit_price", "updated_at"])
    v2 = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    assert v1 != v2


@pytest.mark.django_db
def test_offline_order_create_applies_and_sets_applied_order_id(api_client):
    a = _seed_tenant_bundle(name="OC Tenant", slug="oc-tenant", user_email="oc@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    payload = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "device-1:create-001",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "2"}],
            "catalog_version": cv,
            "table_label": "Tab A",
        },
    }
    r = api_client.post(
        "/api/v1/pos/offline-sync/",
        payload,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 201, r.content
    data = r.json()
    assert data["replay"] is False
    oid = data["queue"].get("applied_order_id")
    assert oid
    order = Order.objects.get(id=oid)
    assert order.status == OrderStatus.OPEN
    assert order.lines.count() == 1
    assert order.table_label == "Tab A"


@pytest.mark.django_db
def test_offline_order_create_replay_is_idempotent(api_client):
    a = _seed_tenant_bundle(name="OC Rep", slug="oc-rep", user_email="ocrep@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    body = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "device-1:create-rep",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
            "catalog_version": cv,
        },
    }
    first = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert first.status_code == 201
    second = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert second.status_code == 200
    assert second.json()["replay"] is True
    assert Order.objects.filter(tenant=a["tenant"], outlet=a["outlet"]).count() == 1


@pytest.mark.django_db
def test_offline_order_create_catalog_stale_returns_409(api_client):
    a = _seed_tenant_bundle(name="OC Stale", slug="oc-stale", user_email="ocstale@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    stale_token = "0" * 32
    payload = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "device-1:create-stale",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
            "catalog_version": stale_token,
        },
    }
    r = api_client.post(
        "/api/v1/pos/offline-sync/",
        payload,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 409, r.content
    err = r.json()["error"]
    assert err["code"] == "catalog_stale"
    assert len(err["server_catalog_version"]) == 32
    row = OfflineQueuedOperation.objects.get(tenant=a["tenant"], client_mutation_id="device-1:create-stale")
    assert row.status == "failed"
    assert "catalog_stale" in row.error_message
    assert row.payload.get("catalog_version") == stale_token


@pytest.mark.django_db
def test_offline_catalog_stale_retry_with_fresh_catalog_applies(api_client):
    a = _seed_tenant_bundle(name="OC Stale Retry", slug="oc-stale-retry", user_email="ocstaleretry@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    stale_token = "0" * 32
    first = api_client.post(
        "/api/v1/pos/offline-sync/",
        {
            "outlet": str(a["outlet"].id),
            "client_mutation_id": "device-1:retry-after-stale",
            "operation_type": "order_create",
            "payload": {
                "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                "catalog_version": stale_token,
            },
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert first.status_code == 409
    row = OfflineQueuedOperation.objects.get(tenant=a["tenant"], client_mutation_id="device-1:retry-after-stale")
    assert row.status == "failed"
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    second = api_client.post(
        "/api/v1/pos/offline-sync/",
        {
            "outlet": str(a["outlet"].id),
            "client_mutation_id": "device-1:retry-after-stale",
            "operation_type": "order_create",
            "payload": {
                "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                "catalog_version": cv,
            },
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert second.status_code == 201, second.content
    row.refresh_from_db()
    assert row.status == "applied"


@pytest.mark.django_db
def test_offline_order_create_without_catalog_version_succeeds(api_client):
    a = _seed_tenant_bundle(name="OC NoCV", slug="oc-nocv", user_email="nocv@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    payload = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "device-1:create-nocv",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
        },
    }
    r = api_client.post(
        "/api/v1/pos/offline-sync/",
        payload,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 201, r.content


@pytest.mark.django_db
def test_offline_order_add_lines_appends_and_replay(api_client):
    a = _seed_tenant_bundle(name="AddLines", slug="add-lines", user_email="addlines@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    base = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "al-base",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
            "catalog_version": cv,
        },
    }
    r0 = api_client.post(
        "/api/v1/pos/offline-sync/",
        base,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r0.status_code == 201
    oid = r0.json()["queue"]["applied_order_id"]
    body = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "al-append",
        "operation_type": "order_add_lines",
        "payload": {
            "order_id": oid,
            "lines": [{"menu_item": str(a["item"].id), "quantity": "2"}],
            "catalog_version": cv,
        },
    }
    r1 = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r1.status_code == 201, r1.content
    order = Order.objects.get(id=oid)
    assert order.lines.count() == 2
    r2 = api_client.post(
        "/api/v1/pos/offline-sync/",
        body,
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r2.status_code == 200
    assert r2.json()["replay"] is True
    order.refresh_from_db()
    assert order.lines.count() == 2


@pytest.mark.django_db
def test_offline_batch_create_then_add_lines(api_client):
    a = _seed_tenant_bundle(name="Batch OL", slug="batch-ol", user_email="batchol@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    create_op = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "batch:create",
        "operation_type": "order_create",
        "payload": {
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
            "catalog_version": cv,
        },
    }
    r0 = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {"operations": [create_op]},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r0.status_code == 200
    res0 = r0.json()["results"][0]
    assert res0["ok"] is True
    oid = res0["queue"]["applied_order_id"]
    add_op = {
        "outlet": str(a["outlet"].id),
        "client_mutation_id": "batch:add",
        "operation_type": "order_add_lines",
        "payload": {
            "order_id": oid,
            "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
            "catalog_version": cv,
        },
    }
    r1 = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {"operations": [add_op]},
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r1.status_code == 200
    res1 = r1.json()["results"][0]
    assert res1["ok"] is True
    order = Order.objects.get(id=oid)
    assert order.lines.count() == 2


@pytest.mark.django_db
def test_offline_batch_depends_on_chains_create_and_add_lines(api_client):
    a = _seed_tenant_bundle(name="Dep Chain", slug="dep-chain", user_email="depchain@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:create",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:add",
                    "operation_type": "order_add_lines",
                    "depends_on": 0,
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "2"}],
                        "catalog_version": cv,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["ok"] and res[1]["ok"]
    oid = res[0]["queue"]["applied_order_id"]
    assert res[1]["queue"]["applied_order_id"] == oid
    assert Order.objects.get(id=oid).lines.count() == 2


@pytest.mark.django_db
def test_offline_batch_depends_on_chains_create_and_pay(api_client):
    a = _seed_tenant_bundle(name="Dep Pay", slug="dep-pay", user_email="deppay@test.local")
    a["item"].kds_station = "bar"
    a["item"].track_inventory = False
    a["item"].save(update_fields=["kds_station", "track_inventory", "updated_at"])
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:pay-create",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:pay",
                    "operation_type": "order_payment",
                    "depends_on": 0,
                    "payload": {
                        "idempotency_key": "offline-batch-pay-1",
                        "amount": "5.00",
                        "method": PaymentMethod.CASH,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["ok"] and res[1]["ok"]
    oid = res[0]["queue"]["applied_order_id"]
    order = Order.objects.get(id=oid)
    assert order.is_paid


@pytest.mark.django_db
def test_offline_batch_depends_on_create_add_pay(api_client):
    a = _seed_tenant_bundle(name="Dep CAP", slug="dep-cap", user_email="depcap@test.local")
    a["item"].kds_station = "bar"
    a["item"].track_inventory = False
    a["item"].save(update_fields=["kds_station", "track_inventory", "updated_at"])
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "cap:create",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "cap:add",
                    "operation_type": "order_add_lines",
                    "depends_on": 0,
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "cap:pay",
                    "operation_type": "order_payment",
                    "depends_on": 1,
                    "payload": {
                        "idempotency_key": "offline-cap-pay",
                        "amount": "10.00",
                        "method": PaymentMethod.CASH,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["ok"] and res[1]["ok"] and res[2]["ok"]
    oid = res[0]["queue"]["applied_order_id"]
    order = Order.objects.get(id=oid)
    assert order.is_paid
    assert order.lines.count() == 2


@pytest.mark.django_db
def test_offline_batch_depends_on_rejects_order_id_and_depends_on_together(api_client):
    a = _seed_tenant_bundle(name="Dep Both", slug="dep-both", user_email="depboth@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    oid = str(uuid.uuid4())
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:x",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:y",
                    "operation_type": "order_add_lines",
                    "depends_on": 0,
                    "payload": {
                        "order_id": oid,
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_offline_batch_payment_depends_on_rejects_order_id_and_depends_on_together(api_client):
    a = _seed_tenant_bundle(name="Dep PayBoth", slug="dep-payboth", user_email="payboth@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    oid = str(uuid.uuid4())
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "payboth:create",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "payboth:pay",
                    "operation_type": "order_payment",
                    "depends_on": 0,
                    "payload": {
                        "order_id": oid,
                        "idempotency_key": "x",
                        "amount": "5.00",
                        "method": PaymentMethod.CASH,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_offline_batch_depends_on_must_be_prior_index(api_client):
    a = _seed_tenant_bundle(name="DepFwd", slug="dep-fwd", user_email="depfwd@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:f1",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:f2",
                    "operation_type": "order_add_lines",
                    "depends_on": 1,
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    assert r.json()["results"][0]["ok"] is True
    row = r.json()["results"][1]
    assert row["ok"] is False
    assert row["error"]["code"] == "invalid_depends_on"


@pytest.mark.django_db
def test_offline_batch_depends_on_after_failed_prior(api_client):
    a = _seed_tenant_bundle(name="DepFail", slug="dep-fail", user_email="depfail@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    cv = catalog_version_payload(tenant_id=a["tenant"].id, outlet_id=a["outlet"].id)["catalog_version"]
    bad = uuid.uuid4()
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(bad),
                    "client_mutation_id": "dep:bad-outlet",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "dep:after-bad",
                    "operation_type": "order_add_lines",
                    "depends_on": 0,
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": cv,
                    },
                },
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    res = r.json()["results"]
    assert res[0]["ok"] is False
    assert res[1]["ok"] is False
    assert res[1]["error"]["code"] == "depends_on_failed"


@pytest.mark.django_db
def test_offline_batch_catalog_stale_records_queue_row(api_client):
    a = _seed_tenant_bundle(name="Batch Stale", slug="batch-stale", user_email="batchstale@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    stale_token = "0" * 32
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(a["outlet"].id),
                    "client_mutation_id": "batch:stale-cv",
                    "operation_type": "order_create",
                    "payload": {
                        "lines": [{"menu_item": str(a["item"].id), "quantity": "1"}],
                        "catalog_version": stale_token,
                    },
                }
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["ok"] is False
    assert res["status_code"] == 409
    assert res["error"]["code"] == "catalog_stale"
    row = OfflineQueuedOperation.objects.get(tenant=a["tenant"], client_mutation_id="batch:stale-cv")
    assert row.status == "failed"
    assert "catalog_stale" in row.error_message
    assert row.payload.get("catalog_version") == stale_token


@pytest.mark.django_db
def test_offline_batch_invalid_outlet_entry(api_client):
    a = _seed_tenant_bundle(name="Batch Bad", slug="batch-bad", user_email="batchbad@test.local")
    assert api_client.login(username=a["user"].email, password="TestPass9!")
    bad_outlet = uuid.uuid4()
    r = api_client.post(
        "/api/v1/pos/offline-sync/batch/",
        {
            "operations": [
                {
                    "outlet": str(bad_outlet),
                    "client_mutation_id": "bad-outlet",
                    "operation_type": "order_create",
                    "payload": {"lines": [{"menu_item": str(a["item"].id), "quantity": "1"}]},
                }
            ]
        },
        format="json",
        HTTP_X_TENANT_ID=str(a["tenant"].id),
    )
    assert r.status_code == 200
    row = r.json()["results"][0]
    assert row["ok"] is False
    assert row["status_code"] == 400
