"""Delivery manager queue, using canonical POS order/payment/fulfillment services."""
from __future__ import annotations

import uuid

from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.models import Membership, User
from apps.pos.models import Order, OrderDelivery, OutletDeliverySettings
from apps.pos.services.deliveries import (
    MANAGER_ROLES, assign_delivery_driver, register_paid_order_delivery,
    set_outlet_delivery_enabled, transition_order_delivery,
)
from apps.pos.services.delivery_policy import ALLOWED_NEXT
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


class StaffDeliveriesView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"
    template_name = "staff/pos/deliveries.html"

    def _can_manage(self):
        m = self.request.tenant_membership
        return bool(m and m.is_active and m.role in MANAGER_ROLES)

    def _outlets(self):
        return [
            outlet for outlet in staff_accessible_outlets(self.request.tenant_membership)
            if outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and outlet.is_active
        ]

    def get(self, request):
        if not self._can_manage():
            return HttpResponseForbidden("Delivery management requires an authorized manager.")
        outlets = self._outlets()
        ids = [o.pk for o in outlets]
        settings = dict(OutletDeliverySettings.objects.filter(
            tenant=request.tenant, outlet_id__in=ids,
        ).values_list("outlet_id", "is_enabled"))
        deliveries = list(OrderDelivery.objects.filter(
            tenant=request.tenant, outlet_id__in=ids,
        ).select_related("order", "outlet", "assigned_driver").order_by("-created_at")[:75])
        enabled_ids = [oid for oid, enabled in settings.items() if enabled]
        pending_orders = list(Order.objects.filter(
            tenant=request.tenant, outlet_id__in=enabled_ids,
            status="closed", is_paid=True, delivery__isnull=True,
            retail_pickup__isnull=True,
        ).select_related("outlet", "customer").order_by("-created_at")[:60])
        for delivery in deliveries:
            delivery.allowed_next_stages = ALLOWED_NEXT.get(delivery.status, ())
        from apps.access.outlets import outlet_belongs_to_membership
        workers = [
            member for member in Membership.objects.filter(
                tenant=request.tenant, is_active=True,
            ).select_related("user").order_by("user__email")
            if any(outlet_belongs_to_membership(member, oid) for oid in ids)
        ]
        return render(request, self.template_name, {
            "delivery_outlets": [
                {"outlet":outlet, "enabled":settings.get(outlet.pk, False)}
                for outlet in outlets
            ],
            "delivery_records":deliveries, "delivery_workers":workers,
            "delivery_ready_orders":pending_orders,
        })

    def post(self, request):
        if not self._can_manage():
            return HttpResponseForbidden("Delivery management requires an authorized manager.")
        ids = [o.pk for o in self._outlets()]
        action = request.POST.get("action", "")
        try:
            if action == "configure":
                from apps.tenants.models import Outlet
                oid = _uuid_or_none(request.POST.get("outlet_id"))
                outlet = get_object_or_404(Outlet, pk=oid, site__tenant=request.tenant, pk__in=ids)
                enabled = request.POST.get("enabled")
                if enabled not in {"true", "false"}:
                    raise DRFValidationError({"enabled":"Choose enable or disable."})
                set_outlet_delivery_enabled(
                    outlet=outlet, enabled=enabled == "true", user=request.user,
                    membership=request.tenant_membership,
                )
                messages.success(request, "Delivery setting updated for this outlet.")
            elif action == "register":
                oid = _uuid_or_none(request.POST.get("order_id"))
                order = get_object_or_404(
                    Order, pk=oid, tenant=request.tenant, outlet_id__in=ids,
                )
                delivery, replay = register_paid_order_delivery(
                    order=order, user=request.user,
                    membership=request.tenant_membership,
                    destination_type=request.POST.get("destination_type", ""),
                    recipient_name=request.POST.get("recipient_name", ""),
                    contact_phone=request.POST.get("contact_phone", ""),
                    address=request.POST.get("address", ""),
                    room_reference=request.POST.get("room_reference", ""),
                    instructions=request.POST.get("instructions", ""),
                )
                messages.success(request, "Delivery already registered." if replay else
                                 "Paid sale registered for delivery.")
            elif action in {"assign", "transition"}:
                did = _uuid_or_none(request.POST.get("delivery_id"))
                delivery = get_object_or_404(
                    OrderDelivery, pk=did, tenant=request.tenant,
                    outlet_id__in=ids,
                )
                if action == "assign":
                    worker_id = _uuid_or_none(request.POST.get("driver_id"))
                    worker = get_object_or_404(User, pk=worker_id)
                    assign_delivery_driver(
                        delivery=delivery, driver=worker, user=request.user,
                        membership=request.tenant_membership,
                    )
                    messages.success(request, "Assigned delivery worker.")
                else:
                    transition_order_delivery(
                        delivery=delivery, target_status=request.POST.get("status", ""),
                        note=request.POST.get("note", ""),
                        user=request.user, membership=request.tenant_membership,
                    )
                    messages.success(request, "Fulfillment status updated.")
            else:
                raise DRFValidationError({"action":"Choose a valid delivery action."})
        except DRFValidationError as exc:
            messages.error(request, str(exc.detail))
        return redirect("staff-deliveries")


class StaffDeliveryPackingSlipView(StaffTenantRequiredMixin, View):
    """Printer-friendly fulfillment checklist, restricted to manager scope.

    This is NOT a fiscal receipt. Viewing/printing does not mutate fulfillment,
    settlement, customer identity, or stock.
    """
    staff_nav_capability = "orders"
    template_name = "staff/pos/delivery_packing_slip.html"

    def get(self, request, delivery_id):
        membership = request.tenant_membership
        if not membership.is_active or membership.role not in MANAGER_ROLES:
            return HttpResponseForbidden("Delivery packing slips are restricted to managers.")
        ids = [
            outlet.pk for outlet in staff_accessible_outlets(membership)
            if outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        ]
        delivery = get_object_or_404(
            OrderDelivery.objects.select_related(
                "order", "outlet", "assigned_driver",
            ), pk=delivery_id, tenant=request.tenant, outlet_id__in=ids,
        )
        order = delivery.order
        if order.tenant_id != request.tenant.pk or order.outlet_id != delivery.outlet_id:
            return HttpResponseForbidden("Delivery sale scope mismatch.")
        lines = list(order.lines.filter(is_voided=False).order_by("sort_order", "created_at"))
        response = render(request, self.template_name, {
            "delivery":delivery, "order":order, "packing_lines":lines,
        })
        response["Cache-Control"] = "no-store, private"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
