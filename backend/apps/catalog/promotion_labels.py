"""Safe physical markdown-label preparation for retail promotions."""
from __future__ import annotations

from decimal import Decimal

from apps.catalog.label_queue import queue_product_label, retail_label_outlets_for_item
from apps.catalog.models import MenuItem, ProductLabelQueueEntry, Promotion


def promotion_markdown_items(promotion: Promotion):
    """Return active concrete products covered by one promotion target."""
    qs = MenuItem.objects.filter(tenant_id=promotion.tenant_id, is_active=True)
    if promotion.menu_item_id:
        return qs.filter(pk=promotion.menu_item_id)
    if promotion.product_family_id:
        return qs.filter(product_family_id=promotion.product_family_id)
    if promotion.category_id:
        return qs.filter(category_id=promotion.category_id)
    brand = (promotion.brand or "").strip()
    if brand:
        return qs.filter(brand__iexact=brand)
    return qs.none()


def queue_markdown_labels_for_promotion(*, promotion: Promotion, user=None) -> int:
    """Queue only promotions that have an honest per-item shelf price.

    Basket/coupon/quantity-conditioned offers and multi-item fixed-amount
    discounts are deliberately excluded because a single shelf 'Now' price
    would misrepresent the checkout rule.
    """
    if (
        not promotion.is_active
        or promotion.offer_type != Promotion.OfferType.STANDARD
        or promotion.coupon_code
        or promotion.min_order_subtotal is not None
        or promotion.min_target_quantity is not None
    ):
        return 0
    if promotion.discount_percent is None and (
        promotion.discount_amount is None or not promotion.menu_item_id
    ):
        return 0

    limited_outlet_ids = set(promotion.outlets.values_list("pk", flat=True))
    count = 0
    for item in promotion_markdown_items(promotion).select_related("category"):
        for outlet in retail_label_outlets_for_item(item=item):
            if limited_outlet_ids and outlet.pk not in limited_outlet_ids:
                continue
            regular = item.unit_price_for_outlet(outlet.pk)
            if promotion.discount_percent is not None:
                markdown = (
                    regular
                    * (Decimal("100") - promotion.discount_percent)
                    / Decimal("100")
                ).quantize(Decimal("0.01"))
            else:
                markdown = max(
                    Decimal("0.00"),
                    regular - (promotion.discount_amount or Decimal("0.00")),
                ).quantize(Decimal("0.01"))
            if markdown >= regular:
                continue
            note = (
                f"{promotion.name}: {regular} → {markdown}; "
                f"starts {promotion.starts_at}"
            )
            if promotion.ends_at:
                note += f"; ends {promotion.ends_at}"
            queued = queue_product_label(
                tenant_id=promotion.tenant_id,
                outlet=outlet,
                menu_item=item,
                reason=ProductLabelQueueEntry.Reason.MARKDOWN,
                user=user,
                note=note,
                price_snapshot=markdown,
            )
            if queued is not None:
                count += 1
    return count
