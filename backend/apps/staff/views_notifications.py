"""Staff notification inbox: stateful read/unread without cross-user leakage."""
import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.audit.models import StaffNotification
from .mixins import StaffTenantRequiredMixin
from .services.alerts import mark_alerts_read, refresh_staff_alerts


class StaffNotificationsStatusView(StaffTenantRequiredMixin, View):
    """Small private feed for badge/browser notification refresh."""
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        qs = StaffNotification.objects.filter(
            tenant=request.tenant,
            recipient=request.tenant_membership,
            active=True,
            read_at__isnull=True,
        ).order_by("-created_at")
        latest = qs.first()
        payload = {
            "unread_count": qs.count(),
            "latest": None,
        }
        if latest is not None:
            payload["latest"] = {
                "id": str(latest.pk),
                "title": latest.title,
                "body": latest.body,
                "url": latest.url,
                "source_type": latest.source_type,
                "created_at": latest.created_at.isoformat(),
            }
        response = JsonResponse(payload)
        response["Cache-Control"] = "private, no-store"
        return response


class StaffNotificationsView(StaffTenantRequiredMixin, View):
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request):
        qs = StaffNotification.objects.filter(
            tenant=request.tenant, recipient=request.tenant_membership,
            active=True,
        )
        unread_only = request.GET.get("unread") == "1"
        if unread_only:
            qs = qs.filter(read_at__isnull=True)
        page = Paginator(qs.order_by("-created_at"), 30).get_page(
            request.GET.get("page", "1"),
        )
        response = render(request, "staff/notifications/inbox.html", {
            "alerts": page.object_list,
            "page_obj": page,
            "unread_only": unread_only,
            "unread_count": StaffNotification.objects.filter(
                tenant=request.tenant, recipient=request.tenant_membership,
                active=True, read_at__isnull=True,
            ).count(),
        })
        response["Cache-Control"] = "private, no-store"
        return response

    def post(self, request):
        membership = request.tenant_membership
        if not membership or not membership.is_active:
            return HttpResponseForbidden("An active staff session is required.")
        action = (request.POST.get("action") or "").strip()
        if action == "refresh":
            created = refresh_staff_alerts(tenant=request.tenant, membership=membership)
            messages.success(request, f"Notifications refreshed. {created} new alerts.")
        elif action == "read_all":
            count = mark_alerts_read(
                tenant=request.tenant, membership=membership, all_visible=True,
            )
            messages.success(request, f"Marked {count} alerts as read.")
        elif action == "read":
            try:
                alert_id = uuid.UUID(request.POST.get("alert_id") or "")
            except (TypeError, ValueError):
                messages.error(request, "Choose a valid alert.")
            else:
                mark_alerts_read(
                    tenant=request.tenant, membership=membership, ids=[alert_id],
                )
                messages.success(request, "Marked as read.")
        else:
            messages.error(request, "Choose a supported notification action.")
        return redirect("staff-notifications")
