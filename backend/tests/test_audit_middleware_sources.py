import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.audit.context import get_audit_request_context
from apps.audit.middleware import AuditRequestContextMiddleware


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/v1/orders/", "api"),
        ("/staff/dashboard/", "staff"),
        ("/console/org/", "console"),
    ],
)
def test_audit_middleware_sets_source(path, expected):
    factory = RequestFactory()
    captured: dict = {}

    def get_response(request):
        captured["ctx"] = dict(get_audit_request_context())
        return HttpResponse("ok")

    request = factory.get(path)
    request.request_id = "trace-1"
    AuditRequestContextMiddleware(get_response)(request)
    assert captured["ctx"].get("source") == expected
    assert captured["ctx"].get("request_id") == "trace-1"
