from __future__ import annotations

from datetime import time
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from apps.accounts.models import MembershipRole
from apps.catalog.models import MenuItem, Promotion
from apps.pos.models import KdsLineStatus, Order, OrderLine, OrderStatus, Payment

from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import resolve_staff_outlet, staff_accessible_outlets
from .services import get_tenant_staff_modules

PRESETS = {"floor", "kitchen", "guest"}


class StaffServiceTvView(StaffTenantRequiredMixin, View):
    """Read-only, outlet-scoped hospitality display with configurable presentation."""

    # TV visibility is read-only; the outlet-scoped module check in get() keeps
    # this usable for legitimate bar and kitchen-only profiles.

    def get(self, request: HttpRequest) -> HttpResponse:
        outlets = staff_accessible_outlets(request.tenant_membership)
        selected_id = request.GET.get("outlet", "").strip()
        if selected_id:
            outlet = next((item for item in outlets if str(item.id) == selected_id), None)
        elif request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
            outlet = None
        else:
            outlet = resolve_staff_outlet(request, outlets)

        modules = get_tenant_staff_modules(request.tenant, outlet=outlet)
        profile_lines = set(getattr(getattr(request.tenant, "settings", None), "business_lines", []) or [])
        has_display_access = "pos" in modules or "kitchen" in modules
        if outlet is None or not has_display_access or not profile_lines.intersection(
            {"bar", "lounge", "restaurant", "cafeteria", "kitchen"}
        ):
            from django.contrib import messages
            from django.shortcuts import redirect

            messages.error(request, "Service TV is available only for an authorized bar, restaurant, or kitchen outlet.")
            return redirect("staff-dashboard")

        preset = request.GET.get("mode", "floor").strip().lower()
        if preset not in PRESETS:
            preset = "floor"
        try:
            goal = Decimal(request.GET.get("goal", "0").strip() or "0")
            if goal < 0 or goal > Decimal("999999999"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            goal = Decimal("0")
        now = timezone.localtime()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        promo_clock = timezone.localtime()
        daypart = (
            "Breakfast" if time(5) <= now.time() < time(11)
            else "Lunch" if time(11) <= now.time() < time(16)
            else "Dinner" if time(16) <= now.time() < time(22)
            else "Late night"
        )
        context = {
            "hide_staff_nav": True,
            "outlet": outlet,
            "outlets": outlets,
            "mode": preset,
            "refresh_seconds": 12,
            "goal": goal,
            "goal_progress": 0,
            "goal_sales": Decimal("0"),
            "orders_received": 0,
            "orders_prep": 0,
            "orders_ready": 0,
            "food_ready": 0,
            "bar_ready": 0,
            "ready_handoffs": 0,
            "orders": [],
            "leaderboard": [],
            "popular_items": [],
            "featured_items": [],
            "promotions": [],
            "daypart": daypart,
            "last_updated": now,
            "currency": "",
        }
        if outlet:
            context["currency"] = outlet.orders.order_by("-created_at").values_list("currency", flat=True).first() or ""
            base = Order.objects.filter(tenant=request.tenant, outlet=outlet, status=OrderStatus.OPEN)
            live_orders = list(
                base.select_related("created_by").prefetch_related("lines").order_by("created_at")[:60]
            )
            cards = []
            for order in live_orders:
                active_lines = [
                    line for line in order.lines.all()
                    if not line.is_voided and line.kds_status != KdsLineStatus.SERVED
                ]
                if not active_lines:
                    continue
                statuses = {line.kds_status for line in active_lines}
                lane = (
                    "ready" if statuses <= {KdsLineStatus.READY}
                    else "prep" if statuses & {KdsLineStatus.IN_PREP, KdsLineStatus.READY}
                    else "received"
                )
                ready_lines = [line for line in active_lines if line.kds_status == KdsLineStatus.READY]
                food_ready = sum(1 for line in ready_lines if self._station_group(line.kds_station) == "food")
                bar_ready = sum(1 for line in ready_lines if self._station_group(line.kds_station) == "bar")
                card_lines = active_lines if preset != "guest" else ready_lines
                age_seconds = max(0, int((now - timezone.localtime(order.created_at)).total_seconds()))
                age_display = "15m+" if age_seconds >= 900 else (
                    f"{age_seconds // 60}m {age_seconds % 60:02d}s" if age_seconds >= 60 else f"{age_seconds}s"
                )
                cards.append({
                    "order": order,
                    "lines": card_lines[:8],
                    "lane": lane,
                    "age_seconds": age_seconds,
                    "age_display": age_display,
                    "food_ready": food_ready,
                    "bar_ready": bar_ready,
                    "ready_handoff": bool(ready_lines),
                    "assigned_server": self._display_name(order.created_by),
                })
            if preset == "guest":
                cards = [card for card in cards if card["lane"] == "ready"]
            context["orders"] = cards
            context["orders_received"] = sum(card["lane"] == "received" for card in cards)
            context["orders_prep"] = sum(card["lane"] == "prep" for card in cards)
            context["orders_ready"] = sum(card["lane"] == "ready" for card in cards)
            context["food_ready"] = sum(card["food_ready"] for card in cards)
            context["bar_ready"] = sum(card["bar_ready"] for card in cards)
            context["ready_handoffs"] = sum(card["ready_handoff"] for card in cards)

            role_ids = request.tenant.memberships.filter(
                is_active=True,
                role__in=[MembershipRole.SERVER, MembershipRole.BARTENDER, MembershipRole.FRONT_DESK],
            ).values("user_id")
            ranking = (
                Order.objects.filter(
                    tenant=request.tenant, outlet=outlet, created_by_id__in=role_ids, created_at__gte=day_start,
                )
                .exclude(status=OrderStatus.CANCELLED)
                .values("created_by_id", "created_by__first_name", "created_by__last_name", "created_by__email")
                .annotate(order_count=Count("id"), sales_total=Sum("total"))
                .order_by("-sales_total", "-order_count", "created_by__first_name")[:5]
            )
            context["leaderboard"] = [
                {
                    "name": (f"{row['created_by__first_name']} {row['created_by__last_name']}".strip()
                             or row["created_by__email"].split("@")[0]),
                    "orders": row["order_count"],
                    "sales": row["sales_total"] or 0,
                }
                for row in ranking
            ]
            goal_sales = Payment.objects.filter(
                tenant=request.tenant,
                order__outlet=outlet,
                created_at__gte=day_start,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            context["goal_sales"] = goal_sales
            if goal:
                context["goal_progress"] = min(100, int(goal_sales * 100 / goal))

            popularity = (
                OrderLine.objects.filter(
                    order__tenant=request.tenant, order__outlet=outlet, order__created_at__gte=day_start,
                    order__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED], is_voided=False,
                    menu_item__isnull=False,
                )
                .values("label")
                .annotate(quantity_sold=Sum("quantity"))
                .order_by("-quantity_sold", "label")[:5]
            )
            context["popular_items"] = list(popularity)

            linked_items = MenuItem.objects.filter(tenant=request.tenant, is_active=True).filter(
                outlet_links__outlet=outlet,
            ).order_by("category__sort_order", "name").distinct()
            if not linked_items.exists():
                linked_items = MenuItem.objects.filter(tenant=request.tenant, is_active=True).exclude(
                    outlet_links__isnull=False,
                ).order_by("category__sort_order", "name")
            preferred_featured = linked_items.filter(is_featured=True)
            featured = list((preferred_featured if preferred_featured.exists() else linked_items).select_related("category")[:8])
            context["featured_items"] = [
                {
                    "name": item.name,
                    "description": item.description,
                    "price": item.unit_price_for_outlet(outlet.id),
                    "category": item.category.name,
                    "image_url": item.display_image_url,
                    "availability_note": item.availability_note,
                }
                for item in featured
            ]
            context["promotions"] = list(Promotion.objects.filter(
                tenant=request.tenant,
                is_active=True,
                starts_at__lte=promo_clock,
            ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=promo_clock)).filter(
                Q(outlets__isnull=True) | Q(outlets=outlet)
            ).distinct().order_by("name")[:6])
            if preset == "guest":
                # Do not serialize internal performance, goal, or popularity
                # figures into a guest-facing page (even in hidden markup/scripts).
                context["leaderboard"] = []
                context["goal_sales"] = Decimal("0")
                context["goal_progress"] = 0
                context["popular_items"] = []

        return render(request, "staff/service_tv.html", context)

    @staticmethod
    def _station_group(station: str) -> str:
        return "bar" if (station or "").strip().lower() in {"bar", "drinks", "beverage", "bartender"} else "food"

    @staticmethod
    def _display_name(user) -> str:
        if not user:
            return ""
        return user.get_full_name().strip() or user.email.split("@")[0]
