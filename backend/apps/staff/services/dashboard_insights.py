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
from django.db.models import Count, F, Q
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.common.datetime_bounds import utc_day_range_inclusive
from apps.events.models import EventBooking, EventBookingStatus
from apps.inventory.models import StockBalance
from apps.lodging.models import MaintenanceStatus, Reservation, ReservationStatus, Room, RoomMaintenanceRequest, RoomStatus
from apps.pos.models import KdsLineStatus, Order, OrderLine, OrderStatus
from apps.pos.services import default_currency_for_tenant
from apps.purchasing.models import PurchaseOrder, PurchaseOrderStatus

from ..middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from ..sales_summary import build_sales_summary
from . import resolve_staff_outlet, resolve_staff_site, sites_visible_for_membership, staff_accessible_outlets


@dataclass(frozen=True, slots=True)
class DashboardLowStockRow:
    menu_item_name: str
    outlet_name: str
    quantity: str
    reorder_level: str


@dataclass(frozen=True, slots=True)
class DashboardArrivalRow:
    guest_name: str
    room_label: str
    status_label: str
    detail_url: str


@dataclass(frozen=True, slots=True)
class DashboardLodgingSnapshot:
    site_name: str
    arrivals: int
    in_house: int
    departures: int
    ready_rooms: int
    dirty_rooms: int
    out_of_order_rooms: int
    occupied_rooms: int
    total_rooms: int
    occupancy_percent: int
    open_maintenance: int
    arrival_rows: tuple[DashboardArrivalRow, ...]
    reservations_url: str
    tape_url: str
    housekeeping_url: str
    maintenance_url: str


@dataclass(frozen=True, slots=True)
class DashboardOperationsMetric:
    label: str
    value: int
    detail: str
    url: str
    tone: str = ""


def dashboard_operations_snapshot(
    request: HttpRequest,
    *,
    membership,
    modules: frozenset[str],
    vis,
) -> tuple[DashboardOperationsMetric, ...]:
    """Live cross-module workload, scoped to the selected outlet and branch."""
    outlets = staff_accessible_outlets(membership)
    if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
        outlet_ids = [outlet.id for outlet in outlets]
    else:
        current = resolve_staff_outlet(request, outlets)
        outlet_ids = [current.id] if current else []

    metrics: list[DashboardOperationsMetric] = []
    if "pos" in modules and vis.orders and outlet_ids:
        open_orders = Order.objects.filter(
            tenant_id=membership.tenant_id,
            outlet_id__in=outlet_ids,
            status=OrderStatus.OPEN,
            is_paid=False,
        ).count()
        metrics.append(
            DashboardOperationsMetric("Open orders", open_orders, "Awaiting settlement", reverse("staff-orders"), "sales")
        )

    if "kitchen" in modules and vis.kitchen and outlet_ids:
        active_lines = OrderLine.objects.filter(
            order__tenant_id=membership.tenant_id,
            order__outlet_id__in=outlet_ids,
            order__status=OrderStatus.OPEN,
            is_voided=False,
        )
        prep_count = active_lines.filter(kds_status__in=(KdsLineStatus.PENDING, KdsLineStatus.IN_PREP)).count()
        ready_count = active_lines.filter(kds_status=KdsLineStatus.READY).count()
        metrics.append(
            DashboardOperationsMetric("Prep queue", prep_count, f"{ready_count} ready to serve", reverse("staff-kds"), "prep")
        )

    if "purchasing" in modules and vis.purchasing and outlet_ids:
        open_purchase_orders = PurchaseOrder.objects.filter(
            tenant_id=membership.tenant_id,
            outlet_id__in=outlet_ids,
            status__in=(
                PurchaseOrderStatus.DRAFT,
                PurchaseOrderStatus.SENT,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
            ),
        ).count()
        metrics.append(
            DashboardOperationsMetric(
                "Purchase orders", open_purchase_orders, "Open or receiving", reverse("staff-purchasing-orders"), "stock"
            )
        )

    if "events" in modules and vis.events:
        sites = sites_visible_for_membership(membership)
        site = resolve_staff_site(request, sites)
        if site is not None:
            today = timezone.localdate()
            day_start, day_end = utc_day_range_inclusive(today, today)
            event_count = EventBooking.objects.filter(
                tenant_id=membership.tenant_id,
                space__site=site,
                status__in=(EventBookingStatus.TENTATIVE, EventBookingStatus.CONFIRMED),
                start_at__lte=day_end,
                end_at__gte=day_start,
            ).count()
            metrics.append(
                DashboardOperationsMetric("Events today", event_count, site.name, reverse("staff-events-calendar"), "events")
            )

    return tuple(metrics)


