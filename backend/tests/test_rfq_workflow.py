from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.catalog.models import MenuItem
from apps.purchasing.models import (
    PurchaseApprovalStatus,
    PurchaseOrder,
    PurchaseRfqStatus,
    Supplier,
    SupplierQuoteStatus,
)
from apps.purchasing.serializers import PurchaseOrderSerializer
from apps.purchasing.rfq import (
    award_supplier_quote,
    cancel_rfq,
    create_rfq,
    invite_supplier_to_rfq,
    quote_comparison_rows,
    record_supplier_quote,
)
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def _env(slug="rfq-flow"):
    env = _seed_tenant_bundle(
        name="RFQ Flow",
        slug=slug,
        user_email=f"{slug}@example.test",
    )
    member = Membership.objects.get(
        tenant=env["tenant"], user=env["user"],
    )
    member.sites.add(env["site"])
    member.outlets.add(env["outlet"])
    second_item = MenuItem.objects.create(
        tenant=env["tenant"],
        category=env["category"],
        name="RFQ second item",
        sku=f"{slug}-ITEM-2",
        unit_price=Decimal("10.00"),
        track_inventory=True,
    )
    supplier_a = Supplier.objects.create(
        tenant=env["tenant"], name="Alpha Supplier",
    )
    supplier_b = Supplier.objects.create(
        tenant=env["tenant"], name="Beta Supplier",
    )
    env.update(
        member=member,
        second_item=second_item,
        supplier_a=supplier_a,
        supplier_b=supplier_b,
    )
    return env


def _rfq(env):
    return create_rfq(
        tenant=env["tenant"],
        outlet=env["outlet"],
        membership=env["member"],
        user=env["user"],
        reference="RFQ-TEST-001",
        needed_by=timezone.localdate() + timedelta(days=10),
        notes="Compare total landed purchase offer before ordering",
        lines=[
            {"menu_item": env["item"], "quantity": "10"},
            {"menu_item": env["second_item"], "quantity": "5"},
        ],
    )


def _record(quote, env, *, first_cost, second_cost, shipping, available=None, valid_until=None):
    lines = list(quote.rfq.lines.order_by("menu_item__name"))
    item_map = {line.menu_item_id: line for line in lines}
    return record_supplier_quote(
        quote=quote,
        user=env["user"],
        reference=f"QUOTE-{quote.supplier.name[:1]}",
        shipping_cost=shipping,
        other_cost=Decimal("0"),
        lead_time_days=4,
        payment_terms="30 days",
        valid_until=valid_until or (timezone.localdate() + timedelta(days=14)),
        lines=[
            {
                "rfq_line": item_map[env["item"].pk],
                "unit_cost": first_cost,
                "quantity_available": available,
                "promised_date": timezone.localdate() + timedelta(days=4),
            },
            {
                "rfq_line": item_map[env["second_item"].pk],
                "unit_cost": second_cost,
                "quantity_available": None,
                "promised_date": timezone.localdate() + timedelta(days=4),
            },
        ],
    )


@pytest.mark.django_db
def test_rfq_compares_complete_supplier_total_and_awards_existing_po_flow():
    env = _env("rfq-compare")
    rfq = _rfq(env)
    quote_a = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_a"], user=env["user"],
    )
    quote_b = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_b"], user=env["user"],
    )
    _record(
        quote_a, env,
        first_cost=Decimal("4.00"), second_cost=Decimal("8.00"),
        shipping=Decimal("30.00"),
    )
    _record(
        quote_b, env,
        first_cost=Decimal("4.50"), second_cost=Decimal("8.50"),
        shipping=Decimal("5.00"),
    )
    rfq.refresh_from_db()
    rows = quote_comparison_rows(rfq)
    by_name = {row["supplier"].name: row for row in rows}
    assert by_name["Alpha Supplier"]["total"] == Decimal("110.00")
    assert by_name["Beta Supplier"]["total"] == Decimal("92.50")
    assert by_name["Beta Supplier"]["best_price"] is True
    assert by_name["Alpha Supplier"]["best_price"] is False

    po = award_supplier_quote(
        quote=quote_b,
        membership=env["member"],
        user=env["user"],
    )
    assert po.status == "draft"
    assert po.approval_status == PurchaseApprovalStatus.APPROVED
    assert po.supplier == env["supplier_b"]
    assert po.lines.count() == 2
    costs = {
        line.menu_item_id: line.unit_cost for line in po.lines.all()
    }
    assert costs[env["item"].pk] == Decimal("4.50")
    assert costs[env["second_item"].pk] == Decimal("8.50")
    quote_b.refresh_from_db()
    quote_a.refresh_from_db()
    rfq.refresh_from_db()
    assert quote_b.status == SupplierQuoteStatus.ACCEPTED
    assert quote_b.converted_purchase_order == po
    assert quote_a.status == SupplierQuoteStatus.REJECTED
    assert rfq.status == PurchaseRfqStatus.AWARDED

    replay = award_supplier_quote(
        quote=quote_b,
        membership=env["member"],
        user=env["user"],
    )
    assert replay.pk == po.pk
    assert PurchaseOrder.objects.filter(pk=po.pk).count() == 1


