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


def customer_display_active_key(order):
    return "pos:customer-screen:%s:%s:%s" % (
        order.tenant_id, order.outlet_id, order.created_by_id,
    )


def mark_customer_display_active(order, actor):
    # A manager inspecting another cashier's sale must never redirect that
    # cashier's customer-facing screen.
    if order.created_by_id and order.created_by_id == actor.pk:
        cache.set(customer_display_active_key(order), str(order.pk), timeout=60 * 60 * 12)


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
        if order.created_by_id:
            active_id = cache.get(customer_display_active_key(order))
            if active_id and str(active_id) != str(order.pk):
                active = Order.objects.filter(
                    pk=active_id, tenant=request.tenant, outlet_id=order.outlet_id,
                    created_by_id=order.created_by_id,
                ).first()
                if active is not None:
                    # Stable URL: render the latest active sale directly.
                    # Redirecting between order URLs could make displays bounce.
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
