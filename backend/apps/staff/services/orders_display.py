"""Read-model helpers for staff order lists and payment UI."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.catalog.models import Promotion
from apps.pos.models import Order


def order_payment_totals(order: Order) -> tuple[Decimal, Decimal]:
    paid = order.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    paid = paid.quantize(Decimal("0.01"))
    bal = max(Decimal("0"), (order.total - paid).quantize(Decimal("0.01")))
    return paid, bal


def order_refundable_remaining(order: Order) -> Decimal:
    """Net amount still refundable (payments minus refunds already recorded)."""
    paid = order.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    refunded = order.refunds.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    return max(Decimal("0"), (paid - refunded).quantize(Decimal("0.01")))


def promotions_selectable_for_order(order: Order):
    """Active promotions that may apply to this order's outlet (same rules as ``apply_promotion_to_order``)."""
    now = timezone.now()
    return (
        Promotion.objects.filter(
            tenant_id=order.tenant_id,
            is_active=True,
            starts_at__lte=now,
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .filter(Q(discount_percent__isnull=False) | Q(discount_amount__isnull=False))
        .annotate(_outlet_count=Count("outlets", distinct=True))
        .filter(Q(_outlet_count=0) | Q(outlets__id=order.outlet_id))
        .distinct()
        .order_by("name")
    )


def attach_order_payment_display(orders: list[Order]) -> None:
    for o in orders:
        p, b = order_payment_totals(o)
        o.display_paid = p
        o.display_balance = b
