from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Membership
from apps.pos.models import (
    Order,
    OrderLine,
    OrderStatus,
    Payment,
    Refund,
    SupermarketLineReturn,
)
from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.staff.profitability import build_merchandise_profitability
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


def _sale(env, *, cost="60.00", cost_complete=True, reference="PROFIT-1"):
    settings_obj = env["tenant"].settings
    settings_obj.default_currency = "UGX"
    settings_obj.save(update_fields=["default_currency", "updated_at"])
    order = Order.objects.create(
        tenant=env["tenant"],
        outlet=env["outlet"],
        status=OrderStatus.CLOSED,
        subtotal=Decimal("100.00"),
        tax_total=Decimal("0.00"),
        discount_amount=Decimal("10.00"),
        total=Decimal("90.00"),
        is_paid=True,
        bill_reference=reference,
        created_by=env["user"],
    )
    line = OrderLine.objects.create(
        order=order,
        menu_item=env["item"],
        label=env["item"].name,
        quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
        cost_unit_snapshot=Decimal(cost) if cost is not None else None,
        cost_basis_complete_snapshot=cost_complete,
        merchandise_category_snapshot=env["item"].category.name,
    )
    payment = Payment.objects.create(
        tenant=env["tenant"],
        order=order,
        amount=Decimal("90.00"),
        method="cash",
        idempotency_key=f"pay-{reference}",
        recorded_by=env["user"],
    )
    return order, line, payment


def _report(env):
    today = timezone.localdate()
    return build_merchandise_profitability(
        tenant_id=env["tenant"].pk,
        date_from=today,
        date_to=today,
        allowed_outlet_ids=[env["outlet"].pk],
        currency="UGX",
    )


@pytest.mark.django_db
def test_profitability_uses_sale_time_cost_and_order_discount():
    env = _seed_tenant_bundle(
        name="Profit Complete",
        slug="profit-complete",
        user_email="profit-complete@test.local",
    )
    _sale(env)
    result = _report(env)
    assert result["sale_revenue"] == Decimal("90.00")
    assert result["covered_net_revenue"] == Decimal("90.00")
    assert result["uncovered_net_revenue"] == Decimal("0.00")
    assert result["known_net_cogs"] == Decimal("60.00")
    assert result["known_gross_profit"] == Decimal("30.00")
    assert result["known_margin_percent"] == Decimal("33.3")
    assert result["cost_coverage_percent"] == Decimal("100.0")
    assert len(result["categories"]) == 1
    category = result["categories"][0]
    assert category["category_name"] == env["item"].category.name
    assert category["net_revenue"] == Decimal("90.00")
    assert category["covered_net_revenue"] == Decimal("90.00")
    assert category["known_net_cogs"] == Decimal("60.00")
    assert category["known_gross_profit"] == Decimal("30.00")
    assert result["profitability_complete"] is True


@pytest.mark.django_db
def test_profitability_never_substitutes_current_cost_for_incomplete_sale():
    env = _seed_tenant_bundle(
        name="Profit Incomplete",
        slug="profit-incomplete",
        user_email="profit-incomplete@test.local",
    )
    _sale(env, cost=None, cost_complete=False)
    result = _report(env)
    assert result["sale_revenue"] == Decimal("90.00")
    assert result["covered_net_revenue"] == Decimal("0.00")
    assert result["uncovered_net_revenue"] == Decimal("90.00")
    assert result["known_net_cogs"] == Decimal("0.00")
    assert result["cost_coverage_percent"] == Decimal("0.0")
    assert result["incomplete_sale_lines"] == 1
    assert result["profitability_complete"] is False


@pytest.mark.django_db
def test_restocked_line_return_reverses_revenue_and_sale_time_cogs():
    env = _seed_tenant_bundle(
        name="Profit Return",
        slug="profit-return",
        user_email="profit-return@test.local",
    )
    order, line, payment = _sale(env, reference="PROFIT-RETURN")
    refund = Refund.objects.create(
        tenant=env["tenant"],
        order=order,
        payment=payment,
        amount=Decimal("45.00"),
        reason="Half quantity returned",
        idempotency_key="refund-profit-return",
        recorded_by=env["user"],
        restocked=True,
    )
    SupermarketLineReturn.objects.create(
        refund=refund,
        tenant=env["tenant"],
        order=order,
        order_line=line,
        quantity=Decimal("0.500"),
        reason="Half quantity returned",
        restocked=True,
        created_by=env["user"],
        idempotency_key="line-return-profit",
    )
    result = _report(env)
    assert result["return_revenue"] == Decimal("45.00")
    assert result["net_merchandise_revenue"] == Decimal("45.00")
    assert result["covered_return_revenue"] == Decimal("45.00")
    assert result["covered_net_revenue"] == Decimal("45.00")
    assert result["uncovered_net_revenue"] == Decimal("0.00")
    assert result["known_restock_cogs_reversal"] == Decimal("30.00")
    assert result["known_net_cogs"] == Decimal("30.00")
    assert result["known_gross_profit"] == Decimal("15.00")
    assert result["known_margin_percent"] == Decimal("33.3")
    assert result["unmapped_refund_count"] == 0
    assert result["profitability_complete"] is True


