"""Fast aisle / shelf lookup for stock already present in the standard stock ledger."""
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q, Exists, OuterRef
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.inventory.models import StockBalance, StockShelfLocation
from apps.inventory.services_shelves import set_stock_shelf_location
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets, resolve_staff_outlet
from .services.permissions import membership_has_inventory_capability


class StaffShelfLocationView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/shelves.html"
    context_object_name = "balances"
    paginate_by = 40
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        if not membership_has_inventory_capability(request.tenant_membership, "view"):
            return HttpResponseForbidden("Your role cannot open the stock locator.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        current = resolve_staff_outlet(self.request, outlets)
        if self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
            outlet_ids = [outlet.pk for outlet in outlets]
        else:
            outlet_ids = [current.pk] if current else []
        qs = StockBalance.objects.filter(
            tenant=self.request.tenant, outlet_id__in=outlet_ids,
            menu_item__track_inventory=True,
        ).select_related("outlet", "menu_item").order_by("outlet__name", "menu_item__name", "pk")
        query = self.request.GET.get("q", "").strip()[:80]
        if query:
            shelf_matches = StockShelfLocation.objects.filter(
                tenant=self.request.tenant, outlet_id=OuterRef("outlet_id"),
                menu_item_id=OuterRef("menu_item_id"),
            ).filter(
                Q(aisle__icontains=query) | Q(shelf__icontains=query)
                | Q(bin_code__icontains=query),
            )
            qs = qs.annotate(matching_shelf=Exists(shelf_matches)).filter(
                Q(menu_item__name__icontains=query) | Q(menu_item__sku__icontains=query)
                | Q(menu_item__barcode__icontains=query) | Q(matching_shelf=True),
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        current = resolve_staff_outlet(self.request, outlets)
        ctx["current_outlet"] = current
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["locator_q"] = self.request.GET.get("q", "").strip()[:80]
        ctx["can_assign_shelves"] = membership_has_inventory_capability(self.request.tenant_membership, "adjust")
        rows = list(ctx["balances"])
        location_keys = [(row.outlet_id, row.menu_item_id) for row in rows]
        locations = StockShelfLocation.objects.filter(
            tenant=self.request.tenant, outlet_id__in=[x[0] for x in location_keys],
            menu_item_id__in=[x[1] for x in location_keys],
        )
        lookup = {(loc.outlet_id, loc.menu_item_id): loc for loc in locations}
        for row in rows:
            row.location = lookup.get((row.outlet_id, row.menu_item_id))
        ctx["balances"] = rows
        return ctx

    def post(self, request, *args, **kwargs):
        try:
            set_stock_shelf_location(
                tenant_id=request.tenant.pk,
                outlet_id=request.POST.get("outlet_id"),
                menu_item_id=request.POST.get("menu_item_id"),
                aisle=request.POST.get("aisle", ""),
                shelf=request.POST.get("shelf", ""),
                bin_code=request.POST.get("bin_code", ""),
                note=request.POST.get("note", ""),
                membership=request.tenant_membership, user=request.user,
            )
        except (DRFValidationError, ValueError, TypeError) as exc:
            messages.error(request, "Location not saved: " + str(getattr(exc, "detail", exc)))
        else:
            messages.success(request, "Shelf location saved. Stock quantities were not changed.")
        query = (request.POST.get("return_q") or "").strip()[:80]
        return redirect(reverse("staff-inventory-shelves") + ("?" + urlencode({"q": query}) if query else ""))
