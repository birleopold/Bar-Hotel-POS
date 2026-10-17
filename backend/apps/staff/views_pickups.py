from django.views.generic import ListView
from apps.pos.models import RetailPickup
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


class StaffRetailPickupsView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "orders"
    template_name = "staff/pos/pickups.html"
    context_object_name = "pickups"
    paginate_by = 40

    def get_queryset(self):
        ids = [o.pk for o in staff_accessible_outlets(self.request.tenant_membership)
               if o.outlet_type in {OutletType.RETAIL, OutletType.SUPERMARKET}]
        qs = RetailPickup.objects.filter(tenant=self.request.tenant, order__outlet_id__in=ids)
        if self.request.GET.get("status", "awaiting") == "awaiting":
            qs = qs.filter(status=RetailPickup.Status.AWAITING)
        elif self.request.GET.get("status") == "collected":
            qs = qs.filter(status=RetailPickup.Status.COLLECTED)
        return qs.select_related("order", "order__outlet", "order__customer").order_by("expected_on", "-created_at")
