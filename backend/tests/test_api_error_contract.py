import pytest


@pytest.mark.django_db
def test_token_obtain_validation_includes_error_and_request_id(api_client):
    r = api_client.post("/api/v1/auth/token/", {}, format="json")
    assert r.status_code == 400
    body = r.json()
    assert r.headers.get("X-Request-ID")
    assert body.get("request_id") == r.headers.get("X-Request-ID")
    assert "error" in body
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Invalid input."
    assert isinstance(body["error"]["details"], dict)


@pytest.mark.django_db
def test_health_unaffected_by_api_exception_handler(api_client):
    r = api_client.get("/api/v1/health/")
    assert r.status_code == 200
    assert r.json().get("status") == "OK"
