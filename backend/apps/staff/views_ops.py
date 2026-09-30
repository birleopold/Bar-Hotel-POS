from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from django.db.models import Prefetch, Q

from apps.catalog.models import MenuItemModifierGroup, ModifierOption
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.catalog.models import MenuCategory, MenuItem, ServiceOffering, ServiceOfferingOption
from apps.pos.models import KdsLineStatus, Order, OrderLine, OrderStatus, PosShift, PosShiftStatus, Table
from apps.pos.services import (
    adjust_open_order_line_quantity,
    add_line_to_open_order,
    add_service_to_open_order,
    add_supermarket_line_by_code,
    apply_promotion_to_order,
    apply_supermarket_line_discount,
    cancel_open_unpaid_order,
    charge_order_to_folio,
    close_pos_shift,
    create_order_with_lines,
    default_currency_for_tenant,
    hold_open_order,
    menu_items_for_outlet_queryset,
    open_pos_shift,
    process_supermarket_line_return,
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
    StaffPosShiftCloseForm,
    StaffPosShiftOpenForm,
    StaffTableForm,
)
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
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
    resolve_staff_outlet,
    staff_accessible_outlets,
    staff_outlet_allowed_for_membership,
)


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    d = exc.detail
    if isinstance(d, dict):
        for key, val in d.items():
            parts = val if isinstance(val, list) else [val]
            for p in parts:
                messages.error(request, f"{key}: {str(p)}")
    else:
        messages.error(request, str(d))


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
        outlets = staff_accessible_outlets(m)
        oid = request.POST.get("outlet_id", "").strip()
        nxt = request.POST.get("next", "").strip() or reverse("staff-orders")
        if oid == "__all__":
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

    def get_queryset(self):
        qs = (
            Order.objects.filter(tenant=self.request.tenant)
            .select_related("outlet", "table")
            .prefetch_related("payments")
            .order_by("-created_at")
        )
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        filter_all = self.request.session.get(STAFF_SESSION_OUTLET_KEY) is None and self.request.GET.get(
            "all_outlets"
        )
        if outlet and not filter_all:
            qs = qs.filter(outlet=outlet)
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
        ctx["q_filter"] = (self.request.GET.get("q") or "").strip()
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        orders = list(ctx.get("object_list", []))
        attach_order_payment_display(orders)
        quick_qs = self.get_queryset()
        held_tabs = list(
            quick_qs.filter(status=OrderStatus.OPEN, is_paid=False)
            .exclude(table_label="")
            .order_by("-updated_at")[:12]
        )
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
        if outlet is not None and outlet.outlet_type in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            supermarket_lane = True
            shift_open = PosShift.objects.filter(
                tenant=self.request.tenant,
                outlet=outlet,
                status=PosShiftStatus.OPEN,
            ).first()
        ctx["show_supermarket_lane"] = supermarket_lane
        ctx["supermarket_shift_open"] = shift_open
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get("fragment") == "lanes":
            return render(self.request, "staff/includes/orders_lanes.html", context)
        return super().render_to_response(context, **response_kwargs)


class StaffOrderQuickCreateView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"

    def _quick_create(self, request: HttpRequest, *, mode: str, hold_label: str) -> HttpResponse:
        outlets = staff_accessible_outlets(request.tenant_membership)
        outlet = resolve_staff_outlet(request, outlets)
        if outlet is None:
            messages.error(request, "Select one outlet in the header to create an order.")
            return redirect("staff-orders")
        if not staff_outlet_allowed_for_membership(request.tenant_membership, outlet.id):
            messages.error(request, "You cannot create orders for this outlet.")
            return redirect("staff-orders")
        label = ""
        if mode == "hold":
            label = (hold_label or "").strip()
            if not label:
                label = f"HOLD {timezone.localtime().strftime('%H:%M')}"
        order = create_order_with_lines(
            tenant_id=request.tenant.id,
            outlet=outlet,
            created_by=request.user,
            currency=default_currency_for_tenant(request.tenant),
            table_label=label,
            lines=[],
        )
        messages.success(request, "New order started.")
        return redirect("staff-order-detail", order_id=order.id)

    def get(self, request: HttpRequest) -> HttpResponse:
        # Links (dashboard, workbench) use GET; forms on orders list use POST.
        mode = (request.GET.get("mode") or "walkin").strip() or "walkin"
        hold_label = (request.GET.get("hold_label") or "").strip()
        return self._quick_create(request, mode=mode, hold_label=hold_label)

    def post(self, request: HttpRequest) -> HttpResponse:
        mode = (request.POST.get("mode") or "").strip()
        hold_label = (request.POST.get("hold_label") or "").strip()
        return self._quick_create(request, mode=mode, hold_label=hold_label)


