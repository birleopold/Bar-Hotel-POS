"""
Operational snapshots for the staff dashboard (inspired by common IMS dashboards:
low stock at or below reorder; cached sales + top items using the same rules as Sales summary).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import F
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import StockBalance
from apps.pos.services import default_currency_for_tenant

from ..middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from ..sales_summary import build_sales_summary
from . import resolve_staff_outlet, staff_accessible_outlets


@dataclass(frozen=True, slots=True)
class DashboardLowStockRow:
    menu_item_name: str
    outlet_name: str
    quantity: str
    reorder_level: str


def dashboard_low_stock_snapshot(
    request: HttpRequest,
    *,
    membership,
    modules: frozenset[str],
    vis_inventory: bool,
    limit: int = 6,
) -> tuple[tuple[DashboardLowStockRow, ...], str]:
    """
    Items where on-hand <= reorder_level (tracked + reorder set).
    Respects outlet scope: single outlet vs all outlets session mode.
    """
    if "inventory" not in modules or not vis_inventory:
        return (), ""
    outlets = staff_accessible_outlets(membership)
    if not outlets:
        return (), ""

    if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
        ids = [o.id for o in outlets]
    else:
        cur = resolve_staff_outlet(request, outlets)
        ids = [cur.id] if cur else [o.id for o in outlets]

    qs = (
        StockBalance.objects.filter(tenant_id=membership.tenant_id, outlet_id__in=ids)
        .filter(
            menu_item__track_inventory=True,
            menu_item__reorder_level__isnull=False,
        )
        .filter(quantity__lte=F("menu_item__reorder_level"))
        .select_related("outlet", "menu_item")
        .order_by("quantity", "menu_item__name")[: int(limit)]
    )
    rows: list[DashboardLowStockRow] = []
    for bal in qs:
        rl = bal.menu_item.reorder_level
        rows.append(
            DashboardLowStockRow(
                menu_item_name=bal.menu_item.name,
                outlet_name=bal.outlet.name,
                quantity=str(bal.quantity.normalize()),
                reorder_level=str(rl.normalize()) if rl is not None else "—",
            )
        )
    url = reverse("staff-inventory-balances") + "?low_stock=1"
    return tuple(rows), url


_DASH_SALES_CACHE_SECONDS = 300


@dataclass(frozen=True, slots=True)
class DashboardTopItemRow:
    name: str
    quantity_sold: str
    revenue: str


@dataclass(frozen=True, slots=True)
class DashboardSalesSnapshot:
    """Aligned with ``StaffSalesSummaryView`` defaults: date_from = today − 7 days, date_to = today."""

    date_from: date
    date_to: date
    range_caption: str
    net_sales: str
    gross_sales: str
    refunds_total: str
    payments_count: int
    top_items: tuple[DashboardTopItemRow, ...]
    currency_code: str
    detail_url: str


def _fmt_money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def dashboard_sales_snapshot(
    request: HttpRequest,
    *,
    membership,
    modules: frozenset[str],
    vis_sales: bool,
) -> DashboardSalesSnapshot | None:
    """
    Cached net sales + top menu items for the same window and outlet scope as Sales summary.
    """
    if "pos" not in modules or not vis_sales:
        return None
    outlets = staff_accessible_outlets(membership)
    if not outlets:
        return None

    today = timezone.localdate()
    d0 = today - timedelta(days=7)
    d1 = today

    if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
        outlet_id = None
        scope_key = "all"
    else:
        cur = resolve_staff_outlet(request, outlets)
        outlet_id = cur.id if cur else None
        scope_key = str(outlet_id) if outlet_id else "none"

    cache_key = (
        f"staff_dash_sales_v1:{membership.tenant_id}:{scope_key}:{d0.isoformat()}:{d1.isoformat()}"
    )
    hit = cache.get(cache_key)
    if isinstance(hit, DashboardSalesSnapshot):
        return hit

    summary = build_sales_summary(membership.tenant_id, d0, d1, outlet_id)
    currency = default_currency_for_tenant(membership.tenant)
    net = summary.get("net_sales") or Decimal("0")
    gross = summary.get("gross_sales") or Decimal("0")
    ref = summary.get("refunds_total") or Decimal("0")
    pay_count = int(summary.get("payments_count") or 0)

    top_raw = list(summary.get("top_items") or [])[:5]
    top_rows: list[DashboardTopItemRow] = []
    for item in top_raw:
        qty = item.get("quantity_sold") or Decimal("0")
        rev = item.get("revenue") or Decimal("0")
        top_rows.append(
            DashboardTopItemRow(
                name=str(item.get("item_name") or "Item"),
                quantity_sold=str(qty.normalize()) if isinstance(qty, Decimal) else str(qty),
                revenue=_fmt_money(rev) if isinstance(rev, Decimal) else _fmt_money(Decimal(str(rev))),
            )
        )

    detail_qs = urlencode({"date_from": d0.isoformat(), "date_to": d1.isoformat()})
    detail_url = f"{reverse('staff-sales')}?{detail_qs}"

    range_caption = f"{d0.strftime('%d %b')} – {d1.strftime('%d %b %Y')}"

    snap = DashboardSalesSnapshot(
        date_from=d0,
        date_to=d1,
        range_caption=range_caption,
        net_sales=_fmt_money(net),
        gross_sales=_fmt_money(gross),
        refunds_total=_fmt_money(ref),
        payments_count=pay_count,
        top_items=tuple(top_rows),
        currency_code=currency,
        detail_url=detail_url,
    )
    cache.set(cache_key, snap, _DASH_SALES_CACHE_SECONDS)
    return snap
