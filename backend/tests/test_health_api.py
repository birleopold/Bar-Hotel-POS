import pytest


@pytest.mark.django_db
def test_health_ok(api_client):
    r = api_client.get("/api/v1/health/")
    assert r.status_code == 200
    assert r.json().get("status") == "OK"
