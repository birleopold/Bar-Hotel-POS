"""Read-model helpers for staff order lists and payment UI."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.catalog.models import Promotion
from apps.catalog.promotion_rules import (
    promotion_matches_item,
    promotion_qualifying_quantity,
    promotion_redemption_block_reason,
    promotion_reward_matches_item,
    promotion_reward_quantity,
    promotion_target_q_for_items,
)
from apps.pos.models import Order
from apps.pos.services.pricing_policy import promotion_combination_block_reason


def order_payment_totals(order: Order) -> tuple[Decimal, Decimal]:
    gross_paid = order.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    refunded = order.refunds.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    paid = (gross_paid - refunded).quantize(Decimal("0.01"))
    bal = max(Decimal("0"), (order.total - paid).quantize(Decimal("0.01")))
    return paid, bal


def order_refundable_remaining(order: Order) -> Decimal:
    """Net amount still refundable (payments minus refunds already recorded)."""
    paid = order.payments.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    refunded = order.refunds.aggregate(x=Sum("amount"))["x"] or Decimal("0")
    return max(Decimal("0"), (paid - refunded).quantize(Decimal("0.01")))


def promotions_selectable_for_order(order: Order):
    """Active promotions whose schedule, outlet, basket state and target currently qualify."""
    if promotion_combination_block_reason(order):
        return Promotion.objects.none()

    items = [
        line.menu_item
        for line in order.lines.select_related("menu_item").filter(
            is_voided=False,
            menu_item__isnull=False,
        )
    ]
    target_q = promotion_target_q_for_items(items)
    now = timezone.now()
    base = (
        Promotion.objects.filter(
            tenant_id=order.tenant_id,
            is_active=True,
            starts_at__lte=now,
            coupon_code="",
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .filter(
            Q(offer_type__in=[
                Promotion.OfferType.BUY_X_GET_Y,
                Promotion.OfferType.X_FOR_FIXED_AMOUNT,
            ])
            | Q(discount_percent__isnull=False)
            | Q(discount_amount__isnull=False)
        )
        .filter(Q(min_order_subtotal__isnull=True) | Q(min_order_subtotal__lte=order.subtotal))
        .filter(target_q)
        .annotate(_outlet_count=Count("outlets", distinct=True))
        .filter(Q(_outlet_count=0) | Q(outlets__id=order.outlet_id))
        .distinct()
        .order_by("name")
    )
    eligible_ids = []
    for promotion in base:
        qualifying_quantity = promotion_qualifying_quantity(promotion, order)
        if (
            promotion.min_target_quantity is not None
            and qualifying_quantity < promotion.min_target_quantity
        ):
            continue
        if promotion.offer_type == Promotion.OfferType.BUY_X_GET_Y:
            buy_required = promotion.buy_quantity or 0
            get_required = promotion.get_quantity or 0
            reward_is_separate = bool(
                promotion.reward_menu_item_id
                or promotion.reward_product_family_id
                or promotion.reward_category_id
                or (promotion.reward_brand or "").strip()
            )
            if buy_required <= 0 or get_required <= 0:
                continue
            if qualifying_quantity != qualifying_quantity.to_integral_value():
                continue
            if reward_is_separate:
                active_items = [
                    line.menu_item
                    for line in order.lines.select_related("menu_item").filter(
                        is_voided=False,
                        menu_item__isnull=False,
                    )
                ]
                if any(
                    promotion_matches_item(promotion, item)
                    and promotion_reward_matches_item(promotion, item)
                    for item in active_items
                ):
                    continue
                reward_quantity = promotion_reward_quantity(promotion, order)
                if reward_quantity != reward_quantity.to_integral_value():
                    continue
                if qualifying_quantity < buy_required or reward_quantity < get_required:
                    continue
            elif qualifying_quantity < buy_required + get_required:
                continue
        elif promotion.offer_type == Promotion.OfferType.X_FOR_FIXED_AMOUNT:
            required = promotion.fixed_quantity or 0
            if required <= 0 or qualifying_quantity != qualifying_quantity.to_integral_value():
                continue
            if qualifying_quantity < required:
                continue
        if promotion_redemption_block_reason(promotion, order):
            continue
        eligible_ids.append(promotion.pk)
    return Promotion.objects.filter(pk__in=eligible_ids).order_by("name")


def attach_order_payment_display(orders: list[Order]) -> None:
    for o in orders:
        p, b = order_payment_totals(o)
        o.display_paid = p
        o.display_balance = b
