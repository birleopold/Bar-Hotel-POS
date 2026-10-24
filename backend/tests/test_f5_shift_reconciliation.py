"""F5 manager shift evidence must remain linked to the correct till, without guesses."""
from decimal import Decimal

import pytest

from apps.pos.models import Order, Payment, PaymentMethod, PosShift, Refund
from apps.staff.services.shift_reconciliation import build_shift_reconciliation
from tests.test_phase1_isolation_and_idempotency import _seed_tenant_bundle


@pytest.mark.django_db
def test_shift_reconciliation_groups_actual_links_and_excludes_other_tills():
    data = _seed_tenant_bundle(name="F5 Reconciliation", slug="f5-reconciliation", user_email="f5-reconciliation@test.local")
    shift = PosShift.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], cash_attribution=True,
        opening_cash=Decimal("200"),
    )
    another = PosShift.objects.create(
        tenant=data["tenant"], outlet=data["outlet"], cash_attribution=False,
        opening_cash=Decimal("0"),
        status="closed",
    )
    order = Order.objects.create(tenant=data["tenant"], outlet=data["outlet"], currency="UGX")
    cash = Payment.objects.create(
        tenant=data["tenant"], order=order, shift=shift, amount=Decimal("4000"),
        method=PaymentMethod.CASH, idempotency_key="f5-cash",
    )
    Payment.objects.create(
        tenant=data["tenant"], order=order, shift=shift, amount=Decimal("3000"),
        method=PaymentMethod.CARD, idempotency_key="f5-card",
    )
    Payment.objects.create(
        tenant=data["tenant"], order=order, shift=another, amount=Decimal("5000"),
        method=PaymentMethod.CASH, idempotency_key="f5-other",
    )
    Payment.objects.create(
        tenant=data["tenant"], order=order, shift=None, amount=Decimal("6000"),
        method=PaymentMethod.CASH, idempotency_key="f5-unassigned",
    )
    Refund.objects.create(
        tenant=data["tenant"], order=order, payment=cash,
        shift=shift, amount=Decimal("500"), reason="Cashier return",
        idempotency_key="f5-refund",
    )
    report = build_shift_reconciliation(shift)
    assert report["is_exact_attribution"]
    assert report["payments_count"] == 2
    assert report["refunds_count"] == 1
    by_method = {(v["currency"], v["method"]): v for v in report["methods"]}
    currency = order.currency  # New orders inherit this tenant\'s configured currency.
    assert by_method[(currency, PaymentMethod.CASH)]["gross"] == Decimal("4000")
    assert by_method[(currency, PaymentMethod.CASH)]["refunded"] == Decimal("500")
    assert by_method[(currency, PaymentMethod.CASH)]["net"] == Decimal("3500")
    assert by_method[(currency, PaymentMethod.CARD)]["net"] == Decimal("3000")
    assert build_shift_reconciliation(another)["is_exact_attribution"] is False


@pytest.mark.django_db
def test_shift_reconciliation_never_imports_other_business_payments():
    one = _seed_tenant_bundle(name="F5 Owner", slug="f5-owner", user_email="f5-owner@test.local")
    other = _seed_tenant_bundle(name="F5 Other", slug="f5-other", user_email="f5-other@test.local")
    shift = PosShift.objects.create(tenant=one["tenant"], outlet=one["outlet"])
    order = Order.objects.create(tenant=other["tenant"], outlet=other["outlet"])
    Payment.objects.create(
        tenant=other["tenant"], order=order, amount=Decimal("2500"),
        method=PaymentMethod.CASH, idempotency_key="f5-other-tenant",
    )
    report = build_shift_reconciliation(shift)
    assert not report["methods"]
    assert report["payments_count"] == 0
