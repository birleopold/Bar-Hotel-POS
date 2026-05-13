from __future__ import annotations

from django.views.generic import ListView

from apps.audit.models import AuditEvent

from .mixins import StaffTenantRequiredMixin


class StaffAuditLogListView(StaffTenantRequiredMixin, ListView):
    """Tenant-scoped audit trail (read-only; same access idea as API ``AuditEventViewSet``)."""

    staff_nav_capability = "workspace"
    template_name = "staff/settings/audit_log.html"
    context_object_name = "events"
    paginate_by = 40

    def get_queryset(self):
        qs = AuditEvent.objects.filter(tenant=self.request.tenant).select_related("user").order_by(
            "-created_at"
        )
        action = (self.request.GET.get("action") or "").strip()
        if action:
            qs = qs.filter(action=action)
        et = (self.request.GET.get("entity_type") or "").strip()
        if et:
            qs = qs.filter(entity_type=et)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter_action"] = self.request.GET.get("action") or ""
        ctx["filter_entity_type"] = self.request.GET.get("entity_type") or ""
        return ctx