class StaffPosShiftListView(StaffTenantRequiredMixin, TemplateView):
    staff_nav_capability = "orders"
    template_name = "staff/pos_shifts.html"

    def _resolve_outlet(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        return resolve_staff_outlet(self.request, outlets), outlets

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlet, outlets = self._resolve_outlet()
        ctx["outlets"] = outlets
        ctx["current_outlet"] = outlet
        ctx["open_form"] = StaffPosShiftOpenForm()
        ctx["close_form"] = StaffPosShiftCloseForm()
        if outlet is None:
            ctx["open_shift"] = None
            ctx["recent_shifts"] = []
            return ctx
        ctx["open_shift"] = PosShift.objects.filter(
            tenant=self.request.tenant,
            outlet=outlet,
            status=PosShiftStatus.OPEN,
        ).first()
        ctx["recent_shifts"] = list(
            PosShift.objects.filter(tenant=self.request.tenant, outlet=outlet).order_by("-opened_at")[:20]
        )
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        outlet, _ = self._resolve_outlet()
        if outlet is None:
            messages.error(request, "Select one outlet to manage shifts.")
            return redirect("staff-pos-shifts")
        action = (request.POST.get("action") or "").strip()
        if action == "open_shift":
            form = StaffPosShiftOpenForm(request.POST)
            if not form.is_valid():
                for fld, err_list in form.errors.items():
                    for err in err_list:
                        messages.error(request, f"{fld}: {err}")
                return redirect("staff-pos-shifts")
            try:
                open_pos_shift(
                    tenant_id=request.tenant.id,
                    outlet=outlet,
                    user=request.user,
                    opening_cash=form.cleaned_data["opening_cash"],
                    note=form.cleaned_data.get("note") or "",
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Shift opened.")
            return redirect("staff-pos-shifts")
        if action == "close_shift":
            form = StaffPosShiftCloseForm(request.POST)
            if not form.is_valid():
                for fld, err_list in form.errors.items():
                    for err in err_list:
                        messages.error(request, f"{fld}: {err}")
                return redirect("staff-pos-shifts")
            shift = PosShift.objects.filter(
                id=form.cleaned_data["shift_id"],
                tenant=request.tenant,
                outlet=outlet,
            ).first()
            if shift is None:
                messages.error(request, "Shift not found.")
                return redirect("staff-pos-shifts")
            try:
                close_pos_shift(
                    shift=shift,
                    user=request.user,
                    counted_cash=form.cleaned_data["counted_cash"],
                    note=form.cleaned_data.get("note") or "",
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Shift closed.")
            return redirect("staff-pos-shifts")
        messages.error(request, "Unknown shift action.")
        return redirect("staff-pos-shifts")


class StaffOrderDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "orders"
    template_name = "staff/order_detail.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            Order.objects.filter(tenant=self.request.tenant)
            .select_related("outlet", "table", "folio", "applied_promotion")
            .prefetch_related(
                "lines",
                "lines__menu_item",
                "payments",
                "refunds",
                "refunds__payment",
            )
        )

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
        p, b = order_payment_totals(order)
        ctx["amount_paid"] = p
        ctx["balance_due"] = b
        can_pay = (
            membership_can_modify_lodging(self.request.tenant_membership)
            and staff_outlet_allowed_for_membership(self.request.tenant_membership, order.outlet_id)
            and order.status == OrderStatus.OPEN
            and not order.is_paid
            and b > Decimal("0")
        )
        ctx["can_record_payment"] = can_pay
        ctx["payment_form"] = StaffOrderPaymentForm(initial={"amount": b}) if can_pay else None
        m = self.request.tenant_membership
        can_modify_open = (
            membership_can_modify_lodging(m)
            and staff_outlet_allowed_for_membership(m, order.outlet_id)
            and order.status == OrderStatus.OPEN
            and not order.is_paid
        )
        ctx["can_modify_open_order"] = can_modify_open

        # Folio attach/clear (only for open, unpaid orders).
        ctx["can_set_folio"] = can_modify_open
        ctx["can_charge_to_folio"] = can_modify_open and order.folio_id is not None and b > Decimal("0")
        ctx["folio_form"] = None
        ctx["folio_choices"] = []
        if can_modify_open:
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
        can_ack_handoff = (
            staff_outlet_allowed_for_membership(m, order.outlet_id)
            and order.status == OrderStatus.OPEN
            and not order.is_paid
            and membership_can_acknowledge_ready_handoff(m, is_assigned_server=assigned_server)
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
        ctx["add_line_form"] = (
            StaffOrderAddLineForm(tenant_id=order.tenant_id, outlet_id=order.outlet_id)
            if can_modify_open
            else None
        )
        ctx["add_service_form"] = (
            StaffOrderAddServiceForm(tenant_id=order.tenant_id, outlet_id=order.outlet_id)
            if can_modify_open
            else None
        )
        promo_qs = promotions_selectable_for_order(order) if can_modify_open else None
        ctx["apply_promotion_form"] = (
            StaffOrderApplyPromotionForm(eligible_queryset=promo_qs) if promo_qs is not None and promo_qs.exists() else None
        )
        refundable = order_refundable_remaining(order)
        can_approve_refunds = membership_can_approve_refunds(m)
        can_refund = (
            can_approve_refunds
            and staff_outlet_allowed_for_membership(m, order.outlet_id)
            and order.status == OrderStatus.CLOSED
            and order.is_paid
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
            )
            if can_refund
            else None
        )
        ctx["pos_menu_categories"] = []
        ctx["pos_menu_item_modifiers"] = {}
        ctx["service_offerings"] = []
        if can_modify_open:
            menu_qs = (
                menu_items_for_outlet_queryset(order.tenant_id, order.outlet_id)
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
        ctx["scan_add_form"] = (
            StaffOrderScanAddForm()
            if can_modify_open and is_supermarket_outlet and hardware["barcode_scanner_enabled"]
            else None
        )
        ctx["line_discount_form"] = (
            StaffOrderLineDiscountForm()
            if can_modify_open and is_supermarket_outlet
            else None
        )
        ctx["line_return_form"] = (
            StaffOrderLineReturnForm()
            if is_supermarket_outlet and order.status == OrderStatus.CLOSED and order.is_paid
            else None
        )
        ctx["retail_refund_form"] = (
            StaffRetailLineRefundForm(
                lines=list(order.lines.all()), payments=pays, max_refund=refundable,
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

        if not membership_can_modify_lodging(m):
            messages.error(request, "Your role cannot modify orders or payments.")
            return redirect("staff-order-detail", order_id=order.id)
        if not staff_outlet_allowed_for_membership(m, order.outlet_id):
            messages.error(request, "You cannot modify this order for its outlet.")
            return redirect("staff-order-detail", order_id=order.id)

        if action == "record_payment":
            return self._post_record_payment(request, order)
        if action == "set_folio":
            return self._post_set_folio(request, order)
        if action == "charge_to_folio":
            try:
                charge_order_to_folio(order=order, membership=m, user=request.user)
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Remaining balance charged to the guest folio.")
            return redirect("staff-order-detail", order_id=order.id)
        if action == "add_line":
            return self._post_add_line(request, order)
        if action == "add_service_line":
            return self._post_add_service_line(request, order)
        if action == "adjust_line_qty":
            return self._post_adjust_line_quantity(request, order)
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
        if action == "void_order":
            return self._post_void_order(request, order)
        if action == "apply_promotion":
            return self._post_apply_promotion(request, order)
        if action == "void_line":
            return self._post_void_line(request, order)
        if action == "record_refund":
            return self._post_record_refund(request, order)
        if action == "ack_ready_line":
            return self._post_ack_ready_line(request, order)

        messages.error(request, "Unknown action.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_set_folio(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Folio can only be changed on open, unpaid orders.")
            return redirect("staff-order-detail", order_id=order.id)
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
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        folio_id = form.cleaned_data["folio_id"]
        try:
            set_open_order_folio(
                order=order,
                membership=request.tenant_membership,
                folio_id=folio_id,
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            if folio_id is None:
                messages.success(request, "Folio cleared.")
            else:
                messages.success(request, "Folio attached.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_ack_ready_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        assigned_server = bool(order.created_by_id and order.created_by_id == request.user.id)
        if not membership_can_acknowledge_ready_handoff(
            request.tenant_membership,
            is_assigned_server=assigned_server,
        ):
            messages.error(request, "Only the assigned server or a manager can acknowledge ready items.")
            return redirect("staff-order-detail", order_id=order.id)
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Handoff acknowledgements are only available on open, unpaid orders.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderReadyHandoffForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
            is_voided=False,
        ).first()
        if line is None:
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        if line.kds_status != KdsLineStatus.READY:
            messages.error(request, "Only ready items can be acknowledged for handoff.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            update_order_line_kds_status(
                order=order,
                line=line,
                kds_status=KdsLineStatus.SERVED.value,
                kds_station=None,
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, f"Handoff acknowledged: {line.label}")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_record_payment(self, request: HttpRequest, order: Order) -> HttpResponse:
        _, bal = order_payment_totals(order)
        if (
            order.status != OrderStatus.OPEN
            or order.is_paid
            or bal <= Decimal("0")
        ):
            messages.error(
                request,
                "Payments can only be recorded on open orders with an outstanding balance.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderPaymentForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            record_order_payment(
                order=order,
                user=request.user,
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                idempotency_key=str(uuid.uuid4()),
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Payment recorded.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_add_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(
                request,
                "Lines can only be added to open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderAddLineForm(
            request.POST,
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
        )
        if not form.is_valid():
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
                messages.error(request, "Invalid modifier selection.")
                return redirect("staff-order-detail", order_id=order.id)
        try:
            add_line_to_open_order(
                order=order,
                menu_item=form.cleaned_data["menu_item"],
                quantity=form.cleaned_data["quantity"],
                user=request.user,
                modifier_option_ids=modifier_option_ids or None,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Line added.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_add_service_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(
                request,
                "Services can only be added to open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderAddServiceForm(
            request.POST,
            tenant_id=order.tenant_id,
            outlet_id=order.outlet_id,
        )
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            add_service_to_open_order(
                order=order,
                service_offering=form.cleaned_data["service_offering"],
                service_option=form.cleaned_data.get("service_option"),
                quantity=form.cleaned_data["quantity"],
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Service added.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_adjust_line_quantity(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(
                request,
                "Line quantities can only be edited on open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderAdjustLineQuantityForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            adjust_open_order_line_quantity(
                order=order,
                line=line,
                quantity=form.cleaned_data["quantity"],
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Line updated.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_scan_add_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        if not _tenant_hardware_flags(order.tenant)["barcode_scanner_enabled"]:
            messages.error(request, "Barcode scanner input is disabled in workspace hardware settings.")
            return redirect("staff-order-detail", order_id=order.id)
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            messages.error(request, "Barcode add is only available on supermarket or retail outlets.")
            return redirect("staff-order-detail", order_id=order.id)
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Barcode add is only available for open, unpaid orders.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderScanAddForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            add_supermarket_line_by_code(
                order=order,
                code=form.cleaned_data["code"],
                quantity=form.cleaned_data["quantity"],
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "SKU added.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_line_discount(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            messages.error(request, "Line discount is only available on supermarket or retail outlets.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderLineDiscountForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            apply_supermarket_line_discount(
                order=order,
                line=line,
                user=request.user,
                discount_amount=form.cleaned_data.get("discount_amount"),
                discount_percent=form.cleaned_data.get("discount_percent"),
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Line discount saved.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_line_return(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            messages.error(request, "Line return is only available on supermarket or retail outlets.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderLineReturnForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            process_supermarket_line_return(
                order=order,
                line=line,
                quantity=form.cleaned_data["quantity"],
                reason=form.cleaned_data.get("reason") or "",
                restock=bool(form.cleaned_data.get("restock")),
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Line return recorded.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_retail_line_refund(self, request: HttpRequest, order: Order) -> HttpResponse:
        if not membership_can_approve_refunds(request.tenant_membership):
            messages.error(request, "Your role cannot approve refunds.")
            return redirect("staff-order-detail", order_id=order.id)
        if order.outlet.outlet_type not in {OutletType.SUPERMARKET, OutletType.RETAIL}:
            messages.error(request, "Item refunds are only available for retail orders.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffRetailLineRefundForm(
            request.POST, lines=list(order.lines.all()), payments=list(order.payments.all()),
            max_refund=order_refundable_remaining(order),
        )
        if not form.is_valid():
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect("staff-order-detail", order_id=order.id)
        line = order.lines.filter(id=form.cleaned_data["line_id"]).first()
        if line is None:
            messages.error(request, "That item is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            refund_retail_line(
                order=order, line=line, quantity=form.cleaned_data["quantity"],
                amount=form.cleaned_data["amount"], reason=form.cleaned_data.get("reason") or "",
                restock=bool(form.cleaned_data.get("restock")), user=request.user,
                idempotency_key=str(uuid.uuid4()),
                payment_id=uuid.UUID(form.cleaned_data["payment_id"]) if "payment_id" in form.fields else None,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Item return and customer refund recorded together.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_hold_order(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Only open, unpaid orders can be put on hold.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderHoldForm(request.POST)
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
            messages.success(request, "Order put on hold.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_void_order(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(request, "Only open, unpaid orders can be voided.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderVoidOrderForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            cancel_open_unpaid_order(
                order=order,
                user=request.user,
                reason=form.cleaned_data.get("reason") or "",
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Order voided.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_apply_promotion(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(
                request,
                "Offers can only be applied to open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        promo_qs = promotions_selectable_for_order(order)
        form = StaffOrderApplyPromotionForm(request.POST, eligible_queryset=promo_qs)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            apply_promotion_to_order(
                order=order,
                promotion=form.cleaned_data["promotion"],
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Promotion applied.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_void_line(self, request: HttpRequest, order: Order) -> HttpResponse:
        if order.status != OrderStatus.OPEN or order.is_paid:
            messages.error(
                request,
                "Lines can only be voided on open orders that are not yet paid.",
            )
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderVoidLineForm(request.POST)
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        line = OrderLine.objects.filter(
            id=form.cleaned_data["line_id"],
            order_id=order.id,
        ).first()
        if line is None:
            messages.error(request, "That line is not on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        try:
            void_open_order_line(
                order=order,
                line=line,
                reason=form.cleaned_data.get("reason") or "",
                user=request.user,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Line voided.")
        return redirect("staff-order-detail", order_id=order.id)

    def _post_record_refund(self, request: HttpRequest, order: Order) -> HttpResponse:
        if not membership_can_approve_refunds(request.tenant_membership):
            messages.error(request, "Refunds require approval by a supervisor or manager.")
            return redirect("staff-order-detail", order_id=order.id)
        if order.status != OrderStatus.CLOSED or not order.is_paid:
            messages.error(request, "Refunds apply only to closed, paid orders.")
            return redirect("staff-order-detail", order_id=order.id)
        pays = list(order.payments.order_by("created_at"))
        refundable = order_refundable_remaining(order)
        if refundable <= Decimal("0"):
            messages.error(request, "Nothing left to refund on this order.")
            return redirect("staff-order-detail", order_id=order.id)
        form = StaffOrderRefundForm(
            request.POST,
            payments=pays,
            max_refund=refundable,
        )
        if not form.is_valid():
            for fld, err_list in form.errors.items():
                for err in err_list:
                    messages.error(request, f"{fld}: {err}")
            return redirect("staff-order-detail", order_id=order.id)
        payment_id = None
        if "payment_id" in form.fields:
            payment_id = uuid.UUID(form.cleaned_data["payment_id"])
        try:
            record_order_refund(
                order=order,
                user=request.user,
                amount=form.cleaned_data["amount"],
                reason=form.cleaned_data.get("reason") or "",
                idempotency_key=str(uuid.uuid4()),
                restock=bool(form.cleaned_data.get("restock")),
                payment_id=payment_id,
            )
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
        else:
            messages.success(request, "Refund recorded.")
        return redirect("staff-order-detail", order_id=order.id)


class StaffOrderPrintView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "orders"
    template_name = "staff/order_print.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return (
            Order.objects.filter(tenant=self.request.tenant)
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

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        if outlet is None:
            return Table.objects.none()
        qs = Table.objects.filter(outlet=outlet).select_related("outlet", "outlet__site")
        if self.request.GET.get("include_inactive") != "1":
            qs = qs.filter(is_active=True)
        return qs.order_by("sort_order", "label")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ctx["outlets"] = outlets
        ctx["current_outlet"] = resolve_staff_outlet(self.request, outlets)
        ctx["can_modify_tables"] = membership_can_modify_lodging(self.request.tenant_membership)
        ctx["include_inactive"] = self.request.GET.get("include_inactive") == "1"
        return ctx


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
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        all_outlets = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL

        if outlet and not all_outlets:
            allowed_ids = menu_items_for_outlet_queryset(tenant_id, outlet.id).values_list("pk", flat=True)
            item_qs = MenuItem.objects.filter(pk__in=allowed_ids, is_active=True).order_by("name")
        else:
            item_qs = MenuItem.objects.filter(tenant_id=tenant_id, is_active=True).order_by("name")

        return (
            MenuCategory.objects.filter(tenant=self.request.tenant, is_active=True)
            .prefetch_related(Prefetch("items", queryset=item_qs))
            .order_by("sort_order", "name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        outlet = resolve_staff_outlet(self.request, outlets)
        ctx["menu_scope_outlet"] = outlet
        ctx["menu_all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        return ctx


class StaffSalesSummaryView(StaffTenantRequiredMixin, TemplateView):
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
        body = format_sales_summary_csv(request.tenant.id, d0, d1, oid)

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
        ctx["summary"] = build_sales_summary(self.request.tenant.id, d0, d1, oid)
        return ctx
