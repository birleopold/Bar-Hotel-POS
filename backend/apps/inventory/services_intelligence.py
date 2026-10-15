"""Read-only stock coverage indicators (Phase 07 groundwork).

Only actual posted sales are used. Forecasts are explicitly descriptive, not
purchase orders: no receipt history or supplier lead times are inferred.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import StockBalance, StockMovement, StockReason


def stock_coverage_snapshot(*, tenant, outlet, days=30):
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    if outlet.site.tenant_id != tenant.pk:
        raise ValueError("outlet must belong to tenant")
    cutoff = timezone.now() - timedelta(days=days)
    consumed = dict(
        StockMovement.objects.filter(
            tenant=tenant, outlet=outlet, reason=StockReason.SALE,
            created_at__gte=cutoff, quantity_change__lt=0,
        ).values("menu_item_id").annotate(used=Sum("quantity_change"))
        .values_list("menu_item_id", "used")
    )
    result = []
    for balance in StockBalance.objects.filter(
        tenant=tenant, outlet=outlet, menu_item__track_inventory=True,
    ).select_related("menu_item").order_by("menu_item__name"):
        used = -(consumed.get(balance.menu_item_id) or Decimal("0"))
        daily = used / Decimal(days)
        on_hand = balance.quantity
        days_remaining = (on_hand / daily) if daily > 0 else None
        level = balance.menu_item.reorder_level
        # Snapshot quantities are indicators, not batch-age or supplier-lead-time data.
        sell_through = None
        if used > 0 and on_hand + used > 0:
            sell_through = used / (on_hand + used)
        result.append({
            "item_id": balance.menu_item_id,
            "name": balance.menu_item.name,
            "on_hand": on_hand,
            "units_sold_window": used,
            "daily_velocity": daily,
            "days_remaining": days_remaining,
            "sell_through_proxy": sell_through,
            "below_reorder_level": level is not None and on_hand <= level,
            "no_sales_history": daily == 0,
        })
    return result
