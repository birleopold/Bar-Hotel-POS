from __future__ import annotations

from django.db.models import Q
from django.views.generic import ListView

from apps.pos.models import OfflineQueuedOperation
from apps.pos.services.catalog_version import catalog_version_payload

from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import resolve_staff_outlet, staff_accessible_outlets


class StaffOfflineQueueListView(StaffTenantRequiredMixin, ListView):
    """Device offline sync replay log (read-only)."""

    staff_nav_capability = "offline_sync"
    template_name = "staff/pos/offline_queue.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_queryset(self):
        qs = OfflineQueuedOperation.objects.filter(tenant=self.request.tenant).select_related(
            "outlet"
        )
        m = self.request.tenant_membership
        outlets = staff_accessible_outlets(m)
        outlet_ids = [outlet.pk for outlet in outlets]
        if not outlet_ids:
            return OfflineQueuedOperation.objects.none()
        qs = qs.filter(outlet_id__in=outlet_ids)
        sel = resolve_staff_outlet(self.request, outlets)
        session_mode = self.request.session.get(STAFF_SESSION_OUTLET_KEY)
        if sel is not None and session_mode != STAFF_SESSION_OUTLET_ALL:
            qs = qs.filter(outlet_id=sel.id)
        st = (self.request.GET.get("status") or "").strip()
        if st:
            qs = qs.filter(status=st)
        op = (self.request.GET.get("q") or "").strip()
        if op:
            qs = qs.filter(
                Q(client_mutation_id__icontains=op)
                | Q(operation_type__icontains=op)
                | Q(error_message__icontains=op)
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_status"] = (self.request.GET.get("status") or "").strip()
        ctx["filter_q"] = (self.request.GET.get("q") or "").strip()
        tenant_id = self.request.tenant.id
        catalog_by_outlet: dict[str, dict] = {}
        for o in staff_accessible_outlets(self.request.tenant_membership):
            snap = catalog_version_payload(tenant_id=tenant_id, outlet_id=o.id)
            catalog_by_outlet[str(o.id)] = {
                "catalog_version": snap["catalog_version"],
                "as_of": snap.get("as_of", ""),
            }
        ctx["catalog_by_outlet"] = catalog_by_outlet
        return ctx