def dashboard_lodging_snapshot(
    request: HttpRequest,
    *,
    membership,
    visible: bool,
    limit: int = 5,
) -> DashboardLodgingSnapshot | None:
    if not visible:
        return None
    sites = sites_visible_for_membership(membership)
    site = resolve_staff_site(request, sites)
    if site is None:
        return None

    today = timezone.localdate()
    reservations = Reservation.objects.filter(tenant_id=membership.tenant_id, site=site)
    arrivals_qs = (
        reservations.filter(
            check_in=today,
            status__in=(ReservationStatus.HELD, ReservationStatus.CONFIRMED),
        )
        .select_related("room")
        .order_by("guest_name")
    )
    arrivals = arrivals_qs.count()
    in_house = reservations.filter(status=ReservationStatus.CHECKED_IN).count()
    departures = reservations.filter(
        check_out=today,
        status__in=(ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_IN),
    ).count()

    room_counts = Room.objects.filter(room_type__site=site, is_active=True).aggregate(
        total=Count("id"),
        ready=Count("id", filter=Q(status__in=(RoomStatus.CLEAN, RoomStatus.INSPECTED))),
        dirty=Count("id", filter=Q(status=RoomStatus.DIRTY)),
        out_of_order=Count("id", filter=Q(status=RoomStatus.OUT_OF_ORDER)),
    )
    total_rooms = int(room_counts["total"] or 0)
    occupied_rooms = (
        reservations.filter(status=ReservationStatus.CHECKED_IN, room_id__isnull=False)
        .values("room_id")
        .distinct()
        .count()
    )
    occupancy_percent = round((occupied_rooms / total_rooms) * 100) if total_rooms else 0
    open_maintenance = RoomMaintenanceRequest.objects.filter(
        tenant_id=membership.tenant_id,
        room__room_type__site=site,
    ).exclude(status=MaintenanceStatus.RESOLVED).count()
    arrival_rows = tuple(
        DashboardArrivalRow(
            guest_name=res.guest_name,
            room_label=res.room.name if res.room else "Unassigned",
            status_label=res.get_status_display(),
            detail_url=reverse("staff-lodging-reservation-detail", kwargs={"reservation_id": res.id}),
        )
        for res in arrivals_qs[: int(limit)]
    )
    return DashboardLodgingSnapshot(
        site_name=site.name,
        arrivals=arrivals,
        in_house=in_house,
        departures=departures,
        ready_rooms=int(room_counts["ready"] or 0),
        dirty_rooms=int(room_counts["dirty"] or 0),
        out_of_order_rooms=int(room_counts["out_of_order"] or 0),
        occupied_rooms=occupied_rooms,
        total_rooms=total_rooms,
        occupancy_percent=occupancy_percent,
        open_maintenance=open_maintenance,
        arrival_rows=arrival_rows,
        reservations_url=reverse("staff-lodging-reservations"),
        tape_url=reverse("staff-lodging-tape"),
        housekeeping_url=reverse("staff-lodging-housekeeping"),
        maintenance_url=reverse("staff-lodging-maintenance"),
    )


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
