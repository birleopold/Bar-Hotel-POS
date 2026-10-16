"""Executive reporting reuses scoped sales data; no parallel ledger."""
import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership, MembershipRole
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_owner_executive_sales_report_has_bounded_period_and_empty_state():
    fixture = _seed_tenant_bundle(
        name="Executive report example", slug="executive-report-example",
        user_email="executive-report-owner@test.local",
    )
    client = Client()
    assert client.login(username=fixture["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(fixture["tenant"].pk)
    session.save()
    path = reverse("staff-management")
    response = client.get(path, {"view": "reports"})
    assert response.status_code == 200
    assert response.context["executive_sales"]["gross_sales"] == 0
    assert b"Executive sales overview" in response.content
    assert b"No payments recorded" in response.content

    invalid = client.get(path, {"view": "reports", "date_from": "2025-01-01", "date_to": "2025-03-01"})
    assert invalid.status_code == 200
    assert "executive_error" in invalid.context
    assert "executive_sales" not in invalid.context

    member = Membership.objects.get(tenant=fixture["tenant"], user=fixture["user"])
    member.role = MembershipRole.SERVER
    member.save(update_fields=["role"])
    denied = client.get(path, {"view": "reports"})
    assert denied.status_code == 403
