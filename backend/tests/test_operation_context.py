"""Operation context for structured JSON logs (tenant, outlet, user)."""

from __future__ import annotations

import logging
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory

from apps.common.middleware.operation_context import (
    OperationContextLogFilter,
    OperationContextMiddleware,
    operation_context_ctx,
)

User = get_user_model()


class _FakeTenant:
    def __init__(self, pk: uuid.UUID) -> None:
        self.id = pk


@pytest.mark.django_db
def test_operation_context_middleware_staff_session_site() -> None:
    factory = RequestFactory()
    user = User.objects.create_user(email="opctx-site@test.local", password="x")
    tenant_id = uuid.uuid4()
    site_id = uuid.uuid4()
    captured: dict = {}

    def get_response(request):
        captured["ctx"] = operation_context_ctx.get()
        return HttpResponse("ok")

    request = factory.get("/staff/finance/")
    request.user = user
    request.tenant = _FakeTenant(tenant_id)
    request.session = {"staff_site_id": str(site_id)}

    OperationContextMiddleware(get_response)(request)

    assert captured["ctx"]["tenant_id"] == str(tenant_id)
    assert captured["ctx"]["site_id"] == str(site_id)


@pytest.mark.django_db
def test_operation_context_middleware_staff_session_outlet() -> None:
    factory = RequestFactory()
    user = User.objects.create_user(email="opctx-staff@test.local", password="x")
    tenant_id = uuid.uuid4()
    outlet_id = uuid.uuid4()
    captured: dict = {}

    def get_response(request):
        captured["ctx"] = operation_context_ctx.get()
        return HttpResponse("ok")

    request = factory.get("/staff/orders/")
    request.user = user
    request.tenant = _FakeTenant(tenant_id)
    request.session = {"staff_outlet_id": str(outlet_id)}

    OperationContextMiddleware(get_response)(request)

    assert captured["ctx"]["tenant_id"] == str(tenant_id)
    assert captured["ctx"]["user_id"] == str(user.pk)
    assert captured["ctx"]["outlet_id"] == str(outlet_id)


@pytest.mark.django_db
def test_operation_context_middleware_staff_all_outlets_no_outlet_id() -> None:
    factory = RequestFactory()
    captured: dict = {}

    def get_response(request):
        captured["ctx"] = operation_context_ctx.get()
        return HttpResponse("ok")

    request = factory.get("/staff/orders/")
    request.user = User.objects.create_user(email="opctx-all@test.local", password="x")
    request.tenant = _FakeTenant(uuid.uuid4())
    request.session = {"staff_outlet_id": "__all__"}

    OperationContextMiddleware(get_response)(request)
    assert captured["ctx"]["outlet_id"] is None
    assert captured["ctx"]["tenant_id"] is not None


def test_operation_context_middleware_api_outlet_header() -> None:
    factory = RequestFactory()
    oid = uuid.uuid4()
    captured: dict = {}

    def get_response(request):
        captured["ctx"] = operation_context_ctx.get()
        return HttpResponse("ok")

    request = factory.get("/api/v1/orders/", HTTP_X_OUTLET_ID=str(oid))
    request.user = type("Anon", (), {"is_authenticated": False})()
    request.tenant = None

    OperationContextMiddleware(get_response)(request)
    ctx = captured["ctx"]
    assert ctx is not None
    assert ctx["outlet_id"] == str(oid)
    assert ctx["tenant_id"] is None


def test_operation_context_log_filter_enriches_record() -> None:
    token = operation_context_ctx.set(
        {"tenant_id": "t-1", "outlet_id": "o-1", "site_id": "s-1", "user_id": "u-1"}
    )
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        OperationContextLogFilter().filter(record)
        assert record.tenant_id == "t-1"
        assert record.outlet_id == "o-1"
        assert record.user_id == "u-1"
        assert record.site_id == "s-1"
    finally:
        operation_context_ctx.reset(token)
