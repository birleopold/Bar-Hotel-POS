"""Read-only supervised checkout display for an attached/second monitor.

Requires the same authenticated staff session as the source register; public
browser access and direct cash-drawer/terminal control are NOT provided.
"""
from decimal import Decimal

from django.db.models import Sum
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views import View

from apps.pos.models import Order
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


def customer_display_active_key(request, outlet_id):
    """Private, register-specific pointer shared only by same staff browser session.

    Never key solely by cashier ID: a cashier may use multiple tills or tabs.
    The paired screen must share this browser's authenticated session.
    """
    from .workstations import selected_workstation
    outlets = staff_accessible_outlets(request.tenant_membership)
    station = selected_workstation(request, outlets=outlets)
    register = str(station.pk) if station and station.outlet_id == outlet_id else "unselected"
    if not request.session.session_key:
        request.session.save()
    return "pos:customer-screen:v2:%s:%s:%s:%s" % (
        request.tenant.pk, outlet_id, register, request.session.session_key,
    )


def mark_customer_display_active(order, request):
    if (order.created_by_id == request.user.pk and order.status == "open"
            and not order.is_paid):
        cache.set(customer_display_active_key(request, order.outlet_id),
                  str(order.pk), timeout=60 * 60 * 12)


def clear_customer_display_active(order, request):
    key = customer_display_active_key(request, order.outlet_id)
    if cache.get(key) == str(order.pk):
        cache.delete(key)


@method_decorator(never_cache, name="dispatch")
class StaffCustomerDisplayView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"
    http_method_names = ["get", "head", "options"]

    def get(self, request, order_id):
        scoped = [o.pk for o in staff_accessible_outlets(request.tenant_membership)
                  if o.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}]
        order = Order.objects.filter(
            pk=order_id, tenant=request.tenant, outlet_id__in=scoped,
        ).select_related("outlet").first()
        if order is None:
            raise Http404
        # Only an explicitly active, open cashier basket is displayable.
        # A stale receipt URL cannot resurrect paid/held orders.
        active = None
        if order.created_by_id:
            active_id = cache.get(customer_display_active_key(request, order.outlet_id))
            if active_id:
                active = Order.objects.filter(
                    pk=active_id, tenant=request.tenant, outlet_id=order.outlet_id,
                    created_by_id=order.created_by_id, status="open", is_paid=False,
                ).select_related("outlet").first()
        if active is None:
            # Empty/idle customer monitor: do not expose an old order.
            response = render(request, "staff/pos/customer_display_idle.html", {
                "outlet": order.outlet,
            })
            response["Cache-Control"] = "no-store, private"
            return response
        order = active
        settled = order.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        remaining = max(Decimal("0.00"), order.total - settled)
        response = render(request, "staff/pos/customer_display.html", {
            "order": order,
            "display_lines": order.lines.filter(is_voided=False).order_by("sort_order", "created_at"),
            "display_paid": settled, "display_remaining": remaining,
        })
        response["Cache-Control"] = "no-store, private"
        return response
