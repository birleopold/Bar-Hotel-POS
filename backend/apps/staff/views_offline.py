from __future__ import annotations

from datetime import timedelta
import uuid
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Max
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from apps.accounts.models import MembershipRole
from apps.audit.models import ExceptionPolicy
from apps.audit.services import log_audit
from apps.pos.models import OfflineQueueStatus
from .services.modules import get_tenant_staff_modules
from django.utils import timezone
from django.views.generic import ListView

from apps.pos.models import OfflineQueuedOperation
from apps.pos.services.catalog_version import catalog_version_payload

from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import resolve_staff_outlet, staff_accessible_outlets


class StaffOfflineQueueListView(StaffTenantRequiredMixin, ListView):
    """Offline replay log with manager-reviewed conflicts, no unsafe re-posting."""

    staff_nav_capability = "offline_sync"
    template_name = "staff/pos/offline_queue.html"
    context_object_name = "entries"
    paginate_by = 50

    def _permitted_queue(self):
        qs = OfflineQueuedOperation.objects.filter(tenant=self.request.tenant).select_related(
            "outlet"
        )
        m = self.request.tenant_membership
        outlets = staff_accessible_outlets(m)
        outlet_ids = [
            outlet.pk for outlet in outlets
            if "pos" in get_tenant_staff_modules(self.request.tenant, outlet=outlet)
        ]
        if not outlet_ids:
            return OfflineQueuedOperation.objects.none()
        qs = qs.filter(outlet_id__in=outlet_ids)
        sel = resolve_staff_outlet(self.request, outlets)
        session_mode = self.request.session.get(STAFF_SESSION_OUTLET_KEY)
        if sel is not None and session_mode != STAFF_SESSION_OUTLET_ALL:
            qs = qs.filter(outlet_id=sel.id)
        return qs

    def get_queryset(self):
        qs = self._permitted_queue()
        st = (self.request.GET.get("status") or "").strip()
        if st in {"pending", "applied", "failed"}:
            qs = qs.filter(status=st)
        elif st == "review":
            qs = qs.filter(status="failed", reviewed_at__isnull=True)
        op = (self.request.GET.get("q") or "").strip()[:80]
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
        ctx["filter_q"] = (self.request.GET.get("q") or "").strip()[:80]
        qs = self._permitted_queue()
        stats = qs.aggregate(
            pending=Count("pk", filter=Q(status="pending")),
            applied=Count("pk", filter=Q(status="applied")),
            failed=Count("pk", filter=Q(status="failed")),
            last_applied=Max("updated_at", filter=Q(status="applied")),
        )
        ctx["offline_counts"] = stats
        policy = ExceptionPolicy.objects.filter(tenant=self.request.tenant).first()
        warning_hours = policy.offline_age_hours if policy else 24
        ctx["offline_warning_hours"] = warning_hours
        ctx["offline_stale"] = qs.filter(
            status="pending",
            created_at__lt=timezone.now() - timedelta(hours=warning_hours),
        ).count()
        ctx["offline_needs_review"] = qs.filter(
            status="failed", reviewed_at__isnull=True,
        ).count()
        ctx["offline_reviewed"] = qs.filter(
            status="failed", reviewed_at__isnull=False,
        ).count()
        ctx["can_review_offline"] = self.request.tenant_membership.role in {
            MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
        }
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


    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """Acknowledge a conflict; never mark it applied or replay it manually."""
        member = request.tenant_membership
        if not member.is_active or member.role not in {
            MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
        }:
            return HttpResponseForbidden("Only a manager can review offline conflicts.")
        if request.POST.get("action") != "review":
            messages.error(request, "Choose a supported queue review action.")
            return redirect("staff-offline-queue")
        note = (request.POST.get("note") or "").strip()
        if not note or len(note) > 500:
            messages.error(request, "Enter a review note of up to 500 characters.")
            return redirect("staff-offline-queue")
        try:
            operation_id = uuid.UUID(request.POST.get("operation_id") or "")
        except (TypeError, ValueError):
            messages.error(request, "Select a valid queued operation.")
            return redirect("staff-offline-queue")
        # Lock the same queue record that the sync service updates. A settled
        # item may not be reclassified as a conflict through a stale page.
        entry = self._permitted_queue().select_for_update().filter(
            pk=operation_id,
        ).first()
        if entry is None or entry.status != OfflineQueueStatus.FAILED:
            messages.error(request, "This queue item is unavailable or no longer failed.")
            return redirect("staff-offline-queue")
        entry.review_note = note
        entry.reviewed_at = timezone.now()
        entry.reviewed_by = request.user
        entry.save(update_fields=[
            "review_note", "reviewed_at", "reviewed_by", "updated_at",
        ])
        log_audit(
            tenant_id=request.tenant.pk, user_id=request.user.pk,
            action="pos.offline_conflict_reviewed",
            entity_type="offline_queue", entity_id=str(entry.pk),
            payload={
                "outlet_id": str(entry.outlet_id),
                "operation_type": entry.operation_type,
                "review_note": note,
            },
        )
        messages.success(request, "Conflict review saved. No payment or stock was changed.")
        return redirect("staff-offline-queue")
