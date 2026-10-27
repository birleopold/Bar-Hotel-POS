from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from django import forms
from django.db import transaction
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from django.db.models import Count, Prefetch, Q

from apps.catalog.models import MenuItemModifierGroup, ModifierOption
from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.audit.models import AuditEvent
from apps.customers.models import Customer
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.catalog.models import MenuCategory, MenuItem, MenuItemOutlet, RetailProductGroup, ServiceOffering, ServiceOfferingOption
from apps.pos.models import KdsLineStatus, Order, OrderLine, OrderServiceMode, OrderStatus, PosShift, PosShiftStatus, ShiftHandover, Table, Workstation
from apps.pos.services import (
    adjust_open_order_line_quantity,
    assign_order_line_seat,
    add_line_to_open_order,
    add_retail_group_to_open_order,
    add_service_to_open_order,
    add_supermarket_line_by_code,
    apply_promotion_to_order,
    apply_supermarket_line_discount,
    cancel_open_unpaid_order,
    charge_order_to_folio,
    close_pos_shift,
    record_cash_drawer_movement,
    submit_shift_handover,
    verify_shift_handover,
    approve_shift_handover,
    accept_shift_handover,
    create_order_with_lines,
    default_currency_for_tenant,
    hold_open_order,
    resume_held_retail_order,
    menu_items_for_outlet_queryset,
    open_pos_shift,
    open_or_resume_table_order,
    transfer_table_order,
    process_supermarket_line_return,
    shift_cash_snapshot,
    record_order_payment,
    record_order_refund,
    refund_retail_line,
    resolve_order_create,
    resolve_table,
    set_open_order_folio,
    update_order_line_kds_status,
    void_open_order_line,
)
from apps.tenants.models import OutletType
from apps.tenants.models import TenantSettings
from apps.tenants.business_lines import normalize_business_lines
from apps.inventory.services import apply_manual_stock_change
from apps.lodging.models import Folio, FolioStatus

from .forms import (
    StaffOrderAddLineForm,
    StaffOrderAddServiceForm,
    StaffOrderAdjustLineQuantityForm,
    StaffOrderApplyPromotionForm,
    StaffOrderHoldForm,
    StaffOrderLineDiscountForm,
    StaffOrderLineReturnForm,
    StaffOrderPaymentForm,
    StaffOrderReadyHandoffForm,
    StaffOrderRefundForm,
    StaffRetailLineRefundForm,
    StaffOrderScanAddForm,
    StaffOrderSetFolioForm,
    StaffOrderVoidLineForm,
    StaffOrderVoidOrderForm,
    StaffCashDrawerMovementForm,
    StaffNoSaleDrawerForm,
    StaffPosShiftCloseForm,
    StaffHandoverCountForm,
    StaffPosShiftOpenForm,
    StaffTableForm,
)
from .services.customers import can_manage_customers, visible_customers
from .services.approvals import (
    SensitiveApprovalError,
    authorize_sensitive_action,
    sensitive_action_approvers,
)
from .services.permissions import membership_can_approve_sensitive_action
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .workstations import active_pairing, select_workstation, selected_workstation, settlement_workstation_id, require_staff_register_selection
from .report_csv import format_sales_summary_csv
from .sales_summary import build_sales_summary
from .services import (
    attach_order_payment_display,
    membership_can_acknowledge_ready_handoff,
    membership_can_approve_refunds,
    membership_can_modify_lodging,
    order_payment_totals,
    order_refundable_remaining,
    promotions_selectable_for_order,
    membership_can_manage_workspace_settings,
    resolve_staff_outlet,
    staff_accessible_outlets,
    staff_outlet_allowed_for_membership,
    get_tenant_staff_modules,
)


def _tenant_services_enabled(tenant) -> bool:
    try:
        lines = normalize_business_lines(tenant.settings.business_lines)
    except TenantSettings.DoesNotExist:
        return False
    return "services" in lines


def _tenant_item_catalog_enabled(tenant) -> bool:
    try:
        lines = set(normalize_business_lines(tenant.settings.business_lines))
    except TenantSettings.DoesNotExist:
        return False
    return bool(
        lines & {"bar", "lounge", "restaurant", "cafeteria", "kitchen", "retail", "supermarket"}
    )


def _tenant_lodging_enabled(tenant) -> bool:
    try:
        lines = normalize_business_lines(tenant.settings.business_lines)
    except TenantSettings.DoesNotExist:
        return False
    return "lodging" in lines


def _drf_detail_messages(detail, *, prefix: str = "") -> list[str]:
    """Flatten DRF ErrorDetail containers into human-readable cashier text."""
    if isinstance(detail, dict):
        result: list[str] = []
        for key, value in detail.items():
            label = f"{prefix}{key}: " if key not in {"non_field_errors", "detail"} else prefix
            result.extend(_drf_detail_messages(value, prefix=label))
        return result
    if isinstance(detail, (list, tuple)):
        result: list[str] = []
        for item in detail:
            result.extend(_drf_detail_messages(item, prefix=prefix))
        return result
    return [f"{prefix}{detail}"]


def _drf_has_code(value, wanted: str) -> bool:
    if isinstance(value, dict):
        return any(_drf_has_code(item, wanted) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_drf_has_code(item, wanted) for item in value)
    return value == wanted


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    for message in _drf_detail_messages(exc.detail):
        messages.error(request, message)


PRINT_DOCUMENT_TYPES = {"bill", "receipt"}
PRINT_PAPER_FORMATS = {"50mm", "80mm", "a4"}


def _normalize_print_document(value: str) -> str:
    doc = (value or "receipt").strip().lower()
    return doc if doc in PRINT_DOCUMENT_TYPES else "receipt"


def _normalize_print_format(value: str) -> str:
    paper = (value or "80mm").strip().lower()
    return paper if paper in PRINT_PAPER_FORMATS else "80mm"


def _tenant_hardware_flags(tenant) -> dict:
    try:
        settings_obj = tenant.settings
    except TenantSettings.DoesNotExist:
        return {
            "barcode_scanner_enabled": True,
            "cash_drawer_enabled": False,
            "receipt_printer_enabled": True,
        }
    return {
        "barcode_scanner_enabled": bool(settings_obj.hardware_barcode_scanner_enabled),
        "cash_drawer_enabled": bool(settings_obj.hardware_cash_drawer_enabled),
        "receipt_printer_enabled": bool(settings_obj.hardware_receipt_printer_enabled),
    }


class StaffSelectOutletView(StaffTenantRequiredMixin, View):
    staff_nav_capability = ("orders", "tables", "menu", "sales", "kitchen", "inventory", "purchasing")

    def post(self, request: HttpRequest) -> HttpResponse:
        m = request.tenant_membership
        if "pos" not in get_tenant_staff_modules(request.tenant):
            messages.error(request, "Point of sale is not enabled for this workspace.")
            return redirect("staff-dashboard")
        outlets = staff_accessible_outlets(m)
        oid = request.POST.get("outlet_id", "").strip()
        nxt = request.POST.get("next", "").strip() or reverse("staff-orders")
        if oid == "__all__":
            if m.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER):
                messages.error(request, "Your role must be assigned to a branch before viewing combined outlet lists.")
                return redirect(nxt)
            request.session[STAFF_SESSION_OUTLET_KEY] = STAFF_SESSION_OUTLET_ALL
            messages.success(request, "Showing all outlets for lists and reports.")
            return redirect(nxt)
        try:
            uid = uuid.UUID(oid)
        except ValueError:
            messages.error(request, "Invalid outlet.")
            return redirect(nxt)
        if not any(o.id == uid for o in outlets):
            messages.error(request, "You cannot switch to that outlet.")
            return redirect(nxt)
        request.session[STAFF_SESSION_OUTLET_KEY] = str(uid)
        messages.success(request, "Outlet updated.")
        return redirect(nxt)


class StaffOrdersListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "orders"
    template_name = "staff/orders_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def _orders_in_scope(self):
        if "pos" not in get_tenant_staff_modules(self.request.tenant):
            return Order.objects.none()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        allowed_ids = [o.id for o in outlets]
        if not allowed_ids:
            return Order.objects.none()
        qs = (
            Order.objects.filter(tenant=self.request.tenant, outlet_id__in=allowed_ids)
            .select_related("outlet", "table")
            .prefetch_related("payments")
            .order_by("-created_at")
        )
        outlet = resolve_staff_outlet(self.request, outlets)
        if outlet:
            qs = qs.filter(outlet=outlet)
        if self.request.GET.get("mine") == "1":
            qs = qs.filter(created_by=self.request.user)
        return qs

    def get_queryset(self):
        qs = self._orders_in_scope()
        st = self.request.GET.get("status")
        if st in ("open", "closed", "cancelled"):
            qs = qs.filter(status=st)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(bill_reference__icontains=q)
                | Q(table_label__icontains=q)
                | Q(outlet__name__icontains=q)
                | Q(table__label__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"] = self.request.GET.get("status") or ""
        ctx["mine_filter"] = self.request.GET.get("mine") == "1"
        ctx["returns_task"] = self.request.GET.get("task") == "returns" and ctx["status_filter"] == "closed"
        ctx["q_filter"] = (self.request.GET.get("q") or "").strip()
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["quick_create_key"] = uuid.uuid4()
        ctx["quick_hold_key"] = uuid.uuid4()
        ctx["quick_takeaway_key"] = uuid.uuid4()
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        orders = list(ctx.get("object_list", []))
        attach_order_payment_display(orders)
        # Service lanes stay live while the history below is filtered or searched.
        quick_qs = self._orders_in_scope()
        held_qs = quick_qs.filter(status=OrderStatus.OPEN, is_paid=False).exclude(table_label="")
        # A cashier can retrieve older parked baskets by receipt or hold note,
        # not only the twelve most recently touched sales.
        retail_types = {OutletType.SUPERMARKET, OutletType.RETAIL}
        allowed_retail_outlets = [
            outlet for outlet in ctx["outlets"] if outlet.outlet_type in retail_types
        ]
        retail_scope = (
            ctx["current_outlet"].outlet_type in retail_types
            if ctx["current_outlet"] is not None
            else bool(allowed_retail_outlets)
            and len(allowed_retail_outlets) == len(ctx["outlets"])
        )
        if ctx["q_filter"] and retail_scope:
            held_qs = held_qs.filter(
                Q(bill_reference__icontains=ctx["q_filter"])
                | Q(table_label__icontains=ctx["q_filter"])
            )
        held_tabs = list(held_qs.order_by("-updated_at")[:50])
        open_tabs = list(
            quick_qs.filter(status=OrderStatus.OPEN, is_paid=False, table_label="")
            .order_by("-updated_at")[:12]
        )
        recent_orders = list(
            quick_qs.exclude(status=OrderStatus.OPEN).order_by("-updated_at")[:12]
        )
        attach_order_payment_display(held_tabs)
        attach_order_payment_display(open_tabs)
        attach_order_payment_display(recent_orders)
        all_lane_orders = [*held_tabs, *open_tabs, *recent_orders]
        ready_ids: set[uuid.UUID] = set()
        if all_lane_orders:
            lane_ids = [o.id for o in all_lane_orders]
            ready_ids = set(
                OrderLine.objects.filter(
                    order_id__in=lane_ids,
                    is_voided=False,
                    kds_status=KdsLineStatus.READY,
                )
                .values_list("order_id", flat=True)
                .distinct()
            )
        for o in all_lane_orders:
            o.has_ready_handoff = o.id in ready_ids
            o.is_assigned_server = bool(o.created_by_id and o.created_by_id == self.request.user.id)
            o.ready_for_me = o.has_ready_handoff and membership_can_acknowledge_ready_handoff(
                self.request.tenant_membership,
                is_assigned_server=o.is_assigned_server,
            )
        ctx["held_tabs"] = held_tabs
        ctx["open_tabs"] = open_tabs
        ctx["recent_orders"] = recent_orders
        ctx["ready_handoff_count"] = sum(1 for o in all_lane_orders if getattr(o, "ready_for_me", False))
        outlet = ctx["current_outlet"]
        supermarket_lane = False
        shift_open = None
        retail_types = {OutletType.SUPERMARKET, OutletType.RETAIL}
        # Owners reviewing all supermarket registers must retain the retail UI.
        # Mixed hospitality/retail workspaces keep the neutral shared list until
        # a specific outlet is selected; never show bar tables as retail baskets.
        visible_outlets = list(ctx["outlets"])
        supermarket_lane = (
            outlet.outlet_type in retail_types
            if outlet is not None
            else bool(visible_outlets)
            and all(item.outlet_type in retail_types for item in visible_outlets)
        )
        if outlet is not None and supermarket_lane:
            shift_open = PosShift.objects.filter(
                tenant=self.request.tenant,
                outlet=outlet,
                status=PosShiftStatus.OPEN,
                workstation=selected_workstation(self.request, outlets=ctx["outlets"]),
            ).first()
        ctx["show_supermarket_lane"] = supermarket_lane
        ctx["supermarket_shift_open"] = shift_open
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get("fragment") == "lanes":
            return render(self.request, "staff/includes/orders_lanes.html", context)
        return super().render_to_response(context, **response_kwargs)


class StaffRetailPosEntryView(StaffTenantRequiredMixin, View):
    """Simple retail start: identify the till, open the shift, and start selling."""
    staff_nav_capability = "orders"
    http_method_names = ["get", "post", "head", "options"]

    def _scope(self, request):
        if "pos" not in get_tenant_staff_modules(request.tenant):
            return None, None
        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        if outlet is None or outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return outlets, None
        return outlets, outlet

    def _station_state(self, request, *, outlets, outlet):
        selected = selected_workstation(request, outlets=outlets)
        if selected is not None and selected.outlet_id == outlet.pk:
            return selected, [], False

        all_stations = list(
            Workstation.objects.filter(
                tenant=request.tenant,
                outlet=outlet,
                is_active=True,
            ).select_related("outlet").order_by("name", "code")
        )
        if not all_stations:
            # Small shops do not need a device record. Their shift is scoped to
            # the retail section and the cashier never sees workstation setup.
            return None, [], False

        pair = active_pairing(request, tenant_id=request.tenant.pk)
        usable = [
            station for station in all_stations
            if not station.requires_pairing
            or (pair is not None and pair.workstation_id == station.pk)
        ]
        if not usable:
            return None, [], True

        # If this worker already owns exactly one live register shift, resume
        # that till instead of asking which register they are on.
        worker_shifts = list(
            PosShift.objects.filter(
                tenant=request.tenant,
                outlet=outlet,
                status=PosShiftStatus.OPEN,
                opened_by=request.user,
                workstation__in=usable,
            ).select_related("workstation")[:2]
        )
        if len(worker_shifts) == 1 and worker_shifts[0].workstation is not None:
            return worker_shifts[0].workstation, [], False

        if len(usable) == 1:
            return usable[0], [], False
        return None, usable, False

    def _open_shift(self, request, *, outlet, station):
        filters = {
            "tenant": request.tenant,
            "outlet": outlet,
            "status": PosShiftStatus.OPEN,
            "workstation": station,
        }
        return PosShift.objects.filter(**filters).select_related("workstation", "opened_by").first()

    def _current_sale(self, request, *, outlet):
        return (
            Order.objects.filter(
                tenant=request.tenant,
                outlet=outlet,
                status=OrderStatus.OPEN,
                is_paid=False,
                created_by=request.user,
                table_label="",
                currency=default_currency_for_tenant(request.tenant),
            )
            .order_by("-updated_at")
            .first()
        )

    def _render_start(
        self,
        request,
        *,
        outlet,
        shift,
        station,
        register_choices,
        pairing_blocked=False,
        opening_form=None,
        status=200,
    ):
        return render(
            request,
            "staff/retail_pos_start.html",
            {
                "current_outlet": outlet,
                "current_shift": shift,
                "selected_station": station,
                "register_choices": register_choices,
                "pairing_blocked": pairing_blocked,
                "opening_form": opening_form or StaffPosShiftOpenForm(),
                "checkout_currency": default_currency_for_tenant(request.tenant),
            },
            status=status,
        )

    def get(self, request: HttpRequest) -> HttpResponse:
        outlets, outlet = self._scope(request)
        if outlet is None:
            messages.info(request, "Choose a retail section to start selling.")
            return redirect("staff-orders")

        station, register_choices, pairing_blocked = self._station_state(
            request,
            outlets=outlets,
            outlet=outlet,
        )
        if pairing_blocked:
            return self._render_start(
                request,
                outlet=outlet,
                shift=None,
                station=None,
                register_choices=[],
                pairing_blocked=True,
            )

        # A single known till should be remembered automatically. This is a
        # device convenience only; it never grants worker permissions.
        if station is not None and selected_workstation(request, outlets=outlets) is None:
            response = redirect("staff-retail-pos-entry")
            return select_workstation(response, station)

        shift = self._open_shift(request, outlet=outlet, station=station)
        if shift is None and station is None and register_choices:
            # The only daily choice shown to a cashier: which physical till.
            return self._render_start(
                request,
                outlet=outlet,
                shift=None,
                station=None,
                register_choices=register_choices,
            )

        if shift is not None:
            current_sale = self._current_sale(request, outlet=outlet)
            if current_sale:
                return redirect("staff-order-detail", order_id=current_sale.id)

        return self._render_start(
            request,
            outlet=outlet,
            shift=shift,
            station=station,
            register_choices=register_choices,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        outlets, outlet = self._scope(request)
        if outlet is None:
            messages.error(request, "Choose a retail section before starting a sale.")
            return redirect("staff-orders")
        if request.POST.get("action") != "start_selling":
            messages.error(request, "Choose Start selling to continue.")
            return redirect("staff-retail-pos-entry")

        station, register_choices, pairing_blocked = self._station_state(
            request,
            outlets=outlets,
            outlet=outlet,
        )
        posted_station = (request.POST.get("workstation_id") or "").strip()
        if posted_station:
            try:
                station_id = uuid.UUID(posted_station)
            except (TypeError, ValueError, AttributeError):
                station_id = None
            chosen = next((item for item in register_choices if item.pk == station_id), None)
            if chosen is None and station is not None and station.pk == station_id:
                chosen = station
            if chosen is None:
                messages.error(request, "Choose one of the available tills.")
                return self._render_start(
                    request,
                    outlet=outlet,
                    shift=None,
                    station=station,
                    register_choices=register_choices,
                    pairing_blocked=pairing_blocked,
                    status=400,
                )
            station = chosen

        if pairing_blocked:
            messages.error(request, "This checkout device needs one-time manager approval before it can be used.")
            return self._render_start(
                request,
                outlet=outlet,
                shift=None,
                station=None,
                register_choices=[],
                pairing_blocked=True,
                status=403,
            )
        if station is None and register_choices:
            messages.error(request, "Choose the till you are using.")
            return self._render_start(
                request,
                outlet=outlet,
                shift=None,
                station=None,
                register_choices=register_choices,
                status=400,
            )

        shift = self._open_shift(request, outlet=outlet, station=station)
        opening_form = StaffPosShiftOpenForm(request.POST)
        if shift is None and not opening_form.is_valid():
            return self._render_start(
                request,
                outlet=outlet,
                shift=None,
                station=station,
                register_choices=register_choices,
                opening_form=opening_form,
                status=400,
            )

        try:
            with transaction.atomic():
                if shift is None:
                    shift = open_pos_shift(
                        tenant_id=request.tenant.id,
                        outlet=outlet,
                        user=request.user,
                        opening_cash=opening_form.cleaned_data["opening_cash"],
                        note="",
                        workstation=station,
                    )

                # Serialize first-basket creation per tenant so a double tap on
                # Start selling does not create two empty active baskets.
                from apps.tenants.models import Tenant
                Tenant.objects.select_for_update().get(pk=request.tenant.pk)
                order = self._current_sale(request, outlet=outlet)
                if order is None:
                    order = create_order_with_lines(
                        tenant_id=request.tenant.id,
                        outlet=outlet,
                        created_by=request.user,
                        currency=default_currency_for_tenant(request.tenant),
                        table_label="",
                        lines=[],
                    )
        except DRFValidationError as exc:
            for message in _drf_detail_messages(exc.detail):
                messages.error(request, message)
            return self._render_start(
                request,
                outlet=outlet,
                shift=self._open_shift(request, outlet=outlet, station=station),
                station=station,
                register_choices=register_choices,
                opening_form=opening_form,
                status=409,
            )

        response = redirect("staff-order-detail", order_id=order.id)
        if station is not None:
            response = select_workstation(response, station)
        return response


class StaffOrderQuickCreateView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"

    def _quick_create(self, request: HttpRequest, *, mode: str, hold_label: str) -> HttpResponse:
        if "pos" not in get_tenant_staff_modules(request.tenant):
            messages.error(request, "Point of sale is not enabled for this workspace.")
            return redirect("staff-dashboard")
        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        if outlet is None:
            messages.error(request, "Select one outlet in the header to create an order.")
            return redirect("staff-orders")
        if not staff_outlet_allowed_for_membership(request.tenant_membership, outlet.id):
            messages.error(request, "You cannot create orders for this outlet.")
            return redirect("staff-orders")
        label = ""
        service_mode = ""
        if mode == "takeaway":
            if outlet.outlet_type not in {
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }:
                messages.error(request, "Takeaway orders are available only in hospitality sections.")
                return redirect("staff-orders")
            service_mode = OrderServiceMode.TAKEAWAY
        if mode == "hold":
            label = " ".join((hold_label or "").split())
            if len(label) > Order._meta.get_field("table_label").max_length:
                messages.error(request, "Hold note is too long. Use a shorter basket reference.")
                return redirect("staff-orders")
            if not label:
                label = f"HOLD {timezone.localtime().strftime('%H:%M')}"
        raw_key = (request.POST.get("quick_create_key") or "").strip()
        if raw_key:
            try:
                request_key = uuid.UUID(raw_key)
            except (ValueError, AttributeError):
                messages.error(request, "Invalid basket request. Refresh the sales page and try again.")
                return redirect("staff-orders")
        else:
            # Existing integrations without a token retain the legacy behavior.
            request_key = None

        with transaction.atomic():
            if request_key:
                # Serializing per tenant prevents two workers from creating
                # duplicate baskets with the same request key.
                from apps.tenants.models import Tenant
                Tenant.objects.select_for_update().get(pk=request.tenant.pk)
                existing = Order.objects.filter(
                    tenant=request.tenant, quick_create_key=request_key
                ).first()
                if existing:
                    if existing.created_by_id != request.user.pk or existing.outlet_id != outlet.pk:
                        messages.error(request, "This basket request belongs to a different register or worker.")
                        return redirect("staff-orders")
                    return redirect("staff-order-detail", order_id=existing.id)
            order = create_order_with_lines(
                tenant_id=request.tenant.id,
                outlet=outlet,
                created_by=request.user,
                currency=default_currency_for_tenant(request.tenant),
                table_label=label,
                service_mode=service_mode,
                lines=[],
            )
            if request_key:
                order.quick_create_key = request_key
                order.save(update_fields=["quick_create_key", "updated_at"])
        messages.success(request, "New order started.")
        return redirect("staff-order-detail", order_id=order.id)

    def get(self, request: HttpRequest) -> HttpResponse:
        # Browsing or prefetching a task link must never create an order.
        return redirect("staff-orders")

    def post(self, request: HttpRequest) -> HttpResponse:
        mode = (request.POST.get("mode") or "").strip()
        # Older staff clients submit "walkin" for the same unlabeled sale.
        # Preserve that supported alias while rejecting unknown operations.
        if mode == "walkin":
            mode = ""
        if mode not in {"", "hold", "takeaway"}:
            messages.error(request, "Invalid sale action. Start a new order, takeaway, or held tab.")
            return redirect("staff-orders")
        hold_label = (request.POST.get("hold_label") or "").strip()
        return self._quick_create(request, mode=mode, hold_label=hold_label)


class StaffPosShiftListView(StaffTenantRequiredMixin, TemplateView):
    staff_nav_capability = "orders"
    template_name = "staff/pos_shifts.html"

    def _resolve_outlet(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        return resolve_staff_outlet(self.request, outlets), outlets

    def _selected_for_outlet(self, request, outlet):
        selected = selected_workstation(request, outlets=staff_accessible_outlets(request.tenant_membership))
        return selected if selected and outlet and selected.outlet_id == outlet.id else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlet, outlets = self._resolve_outlet()
        ctx["outlets"] = outlets
        ctx["current_outlet"] = outlet
        ctx["selected_station"] = self._selected_for_outlet(self.request, outlet)
        ctx["open_form"] = StaffPosShiftOpenForm()
        ctx["close_form"] = StaffPosShiftCloseForm()
        payout_approvers = None
        if (
            outlet is not None
            and membership_can_approve_sensitive_action(
                self.request.tenant_membership, "withdrawal"
            )
        ):
            payout_approvers = sensitive_action_approvers(
                requester=self.request.tenant_membership,
                action="withdrawal",
                outlet_id=outlet.pk,
            )
        ctx["payout_approvers"] = payout_approvers or []
        ctx["movement_form"] = StaffCashDrawerMovementForm(
            initial={"idempotency_key": uuid.uuid4()},
            approvers=payout_approvers,
        )
        ctx["no_sale_form"] = StaffNoSaleDrawerForm(
            initial={"request_key": uuid.uuid4()},
        )
        ctx["handover_form"] = StaffHandoverCountForm()
        if outlet is None:
            ctx["open_shift"] = None
            ctx["recent_shifts"] = []
            return ctx
        station = ctx["selected_station"]
        ctx["pending_handover"] = ShiftHandover.objects.filter(
            tenant=self.request.tenant, shift__outlet=outlet, shift__workstation=station,
        ).exclude(status=ShiftHandover.Status.ACCEPTED).select_related(
            "shift", "shift__closed_by", "verified_by", "approved_by",
        ).first()
        pending = ctx["pending_handover"]
        manager = self.request.tenant_membership.role in {
            MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER, MembershipRole.OUTLET_MANAGER,
        }
        ctx["can_review_shift_history"] = manager
        operator = manager or self.request.tenant_membership.role in {MembershipRole.SERVER, MembershipRole.BARTENDER}
        ctx["can_verify_handover"] = bool(pending and operator and pending.status == ShiftHandover.Status.SUBMITTED and pending.shift.closed_by_id != self.request.user.pk)
        ctx["can_approve_handover"] = bool(pending and manager and pending.status == ShiftHandover.Status.VERIFIED and self.request.user.pk not in {pending.shift.closed_by_id, pending.verified_by_id})
        ctx["can_accept_handover"] = bool(pending and operator and pending.status == ShiftHandover.Status.APPROVED and self.request.user.pk not in {pending.shift.closed_by_id, pending.approved_by_id})
        ctx["open_shift"] = PosShift.objects.filter(
            tenant=self.request.tenant, outlet=outlet, status=PosShiftStatus.OPEN,
            workstation=station,
        ).first()
        ctx["other_open_shifts"] = PosShift.objects.filter(
            tenant=self.request.tenant, outlet=outlet, status=PosShiftStatus.OPEN,
        ).exclude(pk=ctx["open_shift"].pk if ctx["open_shift"] else None).select_related("workstation", "opened_by")
        ctx["cash_snapshot"] = shift_cash_snapshot(shift=ctx["open_shift"]) if ctx["open_shift"] else None
        ctx["cash_movements"] = ctx["open_shift"].cash_movements.select_related("recorded_by")[:30] if ctx["open_shift"] else []
        ctx["shift_currency"] = default_currency_for_tenant(self.request.tenant)
        ctx["recent_shifts"] = list(
            PosShift.objects.filter(tenant=self.request.tenant, outlet=outlet).select_related("workstation").order_by("-opened_at")[:20]
        )
        for shift in ctx["recent_shifts"]:
            shift.cash_variance = (
                shift.counted_cash - shift.expected_cash
                if shift.status == PosShiftStatus.CLOSED and shift.counted_cash is not None else None
            )
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        outlet, _ = self._resolve_outlet()
        if outlet is None:
            messages.error(request, "Select one outlet to manage shifts.")
            return redirect("staff-pos-shifts")
        try:
            selected_station = require_staff_register_selection(request, outlet=outlet)
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
            return redirect("staff-workstations")
        action = (request.POST.get("action") or "").strip()
        if action == "open_shift":
            form = StaffPosShiftOpenForm(request.POST)
            if not form.is_valid():
                context = self.get_context_data()
                context["open_form"] = form
                return self.render_to_response(context, status=400)
            try:
                open_pos_shift(
                    tenant_id=request.tenant.id,
                    outlet=outlet,
                    user=request.user,
                    opening_cash=form.cleaned_data["opening_cash"],
                    note=form.cleaned_data.get("note") or "",
                    workstation=selected_station,
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Shift opened.")
            return redirect("staff-pos-shifts")
        if action == "no_sale_drawer":
            form = StaffNoSaleDrawerForm(request.POST)
            if not form.is_valid():
                context = self.get_context_data()
                context["no_sale_form"] = form
                return self.render_to_response(context, status=400)
            shift = PosShift.objects.filter(
                tenant=request.tenant,
                outlet=outlet,
                workstation=selected_station,
                status=PosShiftStatus.OPEN,
            ).first()
            if shift is None:
                messages.error(request, "Open a shift on this register before recording a no-sale drawer opening.")
                return redirect("staff-pos-shifts")
            request_key = str(form.cleaned_data["request_key"])
            existing = AuditEvent.objects.filter(
                tenant=request.tenant,
                action="pos.drawer_no_sale_opened",
                entity_type="no_sale_drawer",
                entity_id=request_key,
            ).exists()
            if not existing:
                log_audit(
                    tenant_id=request.tenant.pk,
                    user_id=request.user.pk,
                    action="pos.drawer_no_sale_opened",
                    entity_type="no_sale_drawer",
                    entity_id=request_key,
                    payload={
                        "shift_id": str(shift.pk),
                        "outlet_id": str(outlet.pk),
                        "workstation_id": str(selected_station.pk),
                        "reason": form.cleaned_data["reason"],
                    },
                )
            messages.success(
                request,
                "No-sale drawer opening already recorded." if existing
                else "No-sale drawer opening recorded for manager review.",
            )
            return redirect("staff-pos-shifts")
        if action == "cash_movement":
            payout_approvers = (
                sensitive_action_approvers(
                    requester=request.tenant_membership,
                    action="withdrawal",
                    outlet_id=outlet.pk,
                )
                if membership_can_approve_sensitive_action(
                    request.tenant_membership, "withdrawal"
                )
                else None
            )
            form = StaffCashDrawerMovementForm(
                request.POST,
                approvers=payout_approvers,
            )
            if not form.is_valid():
                context = self.get_context_data()
                context["movement_form"] = form
                return self.render_to_response(context, status=400)
            shift = PosShift.objects.filter(
                pk=form.cleaned_data["shift_id"],
                tenant=request.tenant,
                outlet=outlet,
                workstation=selected_station,
            ).first()
            if shift is None:
                messages.error(request, "Shift not found for this register.")
                return redirect("staff-pos-shifts")
            try:
                if form.cleaned_data["direction"] == "payout":
                    with transaction.atomic():
                        locked_shift = PosShift.objects.select_for_update().get(
                            pk=shift.pk,
                            tenant=request.tenant,
                            outlet=outlet,
                            workstation=selected_station,
                        )
                        authorize_sensitive_action(
                            requester=request.tenant_membership,
                            approver_id=form.cleaned_data["approver_id"],
                            approver_pin=form.cleaned_data["approver_pin"],
                            action="withdrawal",
                            entity_type="pos_shift",
                            entity_id=str(locked_shift.pk),
                            request_key=str(form.cleaned_data["idempotency_key"]),
                            outlet_id=locked_shift.outlet_id,
                            intent_payload={
                                "direction": "payout",
                                "amount": str(form.cleaned_data["amount"]),
                                "reason": form.cleaned_data["reason"],
                                "workstation_id": str(selected_station.pk),
                            },
                        )
                        _, replay = record_cash_drawer_movement(
                            shift=locked_shift,
                            membership=request.tenant_membership,
                            user=request.user,
                            workstation_id=selected_station.pk,
                            direction=form.cleaned_data["direction"],
                            amount=form.cleaned_data["amount"],
                            reason=form.cleaned_data["reason"],
                            idempotency_key=str(form.cleaned_data["idempotency_key"]),
                        )
                else:
                    _, replay = record_cash_drawer_movement(
                        shift=shift,
                        membership=request.tenant_membership,
                        user=request.user,
                        workstation_id=selected_station.pk if selected_station else None,
                        direction=form.cleaned_data["direction"],
                        amount=form.cleaned_data["amount"],
                        reason=form.cleaned_data["reason"],
                        idempotency_key=str(form.cleaned_data["idempotency_key"]),
                    )
            except SensitiveApprovalError as exc:
                messages.error(request, str(exc))
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(
                    request,
                    "Movement already recorded." if replay else "Drawer movement recorded.",
                )
            return redirect("staff-pos-shifts")
        if action == "close_shift":
            form = StaffPosShiftCloseForm(request.POST)
            if not form.is_valid():
                context = self.get_context_data()
                context["close_form"] = form
                return self.render_to_response(context, status=400)
            shift = PosShift.objects.filter(
                id=form.cleaned_data["shift_id"],
                tenant=request.tenant,
                outlet=outlet,
                workstation=selected_station,
            ).first()
            if shift is None:
                messages.error(request, "Shift not found.")
                return redirect("staff-pos-shifts")
            try:
                submit_shift_handover(
                    shift=shift,
                    membership=request.tenant_membership,
                    user=request.user,
                    counted_cash=form.cleaned_data["counted_cash"],
                    explanation=form.cleaned_data.get("note") or "",
                    workstation_id=selected_station.pk if selected_station else None,
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Drawer submitted. Another worker must count it before manager approval.")
            return redirect("staff-pos-shifts")
        if action in {"verify_handover", "approve_handover", "accept_handover"}:
            try:
                handover_id = uuid.UUID(request.POST.get("handover_id", ""))
            except (ValueError, TypeError):
                messages.error(request, "Invalid handover reference.")
                return redirect("staff-pos-shifts")
            handover = ShiftHandover.objects.filter(
                pk=handover_id, tenant=request.tenant,
                shift__outlet=outlet, shift__workstation=selected_station,
            ).select_related("shift").first()
            if handover is None:
                messages.error(request, "Handover not found for this register.")
                return redirect("staff-pos-shifts")
            try:
                if action == "verify_handover":
                    form = StaffHandoverCountForm(request.POST)
                    if not form.is_valid():
                        context = self.get_context_data()
                        context["handover_form"] = form
                        return self.render_to_response(context, status=400)
                    verify_shift_handover(handover=handover, membership=request.tenant_membership,
                        user=request.user, counted_cash=form.cleaned_data["counted_cash"], note=form.cleaned_data["note"])
                elif action == "approve_handover":
                    approve_shift_handover(handover=handover, membership=request.tenant_membership,
                        user=request.user, note=request.POST.get("note", ""))
                else:
                    form = StaffPosShiftOpenForm(request.POST)
                    if not form.is_valid():
                        context = self.get_context_data()
                        context["open_form"] = form
                        return self.render_to_response(context, status=400)
                    accept_shift_handover(handover=handover, membership=request.tenant_membership,
                        user=request.user, opening_cash=form.cleaned_data["opening_cash"],
                        workstation_id=selected_station.pk if selected_station else None)
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Handover updated." if action != "accept_handover" else "Handover accepted. Your new shift is open.")
            return redirect("staff-pos-shifts")
        messages.error(request, "Unknown shift action.")
        return redirect("staff-pos-shifts")


class RetailQuickProductForm(forms.Form):
    name = forms.CharField(max_length=255, min_length=2, strip=True)
    unit_price = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    quantity = forms.IntegerField(min_value=1, initial=1, help_text="Quick-added products are sold in whole units.")
    barcode = forms.CharField(max_length=64, required=False, strip=True)


def _can_operate_retail_checkout(membership, order) -> bool:
    """Retail floor workers can serve assigned sales without admin privileges."""
    return bool(
        membership
        and membership.role == MembershipRole.SERVER
        and order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        and staff_outlet_allowed_for_membership(membership, order.outlet_id)
    )


def _can_operate_hospitality_order(membership, order) -> bool:
    """Assigned front-of-house workers may operate their own hospitality check."""
    return bool(
        membership
        and membership.is_active
        and membership.role in {MembershipRole.SERVER, MembershipRole.BARTENDER}
        and order.outlet.outlet_type in {
            OutletType.RESTAURANT,
            OutletType.BAR,
            OutletType.LOUNGE,
            OutletType.CAFETERIA,
        }
        and order.created_by_id == membership.user_id
        and staff_outlet_allowed_for_membership(membership, order.outlet_id)
    )


class StaffOrderDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "orders"
    template_name = "staff/order_detail.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        allowed_outlet_ids = [o.id for o in staff_accessible_outlets(self.request.tenant_membership)]
        if "pos" not in get_tenant_staff_modules(self.request.tenant):
            return Order.objects.none()
        return (
            Order.objects.filter(tenant=self.request.tenant, outlet_id__in=allowed_outlet_ids)
            .select_related("outlet", "table", "folio", "applied_promotion")
            .prefetch_related(
                "lines",
                "lines__menu_item",
                "payments",
                "refunds",
                "refunds__payment",
                "supermarket_returns__order_line",
                "supermarket_returns__refund__payment",
                "supermarket_returns__refund__shift__workstation",
            )
        )

    def get(self, request, *args, **kwargs):
        # Legacy empty USD baskets should not trap cashiers on a USD checkout
        # after their tenant changes its configured currency. This is strictly
        # a currency label correction: no monetary figures are converted.
        order = self.get_object()  # enforce tenant and outlet access first
        configured = default_currency_for_tenant(order.tenant)
        if (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and order.currency != configured
            and order.status == OrderStatus.OPEN
            and not order.is_paid
        ):
            with transaction.atomic():
                locked = Order.objects.select_for_update().get(pk=order.pk)
                if (
                    locked.status == OrderStatus.OPEN
                    and not locked.is_paid
                    and locked.currency != configured
                    and locked.subtotal == Decimal("0")
                    and locked.tax_total == Decimal("0")
                    and locked.total == Decimal("0")
                    and locked.discount_amount == Decimal("0")
                    and not locked.lines.exists()
                    and not locked.payments.exists()
                    and not locked.refunds.exists()
                ):
                    Order.objects.filter(pk=locked.pk).update(currency=configured)
                    return redirect("staff-order-detail", order_id=locked.pk)
        self.object = order
        if (order.status == OrderStatus.OPEN
                and order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}):
            from .views_customer_display import mark_customer_display_active
            mark_customer_display_active(order, request)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_template_names(self):
        order = self.object if getattr(self, "object", None) is not None else self.get_object()
        if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return ["staff/order_detail_supermarket.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order: Order = ctx["order"]
        hardware = _tenant_hardware_flags(order.tenant)
        ctx["hardware"] = hardware
        ctx["payment_request_key"] = uuid.uuid4()
        ctx["refund_request_key"] = uuid.uuid4()
        ctx["retail_refund_request_key"] = uuid.uuid4()
        ctx["line_return_request_key"] = uuid.uuid4()
        ctx["quick_product_request_key"] = uuid.uuid4()
        ctx["next_sale_request_key"] = uuid.uuid4()
        from apps.customers.models import LoyaltyLedgerEntry
        from apps.customers.loyalty import eligible_spend_for_order
        from apps.tenants.models import TenantSettings
        from decimal import ROUND_FLOOR
        policy = TenantSettings.objects.filter(tenant_id=order.tenant_id).only(
            "loyalty_enabled", "loyalty_spend_per_point", "default_currency",
        ).first()
        ctx["configured_currency"] = default_currency_for_tenant(order.tenant)
        ctx["currency_differs_from_settings"] = order.currency != ctx["configured_currency"]
        ctx["active_basket_line_count"] = order.lines.filter(is_voided=False).count()
        ctx["loyalty_policy_active"] = bool(
            policy and policy.loyalty_enabled
            and order.currency == policy.default_currency
        )
        ctx["loyalty_award"] = LoyaltyLedgerEntry.objects.filter(
            tenant_id=order.tenant_id, source_type="sale",
            source_key=str(order.pk),
        ).first()
        ctx["loyalty_estimate"] = None
        if (ctx["loyalty_policy_active"] and order.customer_id
                and not order.is_paid and policy.loyalty_spend_per_point > 0):
            ctx["loyalty_estimate"] = min(1000000, int((
                eligible_spend_for_order(order) / policy.loyalty_spend_per_point
            ).to_integral_value(rounding=ROUND_FLOOR)))
        ctx["can_view_customer_profile"] = can_manage_customers(self.request.tenant_membership)
        ctx["customer_options"] = visible_customers(self.request.tenant_membership, self.request.user).filter(
            Q(orders__outlet_id=order.outlet_id) | Q(created_by=self.request.user) | Q(pk=order.customer_id)
        ).distinct().order_by("name")[:100]
        p, b = order_payment_totals(order)
        ctx["amount_paid"] = p
        ctx["balance_due"] = b
        can_pay = (
            (
                membership_can_modify_lodging(self.request.tenant_membership)
                or _can_operate_retail_checkout(self.request.tenant_membership, order)
                or _can_operate_hospitality_order(self.request.tenant_membership, order)
            )
            and staff_outlet_allowed_for_membership(self.request.tenant_membership, order.outlet_id)
            and order.status == OrderStatus.OPEN
            and not order.is_paid
            and b > Decimal("0")
        )
        retail_held = (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and order.status == OrderStatus.OPEN and bool(order.table_label)
        )
        ctx["retail_held"] = retail_held
        if retail_held:
            can_pay = False
        ctx["can_record_payment"] = can_pay
        ctx["payment_form"] = StaffOrderPaymentForm(initial={"amount": b}) if can_pay else None
        ctx["settlement_station"] = selected_workstation(self.request, outlets=staff_accessible_outlets(self.request.tenant_membership))
        m = self.request.tenant_membership
        can_modify_open = (
            (
                membership_can_modify_lodging(m)
                or _can_operate_retail_checkout(m, order)
                or _can_operate_hospitality_order(m, order)
            )
            and staff_outlet_allowed_for_membership(m, order.outlet_id)
            and order.status == OrderStatus.OPEN
            and not order.is_paid
        )
        if retail_held:
            can_modify_open = False
        ctx["can_modify_open_order"] = can_modify_open
        ctx["serialized_sale_lines"] = []
        if (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and order.status == OrderStatus.OPEN
            and not order.is_paid
        ):
            from apps.inventory.models import SerializedUnitStatus
            for serial_line in order.lines.filter(
                is_voided=False,
                menu_item__serial_tracking=True,
            ).select_related("menu_item").order_by("sort_order", "created_at"):
                units = list(
                    serial_line.reserved_serial_units.filter(
                        tenant_id=order.tenant_id,
                        status=SerializedUnitStatus.RESERVED,
                    ).order_by("serial_number")
                )
                serial_line.serial_reserved_units = units
                serial_line.serial_required_count = int(serial_line.quantity)
                serial_line.serial_missing_count = max(0, int(serial_line.quantity) - len(units))
                ctx["serialized_sale_lines"].append(serial_line)

        # Folio attach/clear (only for open, unpaid orders).
        ctx["can_set_folio"] = can_modify_open and _tenant_lodging_enabled(order.tenant)
        ctx["can_charge_to_folio"] = can_modify_open and order.folio_id is not None and b > Decimal("0")
        ctx["folio_form"] = None
        ctx["folio_choices"] = []
        if ctx["can_set_folio"]:
            folio_qs = Folio.objects.filter(
                tenant_id=order.tenant_id,
                site_id=order.outlet.site_id,
                status=FolioStatus.OPEN,
            ).order_by("-created_at")[:50]
            ctx["folio_form"] = StaffOrderSetFolioForm(
                folio_queryset=folio_qs,
                initial_folio_id=order.folio_id,
            )
        assigned_server = bool(order.created_by_id and order.created_by_id == self.request.user.id)
        hospitality_handoff_after_payment = (
            order.outlet.outlet_type in {
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
            and order.status == OrderStatus.CLOSED
            and order.is_paid
        )
        can_ack_handoff = (
            staff_outlet_allowed_for_membership(m, order.outlet_id)
            and (
                (order.status == OrderStatus.OPEN and not order.is_paid)
                or hospitality_handoff_after_payment
            )
            and membership_can_acknowledge_ready_handoff(
                m,
                is_assigned_server=assigned_server,
            )
        )
        ready_line_ids = {
            str(line.id)
            for line in order.lines.all()
            if not line.is_voided and line.kds_status == KdsLineStatus.READY
        }
        ctx["can_ack_ready_handoff"] = can_ack_handoff
        ctx["ready_line_ids"] = ready_line_ids
        ctx["ready_handoff_count"] = len(ready_line_ids)
        ctx["is_assigned_server"] = assigned_server
        ctx["can_void_lines"] = can_modify_open
        services_enabled = _tenant_services_enabled(order.tenant)
        item_catalog_enabled = _tenant_item_catalog_enabled(order.tenant)
        ctx["add_line_form"] = (
            StaffOrderAddLineForm(tenant_id=order.tenant_id, outlet_id=order.outlet_id)
            if can_modify_open and item_catalog_enabled
            else None
        )
        ctx["retail_product_groups"] = []
        if (
            can_modify_open
            and order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        ):
            ctx["retail_product_groups"] = list(
                RetailProductGroup.objects.filter(
                    tenant_id=order.tenant_id,
                    is_active=True,
                    lines__isnull=False,
                )
                .prefetch_related("lines__menu_item")
                .distinct()
                .order_by("name")[:40]
            )
        ctx["add_service_form"] = (
            StaffOrderAddServiceForm(tenant_id=order.tenant_id, outlet_id=order.outlet_id)
            if can_modify_open and services_enabled
            else None
        )
        promo_qs = promotions_selectable_for_order(order) if can_modify_open else None
        ctx["apply_promotion_form"] = (
            StaffOrderApplyPromotionForm(eligible_queryset=promo_qs) if promo_qs is not None and promo_qs.exists() else None
        )
        refundable = order_refundable_remaining(order)
        can_approve_refunds = membership_can_approve_refunds(m)
        retail_refund_approvers = (
            sensitive_action_approvers(
                requester=m,
                action="refund",
                outlet_id=order.outlet_id,
            )
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            else []
        )
        retail_line_refund_approvers = (
            sensitive_action_approvers(
                requester=m,
                action="retail_line_refund",
                outlet_id=order.outlet_id,
            )
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            else []
        )
        retail_discount_approvers = (
            sensitive_action_approvers(
                requester=m,
                action="discount",
                outlet_id=order.outlet_id,
            )
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            else []
        )
        retail_void_approvers = (
            sensitive_action_approvers(
                requester=m,
                action="void",
                outlet_id=order.outlet_id,
            )
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            else []
        )
        order_refundable_state = (
            (order.status == OrderStatus.CLOSED and order.is_paid)
            or (order.status == OrderStatus.OPEN and not order.is_paid)
        )
        if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            can_refund = (
                staff_outlet_allowed_for_membership(m, order.outlet_id)
                and order_refundable_state
                and refundable > Decimal("0")
                and bool(retail_refund_approvers)
            )
        else:
            can_refund = (
                can_approve_refunds
                and staff_outlet_allowed_for_membership(m, order.outlet_id)
                and order_refundable_state
                and refundable > Decimal("0")
            )
        ctx["can_record_refund"] = can_refund
        ctx["can_approve_refunds"] = can_approve_refunds
        ctx["refundable_remaining"] = refundable
        pays = list(order.payments.all())
        ctx["refund_form"] = (
            StaffOrderRefundForm(
                initial={"amount": refundable},
                payments=pays,
                max_refund=refundable,
                approvers=retail_refund_approvers
                if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
                else None,
            )
            if can_refund
            else None
        )
        ctx["pos_menu_categories"] = []
        ctx["pos_menu_item_modifiers"] = {}
        ctx["service_offerings"] = []
        if can_modify_open:
            menu_qs = menu_items_for_outlet_queryset(order.tenant_id, order.outlet_id)
            if not item_catalog_enabled:
                menu_qs = menu_qs.none()
            menu_qs = (
                menu_qs
                .select_related("category")
                .prefetch_related(
                    Prefetch(
                        "modifier_group_links",
                        queryset=MenuItemModifierGroup.objects.select_related("group").prefetch_related(
                            Prefetch(
                                "group__options",
                                queryset=ModifierOption.objects.filter(is_active=True).order_by(
                                    "sort_order", "name"
                                ),
                            )
                        ),
                    )
                )
                .order_by("category__sort_order", "category__name", "name")
            )
            is_retail_catalogue = order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            if is_retail_catalogue:
                # Bound initial catalogue data and modifier prefetch; code scanning
                # continues through the independent validated scan_add_line handler.
                catalogue_search = (self.request.GET.get("catalogue_q") or "").strip()[:80]
                ctx["retail_catalogue_q"] = catalogue_search
                if catalogue_search:
                    menu_qs = menu_qs.filter(
                        Q(name__icontains=catalogue_search)
                        | Q(sku__icontains=catalogue_search)
                        | Q(barcode__icontains=catalogue_search)
                        | Q(
                            packages__barcode__icontains=catalogue_search,
                            packages__tenant_id=order.tenant_id,
                            packages__is_active=True,
                            packages__is_sellable=True,
                        )
                        | Q(
                            packages__sku_alias__icontains=catalogue_search,
                            packages__tenant_id=order.tenant_id,
                            packages__is_active=True,
                            packages__is_sellable=True,
                        )
                        | Q(supermarket_profile__plu_code__icontains=catalogue_search,
                            supermarket_profile__tenant_id=order.tenant_id,
                            supermarket_profile__is_active=True)
                    ).distinct()
                menu_qs = list(menu_qs[:81])
                ctx["retail_catalogue_has_more"] = len(menu_qs) > 80
                menu_qs = menu_qs[:80]
                if self.request.method == "GET" and ctx["add_line_form"] is not None:
                    # Only the visible choices need HTML option tags; POST binds and
                    # validates against the complete outlet-scoped form queryset.
                    ctx["add_line_form"].fields["menu_item"].queryset = MenuItem.objects.filter(
                        tenant_id=order.tenant_id,
                        pk__in=[item.pk for item in menu_qs],
                    ).order_by("name")
            if is_retail_catalogue:
                from django.db.models import Sum
                from apps.inventory.models import StockBalance
                from apps.inventory.batches import InventoryBatch
                # Only the visible page's tracked products, scoped to the
                # authorized tenant and till. FEFO batches may include stock
                # that is physically counted but quarantined or expired.
                tracked_ids = [item.pk for item in menu_qs if item.track_inventory]
                stock_by_product = dict(
                    StockBalance.objects.filter(
                        tenant_id=order.tenant_id, outlet_id=order.outlet_id,
                        menu_item_id__in=tracked_ids,
                    ).values_list("menu_item_id", "quantity")
                )
                batches = InventoryBatch.objects.filter(
                    tenant_id=order.tenant_id, outlet_id=order.outlet_id,
                    menu_item_id__in=tracked_ids,
                ).values("menu_item_id").annotate(
                    usable=Sum("remaining_quantity", filter=(
                        Q(quarantined=False)
                        & (Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate()))
                    )),
                )
                usable_by_product = {
                    row["menu_item_id"]: row["usable"] or Decimal("0")
                    for row in batches
                }
                outlet_prices = dict(
                    MenuItemOutlet.objects.filter(
                        outlet_id=order.outlet_id, menu_item__tenant_id=order.tenant_id,
                        menu_item_id__in=[item.pk for item in menu_qs],
                        price_override__isnull=False,
                    ).values_list("menu_item_id", "price_override")
                )
                for item in menu_qs:
                    item.cashier_display_price = outlet_prices.get(item.pk, item.unit_price)
                    if not item.track_inventory:
                        continue
                    on_hand = stock_by_product.get(item.pk, Decimal("0"))
                    has_batches = item.pk in usable_by_product
                    # Once batch tracking starts, settlement requires usable
                    # FEFO quantity, not the potentially larger legacy balance.
                    qty = min(on_hand, usable_by_product[item.pk]) if has_batches else on_hand
                    item.cashier_stock_quantity = qty
                    item.cashier_stock_batch_limited = has_batches and qty < on_hand
                    item.cashier_stock_low = (
                        qty <= item.reorder_level
                        if item.reorder_level is not None else qty <= 0
                    )
            modifiers_by_item: dict[str, list] = {}
            for item in menu_qs:
                groups_payload: list[dict] = []
                for link in sorted(
                    item.modifier_group_links.all(),
                    key=lambda x: (x.sort_order, x.group.name),
                ):
                    g = link.group
                    opts = list(g.options.all())
                    if not opts:
                        continue
                    groups_payload.append(
                        {
                            "group_id": str(g.id),
                            "name": g.name,
                            "min": g.min_selections,
                            "max": g.max_selections,
                            "options": [
                                {"id": str(o.id), "name": o.name, "price_delta": str(o.price_delta)}
                                for o in opts
                            ],
                        }
                    )
                modifiers_by_item[str(item.id)] = groups_payload
            ctx["pos_menu_item_modifiers"] = modifiers_by_item
            grouped: dict[str, dict] = {}
            for item in menu_qs:
                cat = item.category
                key = str(cat.id)
                if key not in grouped:
                    grouped[key] = {
                        "id": str(cat.id),
                        "name": cat.name,
                        "menu_items": [],
                    }
                grouped[key]["menu_items"].append(item)
            ctx["pos_menu_categories"] = list(grouped.values())
            ctx["retail_quick_pick_ids"] = []
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
                # Actual successful paid sales, scoped to the current tenant/outlet.
                # Restrict the resulting shortcuts to products in the visible catalogue.
                available_ids = {str(item.id) for category in grouped.values() for item in category["menu_items"]}
                popular = (
                    OrderLine.objects.filter(
                        order__tenant_id=order.tenant_id, order__outlet_id=order.outlet_id,
                        order__status=OrderStatus.CLOSED, order__is_paid=True,
                        order__created_at__gte=timezone.now() - timedelta(days=30),
                        is_voided=False, menu_item_id__isnull=False,
                    )
                    .values("menu_item_id").annotate(sales_count=Count("id"))
                    .order_by("-sales_count", "menu_item_id")[:40]
                )
                ctx["retail_quick_pick_ids"] = [
                    str(row["menu_item_id"]) for row in popular
                    if str(row["menu_item_id"]) in available_ids
                ][:8]
            if services_enabled:
                ctx["service_offerings"] = list(
                    ServiceOffering.objects.filter(tenant_id=order.tenant_id, is_active=True)
                    .filter(Q(outlets__isnull=True) | Q(outlets__id=order.outlet_id))
                    .distinct()
                    .order_by("name")
                )
                service_options = list(
                    ServiceOfferingOption.objects.filter(
                        service_offering__tenant_id=order.tenant_id,
                        service_offering__is_active=True,
                        is_active=True,
                    )
                    .filter(
                        Q(service_offering__outlets__isnull=True)
                        | Q(service_offering__outlets__id=order.outlet_id)
                    )
                    .select_related("service_offering")
                    .order_by("service_offering__name", "sort_order", "name")
                )
                options_by_service: dict[str, list[ServiceOfferingOption]] = {}
                for opt in service_options:
                    options_by_service.setdefault(str(opt.service_offering_id), []).append(opt)
                for svc in ctx["service_offerings"]:
                    svc.active_options = options_by_service.get(str(svc.id), [])
        is_supermarket_outlet = order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        ctx["is_supermarket_outlet"] = is_supermarket_outlet
        from apps.pos.models import RetailPickup
        ctx["retail_pickup"] = RetailPickup.objects.filter(
            tenant_id=order.tenant_id, order=order,
        ).select_related("collected_by").first()
        from apps.pos.services.wholesale import manager_allowed
        ctx["can_schedule_paid_pickup"] = bool(
            is_supermarket_outlet and order.is_paid and order.customer_id
            and order.status == OrderStatus.CLOSED
            and not order.refunds.exists()
            and manager_allowed(self.request.tenant_membership, order.tenant_id, order.outlet_id)
        )
        from apps.pos.services.wholesale import manager_allowed, qualifying_rule
        ctx["can_apply_wholesale"] = bool(
            can_modify_open and is_supermarket_outlet and order.customer_id
            and not order.payments.exists()
            and manager_allowed(m, order.tenant_id, order.outlet_id)
        )
        ctx["wholesale_available_lines"] = []
        if ctx["can_apply_wholesale"]:
            ctx["wholesale_available_lines"] = [
                (line, qualifying_rule(tenant_id=order.tenant_id,
                    outlet_id=order.outlet_id, menu_item_id=line.menu_item_id,
                    quantity=line.quantity))
                for line in order.lines.all() if line.menu_item_id and not line.is_voided
            ]
        ctx["scan_add_form"] = (
            StaffOrderScanAddForm()
            if can_modify_open and is_supermarket_outlet and hardware["barcode_scanner_enabled"]
            else None
        )
        ctx["line_discount_form"] = (
            StaffOrderLineDiscountForm(approvers=retail_discount_approvers)
            if can_modify_open and is_supermarket_outlet and retail_discount_approvers
            else None
        )
        ctx["discount_request_key"] = uuid.uuid4() if ctx["line_discount_form"] is not None else None
        ctx["void_order_form"] = (
            StaffOrderVoidOrderForm(approvers=retail_void_approvers)
            if can_modify_open and is_supermarket_outlet and retail_void_approvers
            else None
        )
        ctx["void_request_key"] = uuid.uuid4() if ctx["void_order_form"] is not None else None
        ctx["line_return_form"] = (
            StaffOrderLineReturnForm()
            if is_supermarket_outlet and order.status == OrderStatus.CLOSED and order.is_paid
            else None
        )
        ctx["retail_refund_form"] = (
            StaffRetailLineRefundForm(
                lines=list(order.lines.all()),
                payments=pays,
                max_refund=refundable,
                approvers=retail_line_refund_approvers,
            ) if is_supermarket_outlet and can_refund else None
        )
        for line in order.lines.all():
            current = line.quantity
            dec = current - Decimal("1")
            if dec < Decimal("0.001"):
                dec = Decimal("0.001")
            inc = current + Decimal("1")
            line.pos_qty_dec = str(dec.normalize())
            line.pos_qty_inc = str(inc.normalize())
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        order: Order = self.object
        action = request.POST.get("action", "").strip()
        m = self.request.tenant_membership

        if not staff_outlet_allowed_for_membership(m, order.outlet_id):
            message = "You cannot modify this order for its outlet."
            if (
                action in {"adjust_line_qty", "assign_line_seat"}
                and request.headers.get("X-Requested-With") == "XMLHttpRequest"
            ):
                return JsonResponse({"ok": False, "message": message}, status=403)
            messages.error(request, message)
            return redirect("staff-order-detail", order_id=order.id)
        # A held retail basket is parked, not an active checkout. Reopen it
        # explicitly before scanning, editing or collecting further tenders.
        # Supervisor refunds remain available for payment reconciliation.
        if (order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
                and order.status == OrderStatus.OPEN and order.table_label
                and action not in {"resume_order", "record_refund", "retail_line_refund"}):
            message = "This basket is on hold. Resume it before editing or taking another payment."
            if (action == "adjust_line_qty"
                    and request.headers.get("X-Requested-With") == "XMLHttpRequest"):
                return JsonResponse({"ok": False, "message": message}, status=409)
            messages.error(request, message)
            return redirect("staff-orders")
        if action == "ack_ready_line":
            # A server assigned to this order may acknowledge its ready handoff;
            # this is intentionally narrower than general order/payment edits.
            return self._post_ack_ready_line(request, order)
        if action == "record_refund":
            # Retail refunds use transaction-bound supervisor approval; other
            # business lines retain the existing manager-only check.
            return self._post_record_refund(request, order)
        if action == "retail_line_refund":
            return self._post_retail_line_refund(request, order)
        if (
            action == "line_discount"
            and order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        ):
            return self._post_line_discount(request, order)
        cashier_actions = {
            "add_line",
            "add_retail_group",
            "scan_add_line",
            "adjust_line_qty",
            "record_payment",
            "hold_order",
            "resume_order",
            "void_order",
            "void_line",
            # Eligible promotions are policy-defined offers, not manual price
            # overrides. Retail cashier UI already exposes them on active sales.
            "apply_promotion",
            "quick_create_product",
            "assign_serial",
            "release_serial",
        }
        hospitality_actions = {
            "add_line",
            "add_service_line",
            "adjust_line_qty",
            "assign_line_seat",
            "record_payment",
            "void_line",
            "apply_promotion",
            "set_customer",
        }
        if not (
            membership_can_modify_lodging(m)
            or (action in cashier_actions and _can_operate_retail_checkout(m, order))
            or (
                action in hospitality_actions
                and _can_operate_hospitality_order(m, order)
            )
        ):
            if (
                action in {"adjust_line_qty", "assign_line_seat"}
                and request.headers.get("X-Requested-With") == "XMLHttpRequest"
            ):
                message = (
                    "Your role is not allowed to change item seats on this check."
                    if action == "assign_line_seat"
                    else "Your role is not allowed to change quantities on this basket."
                )
                return JsonResponse({"ok": False, "message": message}, status=403)
            messages.error(request, "Your role cannot modify orders or payments.")
            return redirect("staff-order-detail", order_id=order.id)

        if action == "set_customer":
            return self._post_set_customer(request, order)

        if action == "apply_wholesale":
            return self._post_apply_wholesale(request, order)
        if action in ("schedule_paid_pickup", "hand_over_paid_pickup"):
            return self._post_paid_pickup(request, order, action=action)
        if action == "record_payment":
            return self._post_record_payment(request, order)
        if action == "set_folio":
            return self._post_set_folio(request, order)
        if action == "charge_to_folio":
            async_charge = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                and order.outlet.outlet_type in {
                    OutletType.RESTAURANT, OutletType.BAR,
                    OutletType.LOUNGE, OutletType.CAFETERIA,
                }
            )
            try:
                charge_order_to_folio(order=order, membership=m, user=request.user)
            except DRFValidationError as exc:
                detail = " ".join(_drf_detail_messages(exc.detail)) or "Folio charge rejected."
                if async_charge:
                    return JsonResponse({"ok": False, "message": detail}, status=409)
                _flash_drf_validation(request, exc)
            else:
                if async_charge:
                    return JsonResponse({"ok": True, "message": "Remaining balance charged to the guest folio."})
                messages.success(request, "Remaining balance charged to the guest folio.")
            return redirect("staff-order-detail", order_id=order.id)
        if action == "assign_serial":
            return self._post_assign_serial(request, order)
        if action == "release_serial":
            return self._post_release_serial(request, order)
        if action == "quick_create_product":
            return self._post_quick_create_product(request, order)
        if action == "add_line":
            return self._post_add_line(request, order)
        if action == "add_retail_group":
            return self._post_add_retail_group(request, order)
        if action == "add_service_line":
            return self._post_add_service_line(request, order)
        if action == "adjust_line_qty":
            return self._post_adjust_line_quantity(request, order)
        if action == "assign_line_seat":
            return self._post_assign_line_seat(request, order)
        if action == "scan_add_line":
            return self._post_scan_add_line(request, order)
        if action == "line_discount":
            return self._post_line_discount(request, order)
        if action == "line_return":
            return self._post_line_return(request, order)
        if action == "retail_line_refund":
            return self._post_retail_line_refund(request, order)
        if action == "hold_order":
            return self._post_hold_order(request, order)
        if action == "resume_order":
            return self._post_resume_order(request, order)
        if action == "void_order":
            return self._post_void_order(request, order)
        if action == "apply_promotion":
            return self._post_apply_promotion(request, order)
        if action == "void_line":
            return self._post_void_line(request, order)
        messages.error(request, "Unknown action.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_assign_serial(self, request: HttpRequest, order: Order) -> HttpResponse:
        from apps.inventory.services_serials import assign_serial_to_order_line

        try:
            line_id = uuid.UUID((request.POST.get("line_id") or "").strip())
        except (TypeError, ValueError):
            messages.error(request, "Choose a serialized sale line.")
            return redirect("staff-order-detail", order_id=order.pk)
        line = OrderLine.objects.filter(
            pk=line_id,
            order=order,
            is_voided=False,
            menu_item__serial_tracking=True,
        ).select_related("menu_item").first()
        if line is None:
            messages.error(request, "Serialized sale line not found.")
            return redirect("staff-order-detail", order_id=order.pk)
        try:
            unit = assign_serial_to_order_line(
                order_line=line,
                serial_number=request.POST.get("serial_number", ""),
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(
                request,
                f"{line.menu_item.get_serial_identifier_type_display()} {unit.serial_number} assigned to {line.label}.",
            )
        return redirect("staff-order-detail", order_id=order.pk)

    def _post_release_serial(self, request: HttpRequest, order: Order) -> HttpResponse:
        from apps.inventory.services_serials import release_serial_from_order_line

        try:
            line_id = uuid.UUID((request.POST.get("line_id") or "").strip())
            serial_unit_id = uuid.UUID((request.POST.get("serial_unit_id") or "").strip())
        except (TypeError, ValueError):
            messages.error(request, "Invalid serialized unit selection.")
            return redirect("staff-order-detail", order_id=order.pk)
        line = OrderLine.objects.filter(
            pk=line_id,
            order=order,
            is_voided=False,
            menu_item__serial_tracking=True,
        ).first()
        if line is None:
            messages.error(request, "Serialized sale line not found.")
            return redirect("staff-order-detail", order_id=order.pk)
        try:
            unit = release_serial_from_order_line(
                order_line=line,
                serial_unit_id=serial_unit_id,
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, f"Released {unit.serial_number} from this basket.")
        return redirect("staff-order-detail", order_id=order.pk)

    def _post_set_customer(self, request: HttpRequest, order: Order) -> HttpResponse:
        membership = request.tenant_membership
        async_retail = (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_retail:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if (
            order.status != OrderStatus.OPEN
            and membership.role not in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}
        ):
            return reject(
                "Only an owner can correct a closed order's customer link.",
                status=403,
            )

        raw = request.POST.get("customer_id", "").strip()
        try:
            customer_id = uuid.UUID(raw) if raw else None
        except ValueError:
            return reject("Invalid customer reference.")

        customer = None
        if customer_id:
            customer = (
                visible_customers(membership, request.user)
                .filter(pk=customer_id)
                .filter(
                    Q(orders__outlet_id=order.outlet_id)
                    | Q(created_by=request.user)
                    | Q(pk=order.customer_id)
                )
                .first()
            )
            if customer is None and can_manage_customers(membership):
                # A newly created customer can remain hidden from the shared
                # directory until it is linked to this worker's scoped sale.
                # Keep this narrow exception inside checkout; never widen the
                # tenant/site customer directory just because the user created it.
                customer = Customer.objects.filter(
                    pk=customer_id,
                    tenant_id=order.tenant_id,
                    merged_into__isnull=True,
                    created_by=request.user,
                ).first()
            if customer is None:
                return reject("Choose a customer visible at this register.", status=403)

        before = str(order.customer_id) if order.customer_id else None
        changed = order.customer_id != customer_id
        if changed:
            from apps.customers.models import LoyaltyLedgerEntry

            if LoyaltyLedgerEntry.objects.filter(
                tenant_id=order.tenant_id,
                source_type="sale",
                source_key=str(order.pk),
            ).exists():
                return reject(
                    "This sale has earned customer points. Its customer cannot be relinked directly; "
                    "review the original transaction or use the verified customer merge.",
                    status=409,
                )
            order.customer = customer
            order.save(update_fields=["customer", "updated_at"])
            log_audit(
                tenant_id=order.tenant_id,
                user_id=request.user.pk,
                action="order.customer_link_changed",
                entity_type="order",
                entity_id=str(order.pk),
                payload={
                    "before": before,
                    "after": str(customer_id) if customer_id else None,
                },
            )

        message = (
            "Customer link saved. Transaction amounts and receipt details were not changed."
            if changed
            else "Customer link was already current."
        )
        if async_retail:
            return JsonResponse({
                "ok": True,
                "message": message,
                "changed": changed,
                "customer_id": str(customer.pk) if customer else "",
                "customer_name": customer.name if customer else "",
            })
        if changed:
            messages.success(request, message)
        else:
            messages.info(request, message)
        return redirect("staff-order-detail", order_id=order.id)

    def _post_paid_pickup(
        self,
        request: HttpRequest,
        order: Order,
        *,
        action: str,
    ) -> HttpResponse:
        from apps.pos.models import RetailPickup
        from apps.pos.services.pickups import (
            hand_over_paid_pickup,
            register_paid_pickup,
        )

        async_retail = (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_retail:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        try:
            if action == "schedule_paid_pickup":
                pickup, replay = register_paid_pickup(
                    order=order,
                    expected_on=parse_date(request.POST.get("expected_on", "")),
                    note=request.POST.get("note", ""),
                    user=request.user,
                    membership=request.tenant_membership,
                )
                message = (
                    "Pickup was already scheduled with these details."
                    if replay
                    else "Paid order scheduled for collection; stock was not deducted again."
                )
            else:
                pickup = RetailPickup.objects.filter(
                    tenant_id=order.tenant_id,
                    order=order,
                ).first()
                if pickup is None:
                    return reject("This order has no registered pickup.", status=409)
                pickup, replay = hand_over_paid_pickup(
                    pickup=pickup,
                    note=request.POST.get("note", ""),
                    membership=request.tenant_membership,
                    user=request.user,
                )
                message = (
                    "This pickup was already recorded as collected."
                    if replay
                    else "Customer pickup recorded; sale and inventory are unchanged."
                )
        except DRFValidationError as exc:
            return reject(" ".join(_drf_detail_messages(exc.detail)))
        except (ValueError, TypeError) as exc:
            return reject(str(exc))

        if async_retail:
            return JsonResponse({
                "ok": True,
                "message": message,
                "replay": replay,
                "pickup_id": str(pickup.pk),
                "pickup_status": pickup.status,
                "expected_on": pickup.expected_on.isoformat(),
            })
        if replay:
            messages.info(request, message)
        else:
            messages.success(request, message)
        return redirect("staff-order-detail", order_id=order.id)

    def _post_apply_wholesale(self, request: HttpRequest, order: Order) -> HttpResponse:
        from apps.pos.services.wholesale import apply_wholesale_tier

        async_retail = (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_retail:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        try:
            line, replay = apply_wholesale_tier(
                order=order,
                line_id=request.POST.get("line_id"),
                membership=request.tenant_membership,
                user=request.user,
            )
        except DRFValidationError as exc:
            return reject(" ".join(_drf_detail_messages(exc.detail)))
        except (ValueError, TypeError) as exc:
            return reject(str(exc))

        message = (
            "Wholesale price was already applied."
            if replay
            else "Wholesale unit price approved and recalculated."
        )
        order.refresh_from_db()
        if async_retail:
            return JsonResponse({
                "ok": True,
                "message": message,
                "replay": replay,
                "order_id": str(order.pk),
                "line_id": str(line.pk),
                "currency": order.currency,
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
                "subtotal": str(order.subtotal),
                "discount": str(order.discount_amount),
                "tax": str(order.tax_total),
                "total": str(order.total),
            })
        if replay:
            messages.info(request, message)
        else:
            messages.success(request, message)
        return redirect("staff-order-detail", order_id=order.id)

    def _post_set_folio(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_folio = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.RESTAURANT, OutletType.BAR,
                OutletType.LOUNGE, OutletType.CAFETERIA,
            }
        )

        def reject(message, status=422):
            if async_folio:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if not _tenant_lodging_enabled(order.tenant):
            return reject("Lodging and folios are not enabled for this business.", 409)
        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Folio can only be changed on open, unpaid orders.", 409)
        folio_qs = Folio.objects.filter(
            tenant_id=order.tenant_id,
            site_id=order.outlet.site_id,
            status=FolioStatus.OPEN,
        ).order_by("-created_at")[:50]
        form = StaffOrderSetFolioForm(
            request.POST,
            folio_queryset=folio_qs,
            initial_folio_id=order.folio_id,
        )
        if not form.is_valid():
            return reject("; ".join(f"{fld}: {err}" for fld, errors in form.errors.items() for err in errors))
        folio_id = form.cleaned_data["folio_id"]
        try:
            set_open_order_folio(
                order=order,
                membership=request.tenant_membership,
                folio_id=folio_id,
                user=request.user,
            )
        except DRFValidationError as exc:
            if async_folio:
                return reject(" ".join(_drf_detail_messages(exc.detail)), 409)
            _flash_drf_validation(request, exc)
        else:
            if async_folio:
                return JsonResponse({"ok": True, "message": "Folio cleared." if folio_id is None else "Folio attached."})
            if folio_id is None:
                messages.success(request, "Folio cleared.")
            else:
                messages.success(request, "Folio attached.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_ack_ready_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def reject(message, status=400):
            if xhr:
                return JsonResponse({"ok": False, "message": message}, status=status)
            messages.error(request, message)
            return redirect("staff-order-detail", order_id=order.id)

        assigned_server = bool(order.created_by_id and order.created_by_id == request.user.id)
        if not membership_can_acknowledge_ready_handoff(
            request.tenant_membership,
            is_assigned_server=assigned_server,
        ):
            return reject("Only the assigned server or a manager can acknowledge ready items.", 403)
        handoff_state_allowed = (
            (order.status == OrderStatus.OPEN and not order.is_paid)
            or (
                order.outlet.outlet_type in {
                    OutletType.RESTAURANT,
                    OutletType.BAR,
                    OutletType.LOUNGE,
                    OutletType.CAFETERIA,
                }
                and order.status == OrderStatus.CLOSED
                and order.is_paid
            )
        )
        if not handoff_state_allowed:
            return reject(
                "Handoff acknowledgements are available only on active checks "
                "or paid hospitality checks still awaiting service.",
                409,
            )
        form = StaffOrderReadyHandoffForm(request.POST)
        if not form.is_valid():
            error = next(iter(next(iter(form.errors.values()))), "Invalid handoff request.")
            return reject(str(error))
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
            is_voided=False,
        ).first()
        if line is None:
            return reject("That line is not on this order.", 404)
        if line.kds_status != KdsLineStatus.READY:
            return reject("Only ready items can be acknowledged for handoff.", 409)
        try:
            update_order_line_kds_status(
                order=order,
                line=line,
                kds_status=KdsLineStatus.SERVED.value,
                kds_station=None,
                user=request.user,
            )
        except DRFValidationError as exc:
            message = " ".join(_drf_detail_messages(exc.detail))
            return reject(message)
        message = f"Handoff acknowledged: {line.label}"
        if xhr:
            return JsonResponse({
                "ok": True,
                "message": message,
                "line_id": str(line.id),
            })
        messages.success(request, message)
        return redirect("staff-order-detail", order_id=order.id)

    @staticmethod
    def _payment_request_key(request: HttpRequest) -> str:
        # A rendered payment form carries one stable key. Retries of the same
        # form use the same domain idempotency identity, not a fresh UUID.
        # Old API/integration forms without it retain backwards compatibility.
        raw = (request.POST.get("payment_request_key") or "").strip()
        try:
            return str(uuid.UUID(raw)) if raw else str(uuid.uuid4())
        except (TypeError, ValueError):
            raise DRFValidationError("Invalid payment request identity.")

    @staticmethod
    def _sensitive_request_key(request: HttpRequest, field: str) -> str:
        raw = (request.POST.get(field) or "").strip()
        try:
            return str(uuid.UUID(raw)) if raw else str(uuid.uuid4())
        except (TypeError, ValueError):
            raise DRFValidationError("Invalid approval request identity.")

    @staticmethod
    def _refund_request_key(request: HttpRequest, field: str = "refund_request_key") -> str:
        # Refund forms also carry stable request identities so a double click
        # or browser replay cannot create a second financial transaction.
        raw = (request.POST.get(field) or "").strip()
        try:
            return str(uuid.UUID(raw)) if raw else str(uuid.uuid4())
        except (TypeError, ValueError):
            raise DRFValidationError("Invalid refund request identity.")

    def _post_record_payment(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_payment = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.RETAIL,
                OutletType.SUPERMARKET,
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_payment:
                return JsonResponse({"ok": False, "message": message}, status=status)
            messages.error(request, message)
            return redirect("staff-order-detail", order_id=order.id)

        _, bal = order_payment_totals(order)
        if (
            order.status != OrderStatus.OPEN
            or order.is_paid
            or bal <= Decimal("0")
        ):
            return reject(
                "Payments can only be recorded on open orders with an outstanding balance.",
                status=409,
            )
        form = StaffOrderPaymentForm(request.POST)
        if not form.is_valid():
            errors = [
                f"{field}: {error}"
                for field, error_list in form.errors.items()
                for error in error_list
            ]
            return reject(" ".join(errors) or "Check the payment details.")
        try:
            record_order_payment(
                order=order,
                user=request.user,
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                idempotency_key=self._payment_request_key(request),
                workstation_id=settlement_workstation_id(request, outlet=order.outlet),
            )
        except DRFValidationError as exc:
            detail = " ".join(_drf_detail_messages(exc.detail)) or "Payment could not be recorded."
            if async_payment:
                return JsonResponse({"ok": False, "message": detail}, status=409)
            _flash_drf_validation(request, exc)
            return redirect("staff-order-detail", order_id=order.id)

        order.refresh_from_db(fields=["is_paid", "status"])
        paid, remaining = order_payment_totals(order)
        completed = bool(order.is_paid and order.status == OrderStatus.CLOSED)
        is_retail = order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        if completed:
            if is_retail:
                from .views_customer_display import mark_customer_display_completed
                mark_customer_display_completed(order, request)
            message = (
                "Sale fully paid and completed. The final receipt is ready."
                if is_retail
                else "Check fully paid and completed. The final receipt is ready."
            )
        else:
            message = (
                f"Partial payment recorded. Balance remaining: {order.currency} {remaining:.2f}. "
                + (
                    "You may hold this basket and resume payment later."
                    if is_retail
                    else "You can continue service or collect the remaining payment later."
                )
            )

        if async_payment:
            return JsonResponse(
                {
                    "ok": True,
                    "message": message,
                    "completed": completed,
                    "currency": order.currency,
                    "paid": f"{paid:.2f}",
                    "due": f"{remaining:.2f}",
                }
            )
        messages.success(request, message)
        return redirect("staff-order-detail", order_id=order.id)

    def _post_quick_create_product(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_quick = (
            order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message, status=422):
            if async_quick:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        def accepted(message, *, replay=False):
            if async_quick:
                return JsonResponse({
                    "ok": True,
                    "message": str(message),
                    "order_id": str(order.pk),
                    "replay": replay,
                    "next_request_key": str(uuid.uuid4()),
                })
            if replay:
                messages.info(request, str(message))
            else:
                messages.success(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Quick product creation is available only at retail checkouts.", 409)
        if not _tenant_item_catalog_enabled(order.tenant) or order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Open an unpaid retail sale before adding a new product.", 409)
        form = RetailQuickProductForm(request.POST)
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, error_list in form.errors.items()
                for error in error_list
            ) or "Check the quick product details."
            return reject(detail)
        data = form.cleaned_data
        try:
            request_key = str(uuid.UUID(request.POST.get("quick_product_request_key", "")))
        except (ValueError, AttributeError, TypeError):
            return reject("Quick-add form expired. Reload the checkout and try again.", 409)
        if AuditEvent.objects.filter(
            tenant_id=order.tenant_id, action="catalog.quick_product_created",
            payload__order_id=str(order.pk), payload__request_key=request_key,
        ).exists():
            return accepted(
                "This product was already added; the repeated request was ignored.",
                replay=True,
            )
        if data["barcode"] and MenuItem.objects.filter(
            tenant_id=order.tenant_id, barcode=data["barcode"],
        ).exists():
            return reject(
                "This barcode already exists. Search for its registered product instead.",
                409,
            )
        # Prevent a second quick-entry for an already catalogued product.
        duplicate = MenuItem.objects.filter(
            tenant_id=order.tenant_id, name__iexact=data["name"],
            is_active=True,
        ).first()
        if duplicate:
            return reject(
                "A product with this name already exists. Search the catalogue before creating another.",
                409,
            )
        try:
            with transaction.atomic():
                # Serialize edits to this basket and reject a concurrent settlement.
                current = Order.objects.select_for_update().get(
                    pk=order.pk, tenant_id=order.tenant_id,
                )
                prior = AuditEvent.objects.filter(
                    tenant_id=order.tenant_id, action="catalog.quick_product_created",
                    payload__order_id=str(order.pk),
                    payload__request_key=request_key,
                ).first()
                if prior:
                    return accepted(
                        "This product was already added; the repeated request was ignored.",
                        replay=True,
                    )
                if current.status != OrderStatus.OPEN or current.is_paid:
                    raise ValueError("This sale is no longer open; no product was created.")
                category, _ = MenuCategory.objects.get_or_create(
                    tenant_id=order.tenant_id, name="Needs catalogue review",
                    defaults={"is_active": True, "sort_order": 9999},
                )
                # Serialize quick-registration across separate orders for the
                # same tenant, not just retries against one basket.
                # Coordinate with console product creation/edit using the tenant row.
                from apps.tenants.models import Tenant
                Tenant.objects.select_for_update().get(pk=order.tenant_id)
                MenuCategory.objects.select_for_update().get(pk=category.pk)
                if data["barcode"] and MenuItem.objects.filter(
                    tenant_id=order.tenant_id, barcode=data["barcode"]
                ).exists():
                    raise ValueError("This barcode is already registered.")
                if MenuItem.objects.filter(
                    tenant_id=order.tenant_id, name__iexact=data["name"], is_active=True,
                ).exists():
                    raise ValueError("This product name is already registered.")
                item = MenuItem.objects.create(
                    tenant_id=order.tenant_id, category=category,
                    name=data["name"], unit_price=data["unit_price"],
                    sku="QUICK-" + uuid.uuid4().hex[:16].upper(),
                    barcode=data["barcode"], is_active=True,
                    track_inventory=False, unit_of_measure="each",
                    description="Quick-added during checkout; cost, stock, tax and supplier details require catalogue review.",
                )
                # Quick-added stock is only available at the originating store.
                MenuItemOutlet.objects.create(menu_item=item, outlet=order.outlet)
                add_line_to_open_order(
                    order=order, menu_item=item, quantity=Decimal(data["quantity"]),
                    user=request.user,
                )
                log_audit(
                    tenant_id=order.tenant_id, user_id=request.user.pk,
                    action="catalog.quick_product_created", entity_type="menu_item",
                    entity_id=str(item.pk),
                    payload={
                        "order_id": str(order.pk), "outlet_id": str(order.outlet_id),
                        "unit_price": str(data["unit_price"]),
                        "quantity": str(data["quantity"]), "requires_review": True,
                        "stock_tracked": False,
                        "request_key": request_key,
                    },
                )
        except (DRFValidationError, ValueError, TypeError) as exc:
            return reject(f"Could not add product: {getattr(exc, 'detail', exc)}")
        return accepted("New product saved and added to this sale. Catalogue review required.")

    def _post_add_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_add = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.RETAIL,
                OutletType.SUPERMARKET,
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
        )
        def reject(message, status=422):
            if async_add:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if not _tenant_item_catalog_enabled(order.tenant):
            return reject("Items and menus are not enabled for this business.", 403)
        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Lines can only be added to open orders that are not yet paid.", 409)
        form = StaffOrderAddLineForm(
            request.POST,
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
        )
        if not form.is_valid():
            if async_add:
                return reject("; ".join(str(error) for errors in form.errors.values() for error in errors))
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        modifier_option_ids: list[uuid.UUID] = []
        for token in request.POST.getlist("modifier_option"):
            t = (token or "").strip()
            if not t:
                continue
            try:
                modifier_option_ids.append(uuid.UUID(t))
            except ValueError:
                return reject("Invalid modifier selection.")
        try:
            added_line = add_line_to_open_order(
                order=order,
                menu_item=form.cleaned_data["menu_item"],
                quantity=form.cleaned_data["quantity"],
                user=request.user,
                modifier_option_ids=modifier_option_ids or None,
                seat_number=form.cleaned_data.get("seat_number"),
            )
        except DRFValidationError as exc:
            if async_add:
                return reject(exc.detail)
            _flash_drf_validation(request, exc)
        else:
            if async_add:
                order.refresh_from_db(fields=["subtotal", "discount_amount", "tax_total", "total", "currency"])
                return JsonResponse({
                    "ok": True,
                    "message": "Line added.",
                    "order_id": str(order.pk),
                    "line_id": str(added_line.pk),
                    "total": str(order.total),
                    "currency": order.currency,
                })
            messages.success(request, "Line added.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_add_retail_group(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_add = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def reject(message, status=422):
            if async_add:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.pk)

        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Retail product groups are available only at supermarket or retail checkout.", 403)
        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Groups can be added only to an open unpaid basket.", 409)
        try:
            group_id = uuid.UUID((request.POST.get("retail_group_id") or "").strip())
        except (TypeError, ValueError):
            return reject("Choose a retail product group.")
        group = RetailProductGroup.objects.filter(
            pk=group_id,
            tenant_id=order.tenant_id,
            is_active=True,
        ).first()
        if group is None:
            return reject("Choose an active retail product group.")
        try:
            add_retail_group_to_open_order(
                order=order,
                retail_group=group,
                quantity=(request.POST.get("quantity") or "1").strip(),
                user=request.user,
            )
        except DRFValidationError as exc:
            return reject(exc.detail, 409)
        if async_add:
            order.refresh_from_db(fields=["subtotal", "tax_total", "total", "currency"])
            return JsonResponse({
                "ok": True,
                "message": f"{group.name} added.",
                "order_id": str(order.pk),
                "currency": order.currency,
                "total": str(order.total),
            })
        messages.success(request, f"{group.name} added to basket.")
        return redirect("staff-order-detail", order_id=order.pk)


    def _post_add_service_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_service = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.RESTAURANT, OutletType.BAR,
                OutletType.LOUNGE, OutletType.CAFETERIA,
            }
        )

        def reject(message, status=422):
            if async_service:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if not _tenant_services_enabled(order.tenant):
            return reject("Services are not enabled for this business.", 409)
        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Services can only be added to open orders that are not yet paid.", 409)
        form = StaffOrderAddServiceForm(
            request.POST,
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
        )
        if not form.is_valid():
            return reject("; ".join(f"{fld}: {err}" for fld, errors in form.errors.items() for err in errors))
        try:
            add_service_to_open_order(
                order=order,
                service_offering=form.cleaned_data["service_offering"],
                service_option=form.cleaned_data.get("service_option"),
                quantity=form.cleaned_data["quantity"],
                user=request.user,
            )
        except DRFValidationError as exc:
            if async_service:
                return reject(" ".join(_drf_detail_messages(exc.detail)), 409)
            _flash_drf_validation(request, exc)
        else:
            if async_service:
                return JsonResponse({"ok": True, "message": "Service added."})
            messages.success(request, "Service added.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_assign_line_seat(self, request: HttpRequest, order: Order) -> HttpResponse:
        hospitality_outlets = {
            OutletType.RESTAURANT,
            OutletType.BAR,
            OutletType.LOUNGE,
            OutletType.CAFETERIA,
        }
        async_seat = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in hospitality_outlets
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_seat:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.pk)

        if (
            order.outlet.outlet_type not in hospitality_outlets
            or order.service_mode != OrderServiceMode.DINE_IN
        ):
            return reject(
                "Seat assignment is available only on dine-in checks.",
                status=409,
            )
        try:
            line_id = uuid.UUID((request.POST.get("line_id") or "").strip())
        except (TypeError, ValueError):
            return reject("Choose a valid order item.")
        line = OrderLine.objects.filter(
            pk=line_id,
            order=order,
            is_voided=False,
        ).first()
        if line is None:
            return reject("That item is no longer on this check.", status=404)
        try:
            updated, changed = assign_order_line_seat(
                order=order,
                line=line,
                seat_number=(request.POST.get("seat_number") or "").strip(),
                user=request.user,
            )
        except DRFValidationError as exc:
            return reject(" ".join(_drf_detail_messages(exc.detail)))

        message = "Seat updated." if changed else "Seat was already current."
        if async_seat:
            return JsonResponse({
                "ok": True,
                "message": message,
                "changed": changed,
                "line_id": str(updated.pk),
                "seat_number": updated.seat_number,
                "seat_label": (
                    f"Seat {updated.seat_number}"
                    if updated.seat_number
                    else "Shared table item"
                ),
            })
        messages.success(request, message)
        return redirect("staff-order-detail", order_id=order.pk)

    def _post_adjust_line_quantity(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_qty = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.SUPERMARKET,
                OutletType.RETAIL,
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
        )
        if order.status != OrderStatus.OPEN or order.is_paid:
            if async_qty:
                return JsonResponse({"ok": False, "message": "This basket is no longer open for quantity changes."}, status=409)
            messages.error(
                request,
                "Line quantities can only be edited on open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderAdjustLineQuantityForm(request.POST)
        if not form.is_valid():
            if async_qty:
                return JsonResponse({"ok": False, "message": "; ".join(
                    str(error) for errors in form.errors.values() for error in errors
                )}, status=422)
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            if async_qty:
                return JsonResponse({"ok": False, "message": "This item is no longer on the basket."}, status=404)
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            adjusted = adjust_open_order_line_quantity(
                order=order,
                line=line,
                quantity=form.cleaned_data["quantity"],
                user=request.user,
            )
        except DRFValidationError as exc:
            if async_qty:
                detail = exc.detail
                refund_required = False
                if isinstance(detail, dict):
                    items = [
                        item for value in detail.values()
                        for item in (value if isinstance(value, (list, tuple)) else [value])
                    ]
                    message = "; ".join(str(item) for item in items)
                    refund_required = any(getattr(item, "code", "") == "refund_required" for item in items)
                else:
                    items = detail if isinstance(detail, (list, tuple)) else [detail]
                    message = "; ".join(str(v) for v in items)
                    refund_required = any(getattr(item, "code", "") == "refund_required" for item in items)
                return JsonResponse({
                    "ok": False, "message": message,
                    "refund_required": refund_required,
                }, status=422)
            _flash_drf_validation(request, exc)
        else:
            if async_qty:
                # Return current database values. Do not mask a failed
                # confirmation as a successful quantity change.
                order.refresh_from_db(fields=["subtotal", "tax_total", "total", "currency"])
                paid, due = order_payment_totals(order)
                return JsonResponse({
                    "ok": True, "line_id": str(adjusted.pk),
                    "quantity": str(adjusted.quantity),
                    "line_total": str(adjusted.line_total),
                    "subtotal": str(order.subtotal), "discount": str(order.discount_amount), "tax": str(order.tax_total),
                    "total": str(order.total), "paid": str(paid),
                    "due": str(due), "currency": order.currency,
                })
            messages.success(request, "Line updated.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_scan_add_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_scan = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        def reject(message, status=422):
            if async_scan:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if not _tenant_hardware_flags(order.tenant)["barcode_scanner_enabled"]:
            return reject("Barcode scanner input is disabled in workspace hardware settings.", 403)
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Barcode add is only available on supermarket or retail outlets.", 403)
        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject("Barcode add is only available for open, unpaid orders.", 409)
        form = StaffOrderScanAddForm(request.POST)
        if not form.is_valid():
            if async_scan:
                return reject("; ".join(str(error) for errors in form.errors.values() for error in errors))
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        group_code = (form.cleaned_data["code"] or "").strip()
        retail_group = RetailProductGroup.objects.filter(
            tenant_id=order.tenant_id,
            is_active=True,
            code__iexact=group_code,
        ).first()
        try:
            if retail_group is not None:
                add_retail_group_to_open_order(
                    order=order,
                    retail_group=retail_group,
                    quantity=form.cleaned_data["quantity"],
                    user=request.user,
                )
            else:
                add_supermarket_line_by_code(
                    order=order,
                    code=group_code,
                    quantity=form.cleaned_data["quantity"],
                    user=request.user,
                )
        except DRFValidationError as exc:
            if async_scan:
                return reject(exc.detail)
            _flash_drf_validation(request, exc)
        else:
            if async_scan:
                order.refresh_from_db(fields=["subtotal", "tax_total", "total", "currency"])
                return JsonResponse({"ok": True, "order_id": str(order.pk),
                    "currency": order.currency, "total": str(order.total)})
            messages.success(
                request,
                f"{retail_group.name} added." if retail_group is not None else "SKU added.",
            )
        return redirect("staff-order-detail", order_id=order.id)

    def _post_line_discount(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_discount = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def reject(message, status=422):
            if async_discount:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Line discount is only available on supermarket or retail outlets.", 409)
        approvers = sensitive_action_approvers(
            requester=request.tenant_membership,
            action="discount",
            outlet_id=order.outlet_id,
        )
        if not approvers:
            return reject("No PIN-enabled manager is available to approve this discount.", 409)
        form = StaffOrderLineDiscountForm(request.POST, approvers=approvers)
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, errors in form.errors.items()
                for error in errors
            ) or "Check the discount details."
            return reject(detail)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            return reject("That line is not on this order.", 404)
        try:
            request_key = self._sensitive_request_key(request, "discount_request_key")
            with transaction.atomic():
                locked_order = Order.objects.select_for_update().get(pk=order.pk)
                locked_line = OrderLine.objects.select_for_update().get(
                    pk=line.pk,
                    order_id=locked_order.pk,
                )
                approval = authorize_sensitive_action(
                    requester=request.tenant_membership,
                    approver_id=form.cleaned_data["approver_id"],
                    approver_pin=form.cleaned_data["approver_pin"],
                    action="discount",
                    entity_type="order",
                    entity_id=str(locked_order.pk),
                    request_key=request_key,
                    outlet_id=locked_order.outlet_id,
                    intent_payload={
                        "line_id": str(locked_line.pk),
                        "discount_amount": str(form.cleaned_data.get("discount_amount") or ""),
                        "discount_percent": str(form.cleaned_data.get("discount_percent") or ""),
                        "quantity": str(locked_line.quantity),
                        "unit_price": str(locked_line.unit_price),
                        "line_total_before": str(locked_line.line_total),
                    },
                )
                if not getattr(approval, "idempotent_replay", False):
                    apply_supermarket_line_discount(
                        order=locked_order,
                        line=locked_line,
                        user=request.user,
                        discount_amount=form.cleaned_data.get("discount_amount"),
                        discount_percent=form.cleaned_data.get("discount_percent"),
                    )
        except SensitiveApprovalError as exc:
            return reject(exc)
        except DRFValidationError as exc:
            return reject(exc.detail)
        if async_discount:
            order.refresh_from_db(fields=["subtotal", "discount_amount", "tax_total", "total", "currency"])
            return JsonResponse({
                "ok": True,
                "message": "Manager-approved line discount saved.",
                "order_id": str(order.pk),
                "currency": order.currency,
                "total": str(order.total),
                "next_request_key": str(uuid.uuid4()),
            })
        messages.success(request, "Manager-approved line discount saved.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_line_return(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_return = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def reject(message, status=422):
            if async_return:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Line return is only available on supermarket or retail outlets.", 409)
        form = StaffOrderLineReturnForm(request.POST)
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, errors in form.errors.items()
                for error in errors
            ) or "Check the physical return details."
            return reject(detail)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            return reject("That line is not on this order.", 404)
        raw_key = (request.POST.get("line_return_request_key") or "").strip()
        try:
            request_key = str(uuid.UUID(raw_key)) if raw_key else str(uuid.uuid4())
        except (TypeError, ValueError):
            return reject("Invalid physical return request identity.")
        try:
            returned = process_supermarket_line_return(
                order=order,
                line=line,
                quantity=form.cleaned_data["quantity"],
                reason=form.cleaned_data.get("reason") or "",
                restock=bool(form.cleaned_data.get("restock")),
                user=request.user,
                idempotency_key=request_key,
                serial_numbers=form.cleaned_data.get("serial_numbers") or "",
            )
        except DRFValidationError as exc:
            return reject(" ".join(_drf_detail_messages(exc.detail)))
        if async_return:
            return JsonResponse({
                "ok": True,
                "message": (
                    "Physical return already recorded."
                    if getattr(returned, "idempotent_replay", False)
                    else "Physical return recorded."
                ),
                "order_id": str(order.pk),
                "next_request_key": str(uuid.uuid4()),
            })
        messages.success(
            request,
            "Physical return already recorded."
            if getattr(returned, "idempotent_replay", False)
            else "Line return recorded.",
        )
        return redirect("staff-order-detail", order_id=order.id)

    def _post_retail_line_refund(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_refund = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def reject(message, status=422):
            if async_refund:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            return reject("Item refunds are only available for retail orders.", 409)
        approvers = sensitive_action_approvers(
            requester=request.tenant_membership,
            action="retail_line_refund",
            outlet_id=order.outlet_id,
        )
        if not approvers:
            return reject("No PIN-enabled manager is available to approve this refund.", 409)
        form = StaffRetailLineRefundForm(
            request.POST,
            lines=list(order.lines.all()),
            payments=list(order.payments.all()),
            max_refund=order_refundable_remaining(order),
            approvers=approvers,
        )
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, errors in form.errors.items()
                for error in errors
            ) or "Check the return and refund details."
            return reject(detail)
        line = order.lines.filter(id=form.cleaned_data["line_id"]).first()
        if line is None:
            return reject("That item is not on this order.", 404)
        payment_id = (
            uuid.UUID(form.cleaned_data["payment_id"])
            if "payment_id" in form.fields else None
        )
        reason = form.cleaned_data.get("reason") or ""
        restock = bool(form.cleaned_data.get("restock"))
        try:
            request_key = self._refund_request_key(request, "retail_refund_request_key")
            with transaction.atomic():
                approval = authorize_sensitive_action(
                    requester=request.tenant_membership,
                    approver_id=form.cleaned_data["approver_id"],
                    approver_pin=form.cleaned_data["approver_pin"],
                    action="retail_line_refund",
                    entity_type="order",
                    entity_id=str(order.pk),
                    request_key=request_key,
                    outlet_id=order.outlet_id,
                    intent_payload={
                        "line_id": str(line.pk),
                        "quantity": str(form.cleaned_data["quantity"]),
                        "amount": str(form.cleaned_data["amount"]),
                        "reason": reason,
                        "restock": restock,
                        "payment_id": str(payment_id or ""),
                    },
                )
                refund_retail_line(
                    order=order,
                    line=line,
                    quantity=form.cleaned_data["quantity"],
                    amount=form.cleaned_data["amount"],
                    reason=reason,
                    restock=restock,
                    user=request.user,
                    idempotency_key=request_key,
                    workstation_id=settlement_workstation_id(request, outlet=order.outlet),
                    payment_id=payment_id,
                    serial_numbers=form.cleaned_data.get("serial_numbers") or "",
                )
        except SensitiveApprovalError as exc:
            return reject(exc)
        except DRFValidationError as exc:
            return reject(exc.detail)
        if async_refund:
            return JsonResponse({
                "ok": True,
                "message": "Manager-approved item return and customer refund recorded.",
                "order_id": str(order.pk),
                "next_request_key": str(uuid.uuid4()),
            })
        messages.success(request, "Manager-approved item return and customer refund recorded.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_resume_order(self, request: HttpRequest, order: Order) -> HttpResponse:
        # get_object() has already enforced tenant and outlet scope, and the
        # POST permission gate covers the selected register's cashier role.
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            messages.error(request, "This resume action is only for retail baskets.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            resume_held_retail_order(order=order, user=request.user)
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
            return redirect("staff-orders")
        messages.success(request, "Original basket resumed. Payments and balance were preserved.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_hold_order(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Only open, unpaid orders can be put on hold.")
            return redirect("staff-order-detail", order_id=order.id)
        hold_data = request.POST.copy()
        if (order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
                and not (hold_data.get("hold_label") or "").strip()):
            # Retail tills handle queues; a basket reference is sufficient.
            # Hospitality retains its required explicit table/guest label.
            hold_data["hold_label"] = "Held " + order.bill_reference
        form = StaffOrderHoldForm(hold_data)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            hold_open_order(
                order=order,
                hold_label=form.cleaned_data["hold_label"],
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
                from .views_customer_display import clear_customer_display_active
                clear_customer_display_active(order, request)
            if order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
                messages.success(request, "Basket held. Start serving the next customer; retrieve it from Held sales when they return.")
                return redirect("staff-retail-pos-entry")
            messages.success(request, "Order put on hold.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_void_order(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Only open, unpaid orders can be voided.")
            return redirect("staff-order-detail", order_id=order.id)

        is_retail = order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        approvers = (
            sensitive_action_approvers(
                requester=request.tenant_membership,
                action="void",
                outlet_id=order.outlet_id,
            )
            if is_retail else None
        )
        if is_retail and not approvers:
            messages.error(request, "A different PIN-enabled manager is required to approve this basket void.")
            return redirect("staff-order-detail", order_id=order.id)

        form = StaffOrderVoidOrderForm(request.POST, approvers=approvers)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)

        reason = form.cleaned_data.get("reason") or ""
        try:
            if is_retail:
                request_key = self._sensitive_request_key(request, "void_request_key")
                with transaction.atomic():
                    locked_order = Order.objects.select_for_update().get(
                        pk=order.pk,
                        tenant_id=order.tenant_id,
                        outlet_id=order.outlet_id,
                    )
                    approval = authorize_sensitive_action(
                        requester=request.tenant_membership,
                        approver_id=form.cleaned_data["approver_id"],
                        approver_pin=form.cleaned_data["approver_pin"],
                        action="void",
                        entity_type="order",
                        entity_id=str(locked_order.pk),
                        request_key=request_key,
                        outlet_id=locked_order.outlet_id,
                        intent_payload={
                            "reason": reason,
                            "subtotal": str(locked_order.subtotal),
                            "discount_amount": str(locked_order.discount_amount),
                            "tax_total": str(locked_order.tax_total),
                            "total": str(locked_order.total),
                            "active_line_count": locked_order.lines.filter(is_voided=False).count(),
                        },
                    )
                    if not getattr(approval, "idempotent_replay", False):
                        cancel_open_unpaid_order(
                            order=locked_order,
                            user=request.user,
                            reason=reason,
                        )
            else:
                cancel_open_unpaid_order(
                    order=order,
                    user=request.user,
                    reason=reason,
                )
        except SensitiveApprovalError as exc:
            messages.error(request, str(exc))
        except DRFValidationError as exc:
            if getattr(exc, "get_codes", None) and _drf_has_code(exc.get_codes(), "refund_required"):
                for message in _drf_detail_messages(exc.detail):
                    messages.error(request, message)
                messages.info(request, "Use the authorized refund controls below, then cancel this basket again.")
            else:
                _flash_drf_validation(request, exc)
        else:
            if is_retail:
                from .views_customer_display import clear_customer_display_active
                clear_customer_display_active(order, request)
                messages.success(request, "Manager-approved basket void recorded. Ready for the next sale.")
                return redirect("staff-retail-pos-entry")
            messages.success(request, "Order voided.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_apply_promotion(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_retail = (
            order.outlet.outlet_type in {
                OutletType.SUPERMARKET, OutletType.RETAIL,
                OutletType.RESTAURANT, OutletType.BAR,
                OutletType.LOUNGE, OutletType.CAFETERIA,
            }
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message: str, *, status: int = 422) -> HttpResponse:
            if async_retail:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject(
                "Offers can only be applied to open orders that are not yet paid.",
                status=409,
            )
        promo_qs = promotions_selectable_for_order(order)
        form = StaffOrderApplyPromotionForm(request.POST, eligible_queryset=promo_qs)
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, error_list in form.errors.items()
                for error in error_list
            ) or "Check the offer details."
            return reject(detail)
        try:
            changed = apply_promotion_to_order(
                order=order,
                promotion=form.cleaned_data["promotion"],
                user=request.user,
            )
        except DRFValidationError as exc:
            return reject(" ".join(_drf_detail_messages(exc.detail)))
        if async_retail:
            return JsonResponse({
                "ok": True,
                "message": "Offer applied.",
                "order_id": str(changed.pk),
                "currency": changed.currency,
                "subtotal": str(changed.subtotal),
                "discount": str(changed.discount_amount),
                "tax": str(changed.tax_total),
                "total": str(changed.total),
            })
        messages.success(request, "Promotion applied.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_void_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        async_void = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and order.outlet.outlet_type in {
                OutletType.RETAIL,
                OutletType.SUPERMARKET,
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
        )

        def reject(message, status=422, *, refund_required=False):
            if async_void:
                return JsonResponse({
                    "ok": False,
                    "message": str(message),
                    "refund_required": refund_required,
                }, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if order.status != OrderStatus.OPEN or order.is_paid:
            return reject(
                "Lines can only be voided on open orders that are not yet paid.",
                409,
            )
        form = StaffOrderVoidLineForm(request.POST)
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, errors in form.errors.items()
                for error in errors
            ) or "Check the item removal details."
            return reject(detail)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            return reject("That line is not on this order.", 404)
        try:
            void_open_order_line(
                order=order,
                line=line,
                reason=form.cleaned_data.get("reason") or "",
                user=request.user,
            )
        except DRFValidationError as exc:
            refund_required = bool(
                getattr(exc, "get_codes", None)
                and _drf_has_code(exc.get_codes(), "refund_required")
            )
            return reject(
                " ".join(_drf_detail_messages(exc.detail)),
                409 if refund_required else 422,
                refund_required=refund_required,
            )
        if async_void:
            order.refresh_from_db(
                fields=["subtotal", "discount_amount", "tax_total", "total", "currency"]
            )
            return JsonResponse({
                "ok": True,
                "message": "Item voided.",
                "order_id": str(order.pk),
                "currency": order.currency,
                "total": str(order.total),
            })
        messages.success(request, "Line voided.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_record_refund(self, request: HttpRequest, order: Order) -> HttpResponse:
        is_retail = order.outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}
        async_refund = (
            is_retail
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        def reject(message, status=422):
            if async_refund:
                return JsonResponse({"ok": False, "message": str(message)}, status=status)
            messages.error(request, str(message))
            return redirect("staff-order-detail", order_id=order.id)

        if not is_retail and not membership_can_approve_refunds(request.tenant_membership):
            return reject("Refunds require approval by a supervisor or manager.", 403)
        partial_retail = (
            order.status == OrderStatus.OPEN and not order.is_paid and is_retail
        )
        if not ((order.status == OrderStatus.CLOSED and order.is_paid) or partial_retail):
            return reject("Refunds require a paid sale or a partially paid retail basket.", 409)
        pays = list(order.payments.order_by("created_at"))
        refundable = order_refundable_remaining(order)
        if refundable <= Decimal("0"):
            return reject("Nothing left to refund on this order.", 409)
        approvers = (
            sensitive_action_approvers(
                requester=request.tenant_membership,
                action="refund",
                outlet_id=order.outlet_id,
            )
            if is_retail else None
        )
        if is_retail and not approvers:
            return reject("No PIN-enabled manager is available to approve this refund.", 409)
        form = StaffOrderRefundForm(
            request.POST,
            payments=pays,
            max_refund=refundable,
            approvers=approvers,
        )
        if not form.is_valid():
            detail = "; ".join(
                f"{field}: {error}"
                for field, errors in form.errors.items()
                for error in errors
            ) or "Check the refund details."
            return reject(detail)
        payment_id = None
        if "payment_id" in form.fields:
            payment_id = uuid.UUID(form.cleaned_data["payment_id"])
        reason = form.cleaned_data.get("reason") or ""
        restock = bool(form.cleaned_data.get("restock")) and not partial_retail
        try:
            request_key = self._refund_request_key(request)
            if is_retail:
                with transaction.atomic():
                    authorize_sensitive_action(
                        requester=request.tenant_membership,
                        approver_id=form.cleaned_data["approver_id"],
                        approver_pin=form.cleaned_data["approver_pin"],
                        action="refund",
                        entity_type="order",
                        entity_id=str(order.pk),
                        request_key=request_key,
                        outlet_id=order.outlet_id,
                        intent_payload={
                            "amount": str(form.cleaned_data["amount"]),
                            "reason": reason,
                            "restock": restock,
                            "payment_id": str(payment_id or ""),
                        },
                    )
                    record_order_refund(
                        order=order,
                        user=request.user,
                        amount=form.cleaned_data["amount"],
                        reason=reason,
                        idempotency_key=request_key,
                        workstation_id=settlement_workstation_id(request, outlet=order.outlet),
                        restock=restock,
                        payment_id=payment_id,
                    )
            else:
                record_order_refund(
                    order=order,
                    user=request.user,
                    amount=form.cleaned_data["amount"],
                    reason=reason,
                    idempotency_key=request_key,
                    workstation_id=settlement_workstation_id(request, outlet=order.outlet),
                    restock=restock,
                    payment_id=payment_id,
                )
        except SensitiveApprovalError as exc:
            return reject(exc)
        except DRFValidationError as exc:
            return reject(exc.detail)
        if async_refund:
            return JsonResponse({
                "ok": True,
                "message": "Manager-approved refund recorded.",
                "order_id": str(order.pk),
                "next_request_key": str(uuid.uuid4()),
            })
        messages.success(
            request,
            "Manager-approved refund recorded." if is_retail else "Refund recorded.",
        )
        return redirect("staff-order-detail", order_id=order.id)


def _repair_empty_retail_currency(order: Order) -> bool:
    """Correct a legacy *empty* retail basket, never monetary history."""
    configured = default_currency_for_tenant(order.tenant)
    if (order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}
            or order.currency == configured or order.status != OrderStatus.OPEN
            or order.is_paid):
        return False
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if (locked.status != OrderStatus.OPEN or locked.is_paid
                or locked.currency == configured or locked.subtotal != Decimal("0")
                or locked.tax_total != Decimal("0") or locked.total != Decimal("0")
                or locked.discount_amount != Decimal("0")
                or locked.lines.exists() or locked.payments.exists()
                or locked.refunds.exists()):
            return False
        Order.objects.filter(pk=locked.pk).update(currency=configured)
        return True


class StaffOrderPrintView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "orders"
    template_name = "staff/order_print.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if _repair_empty_retail_currency(self.object):
            self.object.refresh_from_db(fields=["currency"])
        return self.render_to_response(self.get_context_data(object=self.object))

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not getattr(request, "tenant", None):
            return super().dispatch(request, *args, **kwargs)
        from apps.staff.services.membership import staff_accessible_outlets
        from apps.staff.services.modules import get_tenant_staff_modules

        if (
            not getattr(request, "tenant_membership", None)
            or "pos" not in get_tenant_staff_modules(request.tenant)
            or not staff_accessible_outlets(request.tenant_membership)
        ):
            messages.error(request, "Point of sale is not available for your role or workspace setup.")
            return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        allowed_outlet_ids = [outlet.pk for outlet in staff_accessible_outlets(self.request.tenant_membership)]
        if not allowed_outlet_ids or "pos" not in get_tenant_staff_modules(self.request.tenant):
            return Order.objects.none()
        return (
            Order.objects.filter(tenant=self.request.tenant, outlet_id__in=allowed_outlet_ids)
            .select_related("outlet", "table", "folio", "created_by")
            .prefetch_related(
                "lines",
                "payments",
                "refunds",
                "refunds__payment",
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order: Order = ctx["order"]
        amount_paid, balance_due = order_payment_totals(order)
        document_type = _normalize_print_document(self.request.GET.get("type", "receipt"))
        paper_format = _normalize_print_format(self.request.GET.get("format", "80mm"))
        is_receipt = document_type == "receipt"
        payment_entries = list(order.payments.all())
        refund_entries = list(order.refunds.all())
        if paper_format == "50mm":
            paper_width = "50mm"
            page_size = "50mm auto"
            page_margin = "4mm"
            body_padding = "4mm"
            font_size = "10px"
            headline_size = "15px"
            a4_only_display = "none"
        elif paper_format == "a4":
            paper_width = "210mm"
            page_size = "A4 portrait"
            page_margin = "10mm"
            body_padding = "14mm"
            font_size = "12px"
            headline_size = "24px"
            a4_only_display = "block"
        else:
            paper_width = "80mm"
            page_size = "80mm auto"
            page_margin = "5mm"
            body_padding = "6mm"
            font_size = "12px"
            headline_size = "18px"
            a4_only_display = "none"
        ctx["document_type"] = document_type
        ctx["document_title"] = "Receipt" if is_receipt else "Bill"
        ctx["paper_format"] = paper_format
        ctx["paper_width_label"] = paper_format.upper() if paper_format == "a4" else paper_format
        ctx["paper_width"] = paper_width
        ctx["page_size"] = page_size
        ctx["page_margin"] = page_margin
        ctx["body_padding"] = body_padding
        ctx["font_size"] = font_size
        ctx["headline_size"] = headline_size
        ctx["a4_only_display"] = a4_only_display
        ctx["is_receipt"] = is_receipt
        ctx["amount_paid"] = amount_paid
        ctx["balance_due"] = balance_due
        ctx["payment_entries"] = payment_entries
        ctx["refund_entries"] = refund_entries
        ctx["show_payment_history"] = is_receipt and bool(payment_entries)
        ctx["show_refund_history"] = bool(refund_entries)
        ctx["printed_at"] = timezone.localtime()
        return ctx


class StaffTablesListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "tables"
    template_name = "staff/tables_list.html"
    context_object_name = "tables"

    def _scope(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        return outlets, resolve_staff_outlet(self.request, outlets)

    def get_queryset(self):
        if "pos" not in get_tenant_staff_modules(self.request.tenant):
            return Table.objects.none()
        _, outlet = self._scope()
        if outlet is None:
            return Table.objects.none()
        qs = Table.objects.filter(outlet=outlet).select_related("outlet", "outlet__site")
        if self.request.GET.get("include_inactive") != "1":
            qs = qs.filter(is_active=True)
        return qs.order_by("sort_order", "label")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets, outlet = self._scope()
        ctx["outlets"] = outlets
        ctx["current_outlet"] = outlet
        membership = self.request.tenant_membership
        ctx["can_modify_tables"] = membership_can_modify_lodging(membership)
        ctx["include_inactive"] = self.request.GET.get("include_inactive") == "1"
        ctx["hospitality_floor"] = bool(
            outlet and outlet.outlet_type in {
                OutletType.RESTAURANT,
                OutletType.BAR,
                OutletType.LOUNGE,
                OutletType.CAFETERIA,
            }
        )
        ctx["floor_business_label"] = (
            outlet.get_outlet_type_display() if outlet else "Hospitality"
        )
        ctx["can_operate_tables"] = bool(
            ctx["hospitality_floor"]
            and membership.is_active
            and membership.role in {
                MembershipRole.OWNER,
                MembershipRole.TENANT_ADMIN,
                MembershipRole.SITE_MANAGER,
                MembershipRole.OUTLET_MANAGER,
                MembershipRole.SERVER,
                MembershipRole.BARTENDER,
            }
        )

        tables = list(ctx["tables"])
        ctx["tables"] = tables
        if not tables or not outlet:
            return ctx
        table_ids = [table.pk for table in tables]
        live_orders = list(
            Order.objects.filter(
                tenant=self.request.tenant,
                outlet=outlet,
                table_id__in=table_ids,
                status=OrderStatus.OPEN,
            )
            .select_related("created_by")
            .order_by("created_at")
        )
        by_table = {}
        counts = {}
        for order in live_orders:
            counts[order.table_id] = counts.get(order.table_id, 0) + 1
            by_table.setdefault(order.table_id, order)
        manager = membership.role in {
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
            MembershipRole.SITE_MANAGER,
            MembershipRole.OUTLET_MANAGER,
        }
        for table in tables:
            table.active_order = by_table.get(table.pk)
            table.active_order_count = counts.get(table.pk, 0)
            table.can_resume_order = bool(
                table.active_order
                and ctx["can_operate_tables"]
                and (
                    manager
                    or table.active_order.created_by_id == self.request.user.pk
                )
            )
        ctx["available_transfer_table_count"] = sum(
            1 for table in tables if table.is_active and not table.active_order
        )
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if "pos" not in get_tenant_staff_modules(request.tenant):
            messages.error(request, "Point of sale is not enabled for this workspace.")
            return redirect("staff-dashboard")
        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        if outlet is None:
            messages.error(request, "Select one hospitality section before opening a table.")
            return redirect("staff-tables")
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "open_table":
                table_id = uuid.UUID((request.POST.get("table_id") or "").strip())
                raw_guests = (request.POST.get("guest_count") or "").strip()
                guest_count = int(raw_guests) if raw_guests else None
                order, replay = open_or_resume_table_order(
                    tenant_id=request.tenant.pk,
                    outlet=outlet,
                    table_id=table_id,
                    membership=request.tenant_membership,
                    user=request.user,
                    guest_count=guest_count,
                )
                if replay:
                    messages.info(request, f"Resuming {order.table_label or 'table'} check.")
                else:
                    messages.success(request, f"{order.table_label or 'Table'} check opened.")
            elif action == "transfer_table":
                order_id = uuid.UUID((request.POST.get("order_id") or "").strip())
                target_table_id = uuid.UUID((request.POST.get("target_table_id") or "").strip())
                order = transfer_table_order(
                    tenant_id=request.tenant.pk,
                    outlet=outlet,
                    order_id=order_id,
                    target_table_id=target_table_id,
                    membership=request.tenant_membership,
                    user=request.user,
                )
                messages.success(request, f"Check moved to {order.table_label}.")
                return redirect("staff-tables")
            else:
                messages.error(request, "Unknown table action.")
                return redirect("staff-tables")
        except (ValueError, AttributeError):
            messages.error(request, "Choose a valid table and guest count.")
            return redirect("staff-tables")
        except DRFValidationError as exc:
            for message in _drf_detail_messages(exc.detail):
                messages.error(request, message)
            return redirect("staff-tables")
        return redirect("staff-order-detail", order_id=order.pk)


class StaffTableCreateView(StaffTenantRequiredMixin, CreateView):
    staff_nav_capability = "tables"
    model = Table
    form_class = StaffTableForm
    template_name = "staff/table_form.html"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot manage tables.")
            return redirect("staff-tables")
        outlets = staff_accessible_outlets(request.tenant_membership)
        self._current_outlet = resolve_staff_outlet(request, outlets)
        if self._current_outlet is None:
            messages.info(request, "Select a single outlet in the header (not “All outlets”) to add a table.")
            return redirect("staff-tables")
        if not staff_outlet_allowed_for_membership(request.tenant_membership, self._current_outlet.id):
            messages.error(request, "You cannot manage tables for this outlet.")
            return redirect("staff-tables")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["outlet"] = self._current_outlet
        return kw

    def form_valid(self, form):
        form.instance.outlet = self._current_outlet
        messages.success(self.request, "Table created.")
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("staff-tables")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "New table"
        ctx["current_outlet"] = self._current_outlet
        return ctx


class StaffTableUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "tables"
    model = Table
    form_class = StaffTableForm
    template_name = "staff/table_form.html"
    pk_url_kwarg = "table_id"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot manage tables.")
            return redirect("staff-tables")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        oids = [o.id for o in staff_accessible_outlets(self.request.tenant_membership)]
        return (
            Table.objects.filter(outlet_id__in=oids)
            .filter(outlet__site__tenant_id=self.request.tenant.id)
            .select_related("outlet", "outlet__site")
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["outlet"] = self.object.outlet
        return kw

    def form_valid(self, form):
        messages.success(self.request, "Table updated.")
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse("staff-tables")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit table"
        ctx["current_outlet"] = self.object.outlet
        return ctx


class StaffMenuListView(StaffTenantRequiredMixin, ListView):
    """Categories (each row is a category with prefetched items)."""

    staff_nav_capability = "menu"
    template_name = "staff/menu_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        tenant_id = self.request.tenant.id
        if "pos" not in get_tenant_staff_modules(self.request.tenant):
            return MenuCategory.objects.none()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        all_outlets = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL

        if outlet and not all_outlets:
            allowed_ids = menu_items_for_outlet_queryset(tenant_id, outlet.id).values_list("pk", flat=True)
            item_qs = MenuItem.objects.filter(pk__in=allowed_ids, is_active=True).order_by("name")
        elif all_outlets and outlets:
            allowed_ids = set()
            for allowed_outlet in outlets:
                allowed_ids.update(menu_items_for_outlet_queryset(tenant_id, allowed_outlet.id).values_list("pk", flat=True))
            item_qs = MenuItem.objects.filter(pk__in=allowed_ids, is_active=True).order_by("name")
        else:
            item_qs = MenuItem.objects.none()

        if self.request.GET.get("review") == "quick":
            item_qs = item_qs.filter(
                category__name="Needs catalogue review",
                sku__startswith="QUICK-",
            )
        query = self.request.GET.get("q", "").strip()[:80]
        if query:
            item_qs = item_qs.filter(
                Q(name__icontains=query) | Q(sku__icontains=query)
                | Q(barcode__icontains=query)
                | Q(supermarket_profile__plu_code__icontains=query,
                    supermarket_profile__tenant_id=tenant_id,
                    supermarket_profile__is_active=True)
            )
        return (
            MenuCategory.objects.filter(tenant=self.request.tenant, is_active=True)
            .filter(items__in=item_qs)
            .prefetch_related(Prefetch("items", queryset=item_qs))
            .order_by("sort_order", "name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        ctx["menu_scope_outlet"] = outlet
        ctx["menu_all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_manage_tv_details"] = membership_can_manage_workspace_settings(self.request.tenant_membership)
        ctx["menu_search_q"] = self.request.GET.get("q", "").strip()[:80]
        quick_review_qs = MenuItem.objects.filter(
            tenant_id=self.request.tenant.id,
            category__name="Needs catalogue review",
            sku__startswith="QUICK-",
            is_active=True,
        )
        if outlet:
            quick_review_qs = quick_review_qs.filter(
                pk__in=menu_items_for_outlet_queryset(
                    self.request.tenant.id, outlet.id
                ).values("pk")
            )
        elif outlets and ctx["menu_all_outlets_mode"]:
            allowed_q = Q(pk__in=[])
            for authorized_outlet in outlets:
                allowed_q |= Q(pk__in=menu_items_for_outlet_queryset(
                    self.request.tenant.id, authorized_outlet.id
                ).values("pk"))
            quick_review_qs = quick_review_qs.filter(allowed_q)
        else:
            quick_review_qs = quick_review_qs.none()
        ctx["quick_review_count"] = quick_review_qs.count()
        ctx["quick_review_filter"] = self.request.GET.get("review") == "quick"
        # A supermarket staff member in an all-register view needs the same
        # product catalogue as when a single store register is selected.
        retail_types = {OutletType.SUPERMARKET, OutletType.RETAIL}
        ctx["show_retail_catalogue"] = (
            outlet.outlet_type in retail_types
            if outlet is not None
            else bool(outlets) and all(item.outlet_type in retail_types for item in outlets)
        )
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        from django.core.exceptions import ValidationError
        from .services import membership_can_manage_workspace_settings

        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(request, "Your role cannot edit menu display details.")
            return redirect("staff-menu")

        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        if not outlet or request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
            messages.error(request, "Select one outlet before editing display information.")
            return redirect("staff-menu")
        try:
            item_id = uuid.UUID(request.POST.get("item_id", ""))
        except (ValueError, TypeError):
            messages.error(request, "Select a valid menu item.")
            return redirect("staff-menu")
        item = MenuItem.objects.filter(
            pk=item_id,
            tenant=request.tenant,
            is_active=True,
            pk__in=menu_items_for_outlet_queryset(request.tenant.id, outlet.id).values("pk"),
        ).first()
        if item is None:
            messages.error(request, "That item is not available at this outlet.")
            return redirect("staff-menu")
        if request.POST.get("action") != "display_details":
            messages.error(request, "Unsupported catalog action.")
            return redirect("staff-menu")
        item.is_featured = request.POST.get("is_featured") == "on"
        item.display_image_url = (request.POST.get("display_image_url") or "").strip()
        item.availability_note = (request.POST.get("availability_note") or "").strip()[:160]
        try:
            item.full_clean(exclude=["tenant", "category", "unit_price"])
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("staff-menu")
        item.save(update_fields=["is_featured", "display_image_url", "availability_note", "updated_at"])
        messages.success(request, f"Display details saved for {item.name}.")
        return redirect("staff-menu")


class StaffSalesSummaryView(StaffTenantRequiredMixin, TemplateView):
    def _business_report_site(self, request):
        """Return a property only when operating-date reporting has a single property."""
        if request.GET.get("date_basis") != "business":
            return None, None
        outlets = staff_accessible_outlets(request.tenant_membership)
        current = resolve_staff_outlet(request, outlets)
        chosen = (outlets if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
                  else ([current] if current else []))
        site_ids = {o.site_id for o in chosen}
        if len(site_ids) != 1:
            return None, "Operating-date reports need exactly one property. Select a section or property."
        from apps.tenants.models import Site
        return Site.objects.get(pk=next(iter(site_ids)), tenant=request.tenant), None

    staff_nav_capability = "sales"
    template_name = "staff/sales_summary.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if (request.GET.get("format") or "").strip().lower() == "csv":
            return self._csv_response(request)
        return super().get(request, *args, **kwargs)

    def _csv_response(self, request: HttpRequest) -> HttpResponse:
        today = date.today()
        d0 = parse_date(request.GET.get("date_from") or "") or (today - timedelta(days=7))
        d1 = parse_date(request.GET.get("date_to") or "") or today
        if d0 > d1:
            return HttpResponse("Start date must be on or before end date.", status=400, content_type="text/plain")

        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        all_outlets_mode = request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        oid = None if all_outlets_mode else (outlet.id if outlet else None)
        business_site, warning = self._business_report_site(request)
        if warning:
            return HttpResponse(warning, status=400, content_type="text/plain")
        body = format_sales_summary_csv(
            request.tenant.id, d0, d1, oid,
            allowed_outlet_ids=[o.pk for o in outlets],
            business_date_site=business_site,
        )

        resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="sales-summary-{d0.isoformat()}_{d1.isoformat()}.csv"'
        )
        return resp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        d0 = parse_date(self.request.GET.get("date_from") or "") or (today - timedelta(days=7))
        d1 = parse_date(self.request.GET.get("date_to") or "") or today

        ctx["date_from"] = d0
        ctx["date_to"] = d1
        ctx["date_errors"] = []
        ctx["date_basis"] = self.request.GET.get("date_basis", "calendar")
        business_site, warning = self._business_report_site(self.request)
        if warning:
            ctx["date_errors"].append(warning)
        ctx["business_date_property"] = business_site

        if d0 > d1:
            ctx["date_errors"].append("Start date must be on or before end date.")

        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        ctx["outlets"] = outlets
        ctx["current_outlet"] = outlet
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL

        if ctx["date_errors"]:
            ctx["summary"] = None
            return ctx

        oid = None if ctx["all_outlets_mode"] else (outlet.id if outlet else None)
        ctx["summary"] = build_sales_summary(
            self.request.tenant.id, d0, d1, oid,
            allowed_outlet_ids=[o.pk for o in outlets],
            business_date_site=business_site,
        )
        return ctx
