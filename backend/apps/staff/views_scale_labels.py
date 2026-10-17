"""Opt-in variable-weight label mapping for retail and supermarket admins."""
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView
from rest_framework.exceptions import ValidationError

from apps.access.outlets import membership_outlet_ids
from apps.catalog.models import MenuItem, UnitOfMeasure
from apps.catalog.scale_labels import configure_scale_weight_label
from apps.pos.services.menu import menu_items_for_outlet_queryset
from apps.tenants.models import Outlet, OutletType
from .mixins import StaffTenantRequiredMixin
from .services.permissions import membership_can_manage_workspace_settings


class StaffScaleLabelView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/scale_labels.html"
    context_object_name = "scale_items"
    paginate_by = 40
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        outlets = Outlet.objects.filter(
            pk__in=membership_outlet_ids(request.tenant_membership),
            outlet_type__in=[OutletType.RETAIL, OutletType.SUPERMARKET],
        )
        if not outlets.exists():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        ids = set()
        for outlet_id in membership_outlet_ids(self.request.tenant_membership):
            if Outlet.objects.filter(pk=outlet_id, outlet_type__in=[OutletType.RETAIL, OutletType.SUPERMARKET]).exists():
                ids.update(menu_items_for_outlet_queryset(self.request.tenant.pk, outlet_id).values_list("pk", flat=True))
        qs = MenuItem.objects.filter(
            pk__in=ids, tenant=self.request.tenant, is_active=True,
            track_inventory=True, unit_of_measure=UnitOfMeasure.KG,
        ).select_related("supermarket_profile").order_by("name", "pk")
        q = (self.request.GET.get("q") or "").strip()[:80]
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_configure"] = membership_can_manage_workspace_settings(self.request.tenant_membership)
        ctx["scale_q"] = (self.request.GET.get("q") or "").strip()[:80]
        return ctx

    def post(self, request, *args, **kwargs):
        try:
            profile, replay = configure_scale_weight_label(
                tenant_id=request.tenant.pk,
                menu_item_id=request.POST.get("menu_item_id"),
                prefix=request.POST.get("scale_prefix", ""),
                item_code=request.POST.get("scale_item_code", ""),
                membership=request.tenant_membership, user=request.user,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            messages.error(request, "Scale label not saved: " + str(getattr(exc, "detail", exc)))
        else:
            messages.success(
                request, "Scale label mapping already saved." if replay
                else "Weight-label mapping saved. Confirm the physical scale prints this exact format before cashier use.",
            )
        q = (request.POST.get("return_q") or "").strip()[:80]
        return redirect(reverse("staff-inventory-scale-labels") + ("?" + urlencode({"q": q}) if q else ""))
