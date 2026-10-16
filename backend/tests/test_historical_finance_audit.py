"""Historical posting audit must report inconsistencies without changing books."""
import io
import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.finance.models import (
    CashbookEntry, FinanceCategory, FinanceCategoryKind,
    FinancePostingLink, FinancePostingSource,
)
from apps.tenants.models import Tenant


@pytest.mark.django_db
def test_historical_audit_flags_wrong_category_without_mutating_records():
    first = Tenant.objects.create(name="Audit first", slug="historical-audit-first")
    second = Tenant.objects.create(name="Audit second", slug="historical-audit-second")
    income = FinanceCategory.objects.create(
        tenant=first, name="Income", kind=FinanceCategoryKind.INCOME,
    )
    bad = CashbookEntry.objects.create(
        tenant=first, category=income, amount=Decimal("100.00"),
        transaction_date=timezone.localdate(), reference="Historical test",
    )
    FinancePostingLink.objects.create(
        tenant=first, source_type=FinancePostingSource.POS_REFUND,
        source_id="legacy-refund-one", cashbook_entry=bad,
    )
    other = CashbookEntry.objects.create(
        tenant=second,
        category=FinanceCategory.objects.create(
            tenant=second, name="Income", kind=FinanceCategoryKind.INCOME,
        ),
        amount=Decimal("20.00"), transaction_date=timezone.localdate(),
    )
    FinancePostingLink.objects.create(
        tenant=second, source_type=FinancePostingSource.POS_PAYMENT,
        source_id="other-business", cashbook_entry=other,
    )
    output = io.StringIO()
    call_command("audit_legacy_postings", tenant_id=str(first.pk), stdout=output)
    payload = json.loads(output.getvalue())
    assert payload["tenant_id"] == str(first.pk)
    assert len(payload["suspect_posting_links"]) == 1
    assert payload["suspect_posting_links"][0]["issues"] == ["unexpected_category_kind"]
    assert payload["suspect_posting_links"][0]["source_id"] == "legacy-refund-one"
    assert FinancePostingLink.objects.count() == 2
    bad.refresh_from_db()
    assert bad.category_id == income.pk
    assert bad.amount == Decimal("100.00")


@pytest.mark.django_db
def test_historical_audit_requires_valid_tenant():
    with pytest.raises(CommandError):
        call_command("audit_legacy_postings", tenant_id="not-a-uuid")
