from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.customers.models import Customer
from apps.lodging.models import Folio, FolioLine, FolioPayment
from apps.staff.services.customer_finance import (
    customer_financial_snapshot,
    customer_receivable_aging,
)
from apps.tenants.models import Site, Tenant


@pytest.mark.django_db
def test_customer_financial_snapshot_includes_folio_tax():
    tenant = Tenant.objects.create(name="AR tax", slug="ar-tax")
    site = Site.objects.create(tenant=tenant, name="Main")
    customer = Customer.objects.create(
        tenant=tenant,
        name="Taxed customer",
    )
    folio = Folio.objects.create(
        tenant=tenant,
        site=site,
        customer=customer,
        guest_name=customer.name,
        currency="UGX",
    )
    FolioLine.objects.create(
        tenant=tenant,
        folio=folio,
        description="Taxed charge",
        amount=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
    )
    FolioPayment.objects.create(
        tenant=tenant,
        folio=folio,
        amount=Decimal("20.00"),
        method="cash",
        idempotency_key="ar-tax-payment",
    )

    snapshot = customer_financial_snapshot(
        tenant=tenant,
        customer=customer,
        site_ids=[site.pk],
        outlet_ids=[],
    )
    assert snapshot["UGX"]["folio_charges"] == Decimal("118")
    assert snapshot["UGX"]["folio_payments"] == Decimal("20")
    assert snapshot["UGX"]["outstanding"] == Decimal("98")


@pytest.mark.django_db
def test_receivable_aging_applies_fifo_payments_and_separates_foreign_currency():
    tenant = Tenant.objects.create(name="AR ageing", slug="ar-ageing")
    site = Site.objects.create(tenant=tenant, name="Main")
    folio = Folio.objects.create(
        tenant=tenant,
        site=site,
        guest_name="Ageing guest",
        currency="UGX",
    )
    old_line = FolioLine.objects.create(
        tenant=tenant,
        folio=folio,
        description="Old taxed charge",
        amount=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
    )
    recent_line = FolioLine.objects.create(
        tenant=tenant,
        folio=folio,
        description="Recent charge",
        amount=Decimal("50.00"),
        tax_amount=Decimal("0.00"),
    )
    now = timezone.now()
    FolioLine.objects.filter(pk=old_line.pk).update(
        created_at=now - timedelta(days=100)
    )
    FolioLine.objects.filter(pk=recent_line.pk).update(
        created_at=now - timedelta(days=10)
    )
    FolioPayment.objects.create(
        tenant=tenant,
        folio=folio,
        amount=Decimal("70.00"),
        method="cash",
        idempotency_key="ar-ageing-payment",
    )
    Folio.objects.create(
        tenant=tenant,
        site=site,
        guest_name="Foreign guest",
        currency="USD",
    )

    result = customer_receivable_aging(
        tenant=tenant,
        site_ids=[site.pk],
        currency="UGX",
        as_of=timezone.localdate(),
    )
    assert result["folio_count"] == 1
    assert result["foreign_currency_folio_count"] == 1
    assert result["totals"]["outstanding"] == Decimal("98.00")
    assert result["totals"]["days_91_plus"] == Decimal("48.00")
    assert result["totals"]["current_0_30"] == Decimal("50.00")
    assert result["totals"]["days_31_60"] == Decimal("0.00")
    assert result["totals"]["days_61_90"] == Decimal("0.00")
    assert result["folios"][0]["customer_name"] == "Ageing guest"
    assert result["method"] == "FIFO charge age; not contractual due-date ageing"
