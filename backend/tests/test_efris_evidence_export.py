from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import Membership, MembershipRole
from apps.audit.models import AuditEvent
from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.integrations.models import EfrisSubmission, EfrisSubmissionStatus
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.models import Tenant, TenantSettings


def _submission(*, tenant, user, suffix, secret):
    category = FinanceCategory.objects.create(
        tenant=tenant,
        name=f"Sales {suffix}",
        kind=FinanceCategoryKind.INCOME,
    )
    entry = CashbookEntry.objects.create(
        tenant=tenant,
        category=category,
        amount=Decimal("12500.00"),
        transaction_date=date(2026, 10, 25),
        reference=f"REF-{suffix}",
        created_by=user,
    )
    return EfrisSubmission.objects.create(
        tenant=tenant,
        cashbook_entry=entry,
        payload={
            "invoice": f"INV-{suffix}",
            "customer": {"name": "Example customer"},
            "secret_marker": secret,
        },
        status=EfrisSubmissionStatus.FAILED,
        attempts=2,
        last_error=f"provider rejected token={secret}",
        provider_reference=f"URA-{suffix}",
    )


@pytest.mark.django_db
def test_efris_evidence_export_is_tenant_scoped_and_hash_only(client):
    user = get_user_model().objects.create_user(
        email="efris-owner@example.test",
        password="StrongPassword!2026",
    )
    first = Tenant.objects.create(name="First EFRIS tenant", slug="first-efris")
    second = Tenant.objects.create(name="Second EFRIS tenant", slug="second-efris")
    TenantSettings.objects.create(tenant=first)
    TenantSettings.objects.create(tenant=second)
    Membership.objects.create(user=user, tenant=first, role=MembershipRole.OWNER)
    own = _submission(tenant=first, user=user, suffix="OWN", secret="OWN-SECRET")
    other = _submission(tenant=second, user=user, suffix="OTHER", secret="OTHER-SECRET")

    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(first.pk)
    session.save()

    response = client.get(reverse("staff-workspace-efris-evidence"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    body = response.content.decode("utf-8")
    assert str(own.pk) in body
    assert str(other.pk) not in body
    assert "OWN-SECRET" not in body
    assert "OTHER-SECRET" not in body
    assert '"secret_marker"' not in body
    assert "payload_sha256" in body
    assert "last_error_sha256" in body
    assert "provider_response_retained" in body
    assert "URA-OWN" in body
    assert AuditEvent.objects.filter(
        tenant=first,
        action="staff.efris_evidence_exported",
    ).exists()


@pytest.mark.django_db
def test_efris_evidence_export_requires_workspace_admin(client):
    user = get_user_model().objects.create_user(
        email="efris-server@example.test",
        password="StrongPassword!2026",
    )
    tenant = Tenant.objects.create(name="EFRIS restricted", slug="efris-restricted")
    TenantSettings.objects.create(tenant=tenant)
    Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.SERVER)

    client.force_login(user)
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(tenant.pk)
    session.save()

    response = client.get(reverse("staff-workspace-efris-evidence"))
    assert response.status_code == 302
    assert response["Location"] == reverse("staff-workspace-efris")
