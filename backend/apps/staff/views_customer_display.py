"""Read-only supervised checkout display for an attached/second monitor.

Requires the same authenticated staff session as the source register; public
browser access and direct cash-drawer/terminal control are NOT provided.
"""
from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views import View

from apps.pos.models import Order
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


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
        settled = order.payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
        remaining = max(Decimal("0.00"), order.total - settled)
        response = render(request, "staff/pos/customer_display.html", {
            "order": order,
            "display_lines": order.lines.filter(is_voided=False).order_by("sort_order", "created_at"),
            "display_paid": settled, "display_remaining": remaining,
        })
        response["Cache-Control"] = "no-store, private"
        return response
