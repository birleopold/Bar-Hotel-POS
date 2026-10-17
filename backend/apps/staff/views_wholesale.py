"""Manager B2B quantity tiers: separate from anonymous supermarket shelf prices."""
from datetime import datetime
from decimal import Decimal
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_datetime
from django.views import View
from rest_framework.exceptions import ValidationError

from apps.pos.models import WholesalePriceRule
from apps.pos.services.wholesale import manager_allowed, save_wholesale_tier
from apps.pos.services.menu import menu_items_for_outlet_queryset
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import resolve_staff_outlet, staff_accessible_outlets


class StaffWholesalePricingView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"
    http_method_names = ["get", "post", "head", "options"]

    def _context(self, request):
        outlets = list(staff_accessible_outlets(request.tenant_membership))
        outlets = [o for o in outlets if o.outlet_type in {OutletType.RETAIL, OutletType.SUPERMARKET}]
        current = resolve_staff_outlet(request, outlets)
        authorized = current is not None and manager_allowed(
            request.tenant_membership, request.tenant.pk, current.pk,
        )
        items = menu_items_for_outlet_queryset(request.tenant.pk, current.pk).order_by("name")[:500] if authorized else []
        rules = WholesalePriceRule.objects.filter(
            tenant=request.tenant, outlet__in=outlets,
        ).select_related("outlet", "menu_item").order_by("outlet__name", "menu_item__name", "-minimum_quantity")[:200]
        return {"wholesale_outlet": current, "wholesale_outlets": outlets,
                "wholesale_can_edit": authorized, "wholesale_items": items,
                "wholesale_rules": rules}

    def get(self, request):
        return render(request, "staff/pos/wholesale_pricing.html", self._context(request))

    def post(self, request):
        ctx = self._context(request)
        outlet = ctx["wholesale_outlet"]
        if not ctx["wholesale_can_edit"]:
            return HttpResponseForbidden("Choose a retail section and sign in with manager rights.")
        try:
            save_wholesale_tier(
                tenant=request.tenant, outlet=outlet, membership=request.tenant_membership,
                user=request.user, item_id=request.POST.get("menu_item_id"),
                quantity=request.POST.get("minimum_quantity"),
                price=request.POST.get("unit_price"),
                start=parse_datetime(request.POST["starts_at"]) if request.POST.get("starts_at") else None,
                end=parse_datetime(request.POST["ends_at"]) if request.POST.get("ends_at") else None,
                active=request.POST.get("is_active") == "on",
            )
        except (ValidationError, ValueError, TypeError) as exc:
            messages.error(request, str(getattr(exc, "detail", exc)))
        else:
            messages.success(request, "Wholesale price rule saved. Only explicitly approved customer sales use it.")
        return redirect("staff-wholesale-pricing")
