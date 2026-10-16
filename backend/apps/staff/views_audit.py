"""Owner-readable audit timeline. Maintains the existing activity route."""
import csv

from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.views import View

from .mixins import StaffTenantRequiredMixin
from .services.audit_reader import (
    READER_ROLES, audit_view_row, safe_csv_value, visible_audit_events,
)


class StaffAuditLogListView(StaffTenantRequiredMixin, View):
    """Tenant and location-scoped audit; never display unredacted raw payload."""
    staff_nav_capability = "workspace"
    http_method_names = ["get", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        member = getattr(request, "tenant_membership", None)
        if member and (not member.is_active or member.role not in READER_ROLES):
            return HttpResponseForbidden("This activity log is available only to managers.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        events, filters = visible_audit_events(
            tenant=request.tenant, membership=request.tenant_membership,
            params=request.GET,
        )
        if request.GET.get("format") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="audit-records.csv"'
            writer = csv.writer(response)
            writer.writerow(["Time", "Actor", "Action", "Entity", "Record ID", "Redacted details"])
            for event in events[:1000].iterator(chunk_size=100):
                item = audit_view_row(event)
                writer.writerow([
                    safe_csv_value(item["time"].isoformat()),
                    safe_csv_value(item["actor"]),
                    safe_csv_value(item["action_code"]),
                    safe_csv_value(item["entity"]),
                    safe_csv_value(item["entity_id"]),
                    safe_csv_value(item["details"]),
                ])
        else:
            page = Paginator(events, 40).get_page(request.GET.get("page", "1"))
            response = render(request, "staff/settings/audit_log.html", {
                "filter_action": filters.get("action", ""),
                "filter_entity_type": filters.get("entity", ""),
                "filter_from": filters.get("from", ""),
                "filter_to": filters.get("to", ""),
                "page_obj": page,
                "audit_rows": [audit_view_row(event) for event in page.object_list],
            })
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        return response