@pytest.mark.django_db
def test_rfq_award_rejects_short_supply_and_expired_quote():
    env = _env("rfq-guards")
    rfq = _rfq(env)
    short = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_a"], user=env["user"],
    )
    _record(
        short, env,
        first_cost=Decimal("4.00"), second_cost=Decimal("8.00"),
        shipping=Decimal("0"),
        available=Decimal("2"),
    )
    with pytest.raises(ValidationError, match="available"):
        award_supplier_quote(
            quote=short, membership=env["member"], user=env["user"],
        )
    assert not PurchaseOrder.objects.filter(
        source_supplier_quote=short,
    ).exists()

    expired = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_b"], user=env["user"],
    )
    _record(
        expired, env,
        first_cost=Decimal("5.00"), second_cost=Decimal("9.00"),
        shipping=Decimal("0"),
        valid_until=timezone.localdate() - timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="expired"):
        award_supplier_quote(
            quote=expired, membership=env["member"], user=env["user"],
        )


@pytest.mark.django_db
def test_rfq_staff_ui_create_invite_record_compare_and_award():
    env = _env("rfq-ui")
    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()

    created = client.post(
        reverse("staff-purchasing-rfq-create"),
        {
            "outlet": str(env["outlet"].pk),
            "reference": "RFQ-UI-001",
            "needed_by": "",
            "notes": "UI comparison",
            "line_0_menu_item": str(env["item"].pk),
            "line_0_quantity": "10",
            "line_0_note": "",
            "line_1_menu_item": str(env["second_item"].pk),
            "line_1_quantity": "5",
            "line_1_note": "",
        },
    )
    assert created.status_code == 302
    rfq = env["tenant"].purchase_rfqs.get(reference="RFQ-UI-001")
    detail_url = reverse(
        "staff-purchasing-rfq-detail", kwargs={"rfq_id": rfq.pk},
    )

    invited = client.post(
        detail_url,
        {"action": "invite", "supplier": str(env["supplier_a"].pk)},
    )
    assert invited.status_code == 302
    quote = rfq.quotes.get(supplier=env["supplier_a"])
    lines = list(rfq.lines.order_by("menu_item__name"))
    item_map = {line.menu_item_id: line for line in lines}
    posted = {
        "action": "record_quote",
        "quote_id": str(quote.pk),
        "reference": "ALPHA-UI-Q",
        "shipping_cost": "5",
        "other_cost": "2",
        "lead_time_days": "3",
        "valid_until": "",
        "payment_terms": "Cash on delivery",
        "availability_note": "All available",
    }
    for item, cost in (
        (env["item"], "4.00"),
        (env["second_item"], "8.00"),
    ):
        line = item_map[item.pk]
        posted[f"quote_line_{line.pk}_unit_cost"] = cost
        posted[f"quote_line_{line.pk}_available"] = ""
        posted[f"quote_line_{line.pk}_promised"] = ""
        posted[f"quote_line_{line.pk}_note"] = ""

    recorded = client.post(detail_url, posted)
    assert recorded.status_code == 302
    quote.refresh_from_db()
    assert quote.status == SupplierQuoteStatus.SUBMITTED

    page = client.get(detail_url)
    assert page.status_code == 200
    assert b"Alpha Supplier" in page.content
    assert b"Lowest complete price" in page.content
    assert b"Award &amp; create PO" in page.content

    awarded = client.post(
        detail_url,
        {"action": "award", "quote_id": str(quote.pk)},
    )
    assert awarded.status_code == 302
    quote.refresh_from_db()
    assert quote.converted_purchase_order_id is not None
    assert awarded.url == reverse(
        "staff-purchasing-order-detail",
        kwargs={"po_id": quote.converted_purchase_order_id},
    )

@pytest.mark.django_db
def test_cancelled_rfq_locks_quotes_and_cannot_be_awarded():
    env = _env("rfq-cancel")
    rfq = _rfq(env)
    quote = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_a"], user=env["user"],
    )
    _record(
        quote, env,
        first_cost=Decimal("4.00"), second_cost=Decimal("8.00"),
        shipping=Decimal("10.00"),
    )
    cancelled = cancel_rfq(
        rfq=rfq,
        membership=env["member"],
        user=env["user"],
        reason="Requirement withdrawn by stock manager",
    )
    assert cancelled.status == PurchaseRfqStatus.CANCELLED
    quote.refresh_from_db()
    assert quote.status == SupplierQuoteStatus.REJECTED
    with pytest.raises(ValidationError, match="cancelled"):
        award_supplier_quote(
            quote=quote,
            membership=env["member"],
            user=env["user"],
        )
    assert not PurchaseOrder.objects.filter(
        source_supplier_quote=quote,
    ).exists()


@pytest.mark.django_db
def test_awarded_purchase_order_api_serializer_exposes_rfq_provenance():
    env = _env("rfq-api-source")
    rfq = _rfq(env)
    quote = invite_supplier_to_rfq(
        rfq=rfq, supplier=env["supplier_a"], user=env["user"],
    )
    _record(
        quote, env,
        first_cost=Decimal("4.00"), second_cost=Decimal("8.00"),
        shipping=Decimal("10.00"),
    )
    po = award_supplier_quote(
        quote=quote,
        membership=env["member"],
        user=env["user"],
    )
    po = PurchaseOrder.objects.select_related(
        "source_supplier_quote__rfq",
        "supplier",
        "outlet",
    ).get(pk=po.pk)
    data = PurchaseOrderSerializer(po).data
    assert data["sourcing"]["supplier_quote_id"] == str(quote.pk)
    assert data["sourcing"]["rfq_id"] == str(rfq.pk)
    assert data["sourcing"]["rfq_reference"] == rfq.reference
    assert data["sourcing"]["quoted_shipping_cost"] == "10.00"

    ordinary = PurchaseOrder.objects.create(
        tenant=env["tenant"],
        supplier=env["supplier_b"],
        outlet=env["outlet"],
        created_by=env["user"],
    )
    ordinary_data = PurchaseOrderSerializer(ordinary).data
    assert ordinary_data["sourcing"] is None