@pytest.mark.django_db
def test_unmapped_inventory_refund_marks_profitability_incomplete():
    env = _seed_tenant_bundle(
        name="Profit Refund Gap",
        slug="profit-refund-gap",
        user_email="profit-refund-gap@test.local",
    )
    order, _line, payment = _sale(env, reference="PROFIT-REFUND-GAP")
    Refund.objects.create(
        tenant=env["tenant"],
        order=order,
        payment=payment,
        amount=Decimal("20.00"),
        reason="General refund without item attribution",
        idempotency_key="refund-profit-gap",
        recorded_by=env["user"],
    )
    result = _report(env)
    assert result["unmapped_refund_count"] == 1
    assert result["unmapped_refund_amount"] == Decimal("20.00")
    assert result["profitability_complete"] is False


@pytest.mark.django_db
def test_management_profitability_respects_scope_and_csv_export():
    env = _seed_tenant_bundle(
        name="Profit Management",
        slug="profit-management",
        user_email="profit-management@test.local",
    )
    _sale(env, reference="PROFIT-MANAGEMENT")
    membership = Membership.objects.get(
        tenant=env["tenant"], user=env["user"],
    )
    membership.sites.add(env["site"])
    membership.outlets.add(env["outlet"])

    client = Client()
    assert client.login(username=env["user"].email, password="TestPass9!")
    session = client.session
    session[STAFF_SESSION_TENANT_KEY] = str(env["tenant"].pk)
    session.save()
    today = timezone.localdate().isoformat()

    response = client.get(
        reverse("staff-management"),
        {"view": "reports", "date_from": today, "date_to": today},
    )
    assert response.status_code == 200
    assert response.context["executive_profitability"]["known_gross_profit"] == Decimal("30.00")
    assert b"Merchandise profitability" in response.content
    assert b"100.0%" in response.content

    exported = client.get(
        reverse("staff-management"),
        {
            "view": "reports",
            "date_from": today,
            "date_to": today,
            "profit_export": "csv",
        },
    )
    assert exported.status_code == 200
    assert exported["Content-Type"].startswith("text/csv")
    body = exported.content.decode("utf-8")
    assert "Known gross profit,30.00,UGX" in body
    assert "Covered net revenue,90.00,UGX" in body
    assert "Revenue without trusted cost,0.00,UGX" in body
    assert "Category,Net revenue,Covered net revenue" in body
    assert env["item"].category.name in body
    assert env["item"].name in body

@pytest.mark.django_db
def test_unknown_cost_return_does_not_reduce_covered_profit_pool():
    env = _seed_tenant_bundle(
        name="Profit Unknown Return",
        slug="profit-unknown-return",
        user_email="profit-unknown-return@test.local",
    )
    _sale(env, reference="PROFIT-KNOWN")
    order, line, payment = _sale(
        env,
        cost=None,
        cost_complete=False,
        reference="PROFIT-UNKNOWN-RETURN",
    )
    refund = Refund.objects.create(
        tenant=env["tenant"],
        order=order,
        payment=payment,
        amount=Decimal("45.00"),
        reason="Unknown-cost return",
        idempotency_key="refund-profit-unknown-return",
        recorded_by=env["user"],
        restocked=True,
    )
    SupermarketLineReturn.objects.create(
        refund=refund,
        tenant=env["tenant"],
        order=order,
        order_line=line,
        quantity=Decimal("0.500"),
        reason="Unknown-cost return",
        restocked=True,
        created_by=env["user"],
        idempotency_key="line-return-profit-unknown",
    )

    result = _report(env)
    assert result["sale_revenue"] == Decimal("180.00")
    assert result["covered_sale_revenue"] == Decimal("90.00")
    assert result["return_revenue"] == Decimal("45.00")
    assert result["covered_return_revenue"] == Decimal("0.00")
    assert result["net_merchandise_revenue"] == Decimal("135.00")
    assert result["covered_net_revenue"] == Decimal("90.00")
    assert result["uncovered_net_revenue"] == Decimal("45.00")
    assert result["known_net_cogs"] == Decimal("60.00")
    assert result["known_gross_profit"] == Decimal("30.00")
    assert result["known_margin_percent"] == Decimal("33.3")
    assert result["incomplete_restock_return_lines"] == 1
    assert result["profitability_complete"] is False

@pytest.mark.django_db
def test_category_profitability_uses_sale_time_category_snapshot_after_product_move():
    env = _seed_tenant_bundle(
        name="Profit Category Snapshot",
        slug="profit-category-snapshot",
        user_email="profit-category-snapshot@test.local",
    )
    original_name = env["item"].category.name
    _sale(env, reference="PROFIT-CATEGORY-SNAPSHOT")

    category = env["item"].category
    category.name = "Moved after sale"
    category.save(update_fields=["name", "updated_at"])

    result = _report(env)
    names = [row["category_name"] for row in result["categories"]]
    assert original_name in names
    assert "Moved after sale" not in names
    row = next(row for row in result["categories"] if row["category_name"] == original_name)
    assert row["net_revenue"] == Decimal("90.00")
    assert row["known_net_cogs"] == Decimal("60.00")
    assert row["known_gross_profit"] == Decimal("30.00")

