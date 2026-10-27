"""Single source of truth for retail discount and special-price precedence."""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from apps.pos.models import Order, OrderLine


@dataclass(frozen=True)
class PricingPrecedenceState:
    has_promotion: bool
    has_wholesale: bool
    has_price_book: bool
    has_manual_discount: bool

    @property
    def active_labels(self) -> tuple[str, ...]:
        labels = []
        if self.has_promotion:
            labels.append("Promotion")
        if self.has_wholesale:
            labels.append("Wholesale")
        if self.has_price_book:
            labels.append("Customer price book")
        if self.has_manual_discount:
            labels.append("Manual line discount")
        return tuple(labels)

    @property
    def promotion_block_reason(self) -> str:
        if self.has_wholesale:
            return "Wholesale pricing is active. Remove or restore wholesale-priced lines before applying an offer."
        if self.has_price_book:
            return "Customer price-book pricing is active. Offers do not stack with customer price-book rates."
        if self.has_manual_discount:
            return "A manual line discount is active. Offers do not stack with manual line discounts."
        return ""

    @property
    def summary(self) -> str:
        labels = self.active_labels
        if labels:
            return "Active pricing: " + ", ".join(labels) + "."
        return "Active pricing: regular shelf/menu prices."


def pricing_precedence_state(order: Order) -> PricingPrecedenceState:
    active = order.lines.filter(is_voided=False)
    flags = active.aggregate(
        wholesale_count=__count_filter(Q(pricing_source="wholesale")),
        price_book_count=__count_filter(Q(price_book_rule__isnull=False)),
        manual_count=__count_filter(
            Q(line_discount_amount__gt=0) | Q(line_discount_percent__isnull=False)
        ),
    )
    return PricingPrecedenceState(
        has_promotion=bool(order.applied_promotion_id),
        has_wholesale=bool(flags["wholesale_count"]),
        has_price_book=bool(flags["price_book_count"]),
        has_manual_discount=bool(flags["manual_count"]),
    )


def __count_filter(condition):
    from django.db.models import Count
    return Count("id", filter=condition)


def promotion_combination_block_reason(order: Order) -> str:
    return pricing_precedence_state(order).promotion_block_reason


def manual_discount_combination_block_reason(order: Order, line: OrderLine) -> str:
    if order.applied_promotion_id:
        return "Remove the order promotion before applying a manual line discount."
    if line.pricing_source == "wholesale":
        return "Wholesale-priced lines cannot receive a manual discount."
    if line.price_book_rule_id:
        return "Customer price-book lines cannot receive a manual discount."
    return ""


def wholesale_combination_block_reason(order: Order, line: OrderLine | None = None) -> str:
    if order.applied_promotion_id or order.discount_amount:
        return "Remove the order promotion or order discount before applying wholesale pricing."
    if line is not None and (
        line.line_discount_amount > 0 or line.line_discount_percent is not None
    ):
        return "Remove the manual line discount before applying wholesale pricing."
    return ""
