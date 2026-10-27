"""Shared promotion target matching for checkout and staff selectors."""
from __future__ import annotations

from django.db.models import Q


def promotion_matches_item(promotion, item) -> bool:
    """Return whether one promotion target includes one concrete sellable item."""
    if promotion.menu_item_id:
        return promotion.menu_item_id == item.pk
    if promotion.product_family_id:
        return promotion.product_family_id == item.product_family_id
    if promotion.category_id:
        return promotion.category_id == item.category_id
    brand = (promotion.brand or "").strip()
    if brand:
        return bool(item.brand and item.brand.casefold() == brand.casefold())
    return True


def promotion_target_q_for_items(items) -> Q:
    """Build a queryset predicate for promotions matching at least one basket item."""
    item_ids = set()
    family_ids = set()
    category_ids = set()
    brands = set()
    for item in items:
        if item is None:
            continue
        item_ids.add(item.pk)
        if item.product_family_id:
            family_ids.add(item.product_family_id)
        if item.category_id:
            category_ids.add(item.category_id)
        if item.brand:
            brands.add(item.brand)

    q = Q(
        menu_item__isnull=True,
        product_family__isnull=True,
        category__isnull=True,
        brand="",
    )
    if item_ids:
        q |= Q(menu_item_id__in=item_ids)
    if family_ids:
        q |= Q(product_family_id__in=family_ids)
    if category_ids:
        q |= Q(category_id__in=category_ids)
    for brand in brands:
        q |= Q(brand__iexact=brand)
    return q


def promotion_qualifying_quantity(promotion, order):
    """Return the basket quantity eligible for one promotion target."""
    from decimal import Decimal

    quantity = Decimal("0")
    for line in order.lines.select_related("menu_item").filter(
        is_voided=False,
        menu_item__isnull=False,
    ):
        if promotion_matches_item(promotion, line.menu_item):
            quantity += line.quantity
    return quantity


def promotion_redemption_block_reason(promotion, order) -> str:
    """Return a user-facing reason when paid-order redemption limits are exhausted."""
    from apps.pos.models import Order

    paid = Order.objects.filter(
        tenant_id=promotion.tenant_id,
        applied_promotion_id=promotion.pk,
        is_paid=True,
    )
    if promotion.max_redemptions is not None and paid.count() >= promotion.max_redemptions:
        return "This offer has reached its total redemption limit."
    if (
        promotion.max_redemptions_per_customer is not None
        and order.customer_id is not None
        and paid.filter(customer_id=order.customer_id).count() >= promotion.max_redemptions_per_customer
    ):
        return "This customer has reached the redemption limit for this offer."
    return ""


def promotion_reward_matches_item(promotion, item) -> bool:
    """Return whether one concrete item belongs to the Buy X Get Y reward pool.

    When no separate reward target is configured, reward items come from the
    same target pool as the qualifying items for backwards-compatible BOGO.
    """
    if promotion.reward_menu_item_id:
        return promotion.reward_menu_item_id == item.pk
    if promotion.reward_product_family_id:
        return promotion.reward_product_family_id == item.product_family_id
    if promotion.reward_category_id:
        return promotion.reward_category_id == item.category_id
    reward_brand = (promotion.reward_brand or "").strip()
    if reward_brand:
        return bool(item.brand and item.brand.casefold() == reward_brand.casefold())
    return promotion_matches_item(promotion, item)


def promotion_reward_quantity(promotion, order):
    """Return whole/decimal basket quantity available in the configured reward pool."""
    from decimal import Decimal

    quantity = Decimal("0")
    for line in order.lines.select_related("menu_item").filter(
        is_voided=False,
        menu_item__isnull=False,
    ):
        if promotion_reward_matches_item(promotion, line.menu_item):
            quantity += line.quantity
    return quantity



def promotion_schedule_active(promotion, *, at=None) -> bool:
    """Evaluate date range plus recurring weekdays/times in tenant local time."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from django.utils import timezone
    from apps.tenants.models import TenantSettings

    moment = at or timezone.now()
    if not promotion.is_active:
        return False
    if promotion.starts_at > moment:
        return False
    if promotion.ends_at is not None and promotion.ends_at < moment:
        return False

    timezone_name = (
        TenantSettings.objects.filter(tenant_id=promotion.tenant_id)
        .values_list("default_timezone", flat=True)
        .first()
        or "UTC"
    )
    try:
        business_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        business_tz = ZoneInfo("UTC")
    local = timezone.localtime(moment, business_tz)

    weekdays = promotion.schedule_weekdays or []
    if weekdays and local.isoweekday() not in {int(value) for value in weekdays}:
        return False

    start_time = promotion.schedule_start_time
    end_time = promotion.schedule_end_time
    if start_time is not None and end_time is not None:
        current_time = local.timetz().replace(tzinfo=None)
        if not (start_time <= current_time < end_time):
            return False
    return True
