from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, FormView, ListView, UpdateView

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.catalog.models import MenuItem
from apps.purchasing.models import PurchaseOrder, PurchaseOrderStatus, Supplier, SupplierPaymentMethod
from apps.purchasing.serializers import PurchaseOrderCreateSerializer, PurchaseOrderStatusUpdateSerializer, RecordSupplierPaymentSerializer, ConfirmMissingUnitCostSerializer
from apps.purchasing.services import confirm_missing_unit_cost, receive_purchase_order_goods, record_supplier_payment, received_goods_value, has_legacy_receipt_expenses
from apps.tenants.models import Outlet, TenantSettings

from .forms import StaffPOHeaderForm, StaffSupplierForm
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets, membership_can_modify_lodging, resolve_staff_outlet

PO_LINE_SLOTS = 8


def _purchase_order_can_receive(po: PurchaseOrder) -> bool:
    return po.status in (PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIALLY_RECEIVED)


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    d = exc.detail
    if isinstance(d, dict):
        for key, val in d.items():
            parts = val if isinstance(val, list) else [val]
            for p in parts:
                messages.error(request, f"{key}: {str(p)}")
    else:
        messages.error(request, str(d))


def _flash_serializer_errors(request: HttpRequest, errors) -> None:
    for field, val in errors.items():
        if isinstance(val, dict):
            _flash_serializer_errors(request, val)
        elif isinstance(val, list):
            for item in val:
                messages.error(request, f"{field}: {str(item)}")
        else:
            messages.error(request, f"{field}: {str(val)}")


def _purchasing_requires_outlets(request) -> HttpResponse | None:
    outlets = staff_accessible_outlets(request.tenant_membership)
    if not outlets:
        messages.info(request, "You need at least one outlet for purchasing.")
        return redirect("staff-dashboard")
    return None


def _po_outlet_ids(request: HttpRequest, outlets: list[Outlet]) -> list[uuid.UUID]:
    current = resolve_staff_outlet(request, outlets)
    if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
        return [o.id for o in outlets]
    if current:
        return [current.id]
    return []


def _po_base_queryset(request) -> QuerySet:
    oids = [o.id for o in staff_accessible_outlets(request.tenant_membership)]
    return (
        PurchaseOrder.objects.filter(tenant=request.tenant, outlet_id__in=oids)
        .select_related("supplier", "outlet", "created_by")
        .prefetch_related("lines__menu_item", "receipts__lines__purchase_order_line__menu_item", "payments")
    )


class StaffSupplierListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/suppliers_list.html"
    context_object_name = "suppliers"
    paginate_by = 40

    def get_queryset(self):
        if not staff_accessible_outlets(self.request.tenant_membership):
            return Supplier.objects.none()
        return Supplier.objects.filter(tenant=self.request.tenant).order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_modify_purchasing"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffSupplierCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/supplier_form.html"
    form_class = StaffSupplierForm
    success_url = reverse_lazy("staff-purchasing-suppliers")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_modify_lodging(request.tenant_membership) or not staff_accessible_outlets(request.tenant_membership):
            messages.error(request, "Your role cannot manage suppliers.")
            return redirect("staff-purchasing-suppliers")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "New supplier"
        return ctx

    def form_valid(self, form):
        Supplier.objects.create(tenant=self.request.tenant, **form.cleaned_data)
        messages.success(self.request, "Supplier saved.")
        return super().form_valid(form)


class StaffSupplierUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "purchasing"
    model = Supplier
    form_class = StaffSupplierForm
    template_name = "staff/purchasing/supplier_form.html"
    pk_url_kwarg = "supplier_id"
    success_url = reverse_lazy("staff-purchasing-suppliers")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_modify_lodging(request.tenant_membership) or not staff_accessible_outlets(request.tenant_membership):
            messages.error(request, "Your role cannot manage suppliers.")
            return redirect("staff-purchasing-suppliers")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Supplier.objects.filter(tenant=self.request.tenant)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit supplier"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Supplier updated.")
        return super().form_valid(form)


class StaffPurchaseOrderListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/purchase_orders_list.html"
    context_object_name = "purchase_orders"
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        bad = _purchasing_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        oids = _po_outlet_ids(self.request, outlets)
        qs = _po_base_queryset(self.request).filter(outlet_id__in=oids).order_by("-created_at")
        if self.request.GET.get("lane") == "receiving":
            qs = qs.filter(status__in=[PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIALLY_RECEIVED]).order_by("expected_date", "created_at")
        st = self.request.GET.get("status")
        if st and st in {c[0] for c in PurchaseOrderStatus.choices}:
            qs = qs.filter(status=st)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ctx["outlets"] = outlets
        ctx["current_outlet"] = resolve_staff_outlet(self.request, outlets)
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["status_filter"] = self.request.GET.get("status") or ""
        ctx["receiving_lane"] = self.request.GET.get("lane") == "receiving"
        ctx["can_modify_purchasing"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffPurchaseOrderCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/purchase_order_create.html"
    form_class = StaffPOHeaderForm

    def dispatch(self, request, *args, **kwargs):
        bad = _purchasing_requires_outlets(request)
        if bad:
            return bad
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot create purchase orders.")
            return redirect("staff-purchasing-orders")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        oids = [o.id for o in outlets]
        kw["tenant"] = self.request.tenant
        kw["outlets_qs"] = Outlet.objects.filter(pk__in=oids, is_active=True).select_related("site")
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["line_slots"] = range(PO_LINE_SLOTS)
        ctx["menu_items"] = MenuItem.objects.filter(
            tenant=self.request.tenant,
            is_active=True,
            track_inventory=True,
        ).order_by("name")
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, outlets)
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        return ctx

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        header_ok = form.is_valid()
        lines_payload: list[dict] = []
        seen_mi: set[uuid.UUID] = set()
        line_errors: list[str] = []

        for i in range(PO_LINE_SLOTS):
            mid_raw = (request.POST.get(f"line_{i}_menu_item") or "").strip()
            qty_raw = (request.POST.get(f"line_{i}_quantity_ordered") or "").strip()
            cost_raw = (request.POST.get(f"line_{i}_unit_cost") or "").strip()
            if not mid_raw and not qty_raw and not cost_raw:
                continue
            if not mid_raw or not qty_raw:
                line_errors.append(f"Row {i + 1}: choose an item and quantity.")
                continue
            try:
                mid = uuid.UUID(mid_raw)
            except ValueError:
                line_errors.append(f"Row {i + 1}: invalid item.")
                continue
            if mid in seen_mi:
                line_errors.append(f"Row {i + 1}: duplicate item (each line must be a different SKU).")
                continue
            try:
                qty = Decimal(qty_raw)
            except InvalidOperation:
                line_errors.append(f"Row {i + 1}: invalid quantity.")
                continue
            if qty <= 0:
                line_errors.append(f"Row {i + 1}: quantity must be positive.")
                continue
            unit_cost = None
            if cost_raw:
                try:
                    unit_cost = Decimal(cost_raw)
                    if unit_cost < 0:
                        line_errors.append(f"Row {i + 1}: unit cost cannot be negative.")
                        continue
                except InvalidOperation:
                    line_errors.append(f"Row {i + 1}: invalid unit cost.")
                    continue
            seen_mi.add(mid)
            row: dict = {"menu_item": str(mid), "quantity_ordered": str(qty)}
            if unit_cost is not None:
                row["unit_cost"] = str(unit_cost)
            lines_payload.append(row)

        if line_errors:
            for e in line_errors:
                messages.error(request, e)
            ctx = self.get_context_data(form=form)
            return render(request, self.template_name, ctx)

        if not header_ok:
            ctx = self.get_context_data(form=form)
            return render(request, self.template_name, ctx)

        if not lines_payload:
            messages.error(request, "Add at least one line with a tracked menu item and quantity.")
            ctx = self.get_context_data(form=form)
            return render(request, self.template_name, ctx)

        vd = form.cleaned_data
        ser = PurchaseOrderCreateSerializer(
            data={
                "supplier": str(vd["supplier"].id),
                "outlet": str(vd["outlet"].id),
                "reference": vd.get("reference") or "",
                "expected_date": vd.get("expected_date"),
                "notes": vd.get("notes") or "",
                "lines": lines_payload,
            },
            context={"request": request},
        )
        if not ser.is_valid():
            _flash_serializer_errors(request, ser.errors)
            ctx = self.get_context_data(form=form)
            return render(request, self.template_name, ctx)

        po = ser.save()
        messages.success(self.request, "Purchase order created as draft.")
        return redirect("staff-purchasing-order-detail", po_id=po.id)


class StaffPurchaseOrderDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "purchasing"
    model = PurchaseOrder
    template_name = "staff/purchasing/purchase_order_detail.html"
    context_object_name = "po"
    pk_url_kwarg = "po_id"
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        bad = _purchasing_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return _po_base_queryset(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ctx["outlets"] = outlets
        ctx["current_outlet"] = resolve_staff_outlet(self.request, outlets)
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_modify_purchasing"] = membership_can_modify_lodging(self.request.tenant_membership)
        ctx["can_receive"] = self.object.status in (
            PurchaseOrderStatus.SENT,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        ctx["received_value"] = received_goods_value(self.object)
        ctx["supplier_paid"] = self.object.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        ctx["supplier_due"] = ctx["received_value"] - ctx["supplier_paid"]
        ctx["legacy_receipt_expenses"] = has_legacy_receipt_expenses(self.object)
        ctx["uncosted_received"] = self.object.lines.filter(quantity_received__gt=0, unit_cost__isnull=True).exists()
        ctx["supplier_payment_methods"] = SupplierPaymentMethod.choices
        settings = TenantSettings.objects.filter(tenant_id=self.object.tenant_id).first()
        ctx["purchase_currency"] = settings.default_currency if settings else "USD"
        ctx["supplier_payment_key"] = uuid.uuid4()
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        po: PurchaseOrder = self.object

        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot change purchase orders.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        action = request.POST.get("action", "").strip()

        if action == "confirm_cost":
            ser = ConfirmMissingUnitCostSerializer(data=request.POST)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    confirm_missing_unit_cost(
                        po=po, user=request.user, membership=request.tenant_membership,
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(request, "Unit cost confirmed.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "supplier_payment":
            ser = RecordSupplierPaymentSerializer(data=request.POST)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    _, replay = record_supplier_payment(
                        po=po, user=request.user, membership=request.tenant_membership,
                        idempotency_key=request.POST.get("idempotency_key", ""),
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(request, "Supplier payment already recorded." if replay else "Supplier payment recorded.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "send":
            ser = PurchaseOrderStatusUpdateSerializer(
                po,
                data={"status": PurchaseOrderStatus.SENT},
                partial=True,
            )
            if ser.is_valid():
                ser.save()
                messages.success(request, "Order marked as sent.")
            else:
                _flash_serializer_errors(request, ser.errors)
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "cancel":
            ser = PurchaseOrderStatusUpdateSerializer(
                po,
                data={"status": PurchaseOrderStatus.CANCELLED},
                partial=True,
            )
            if ser.is_valid():
                ser.save()
                messages.success(request, "Purchase order cancelled.")
            else:
                _flash_serializer_errors(request, ser.errors)
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "receive_all":
            if not _purchase_order_can_receive(po):
                messages.error(
                    request,
                    "Goods can only be received while the order is sent or partially received.",
                )
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            po_fresh = (
                PurchaseOrder.objects.filter(pk=po.pk)
                .prefetch_related("lines__menu_item")
                .first()
            )
            if po_fresh is None:
                messages.error(request, "Order not found.")
                return redirect("staff-purchasing-orders")
            lines_payload: list[dict] = []
            for line in po_fresh.lines.all():
                rem = line.quantity_remaining
                if rem > 0:
                    lines_payload.append({"line_id": line.id, "quantity": rem})
            if not lines_payload:
                messages.info(request, "Nothing left to receive on this order.")
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            try:
                receive_purchase_order_goods(
                    po=po_fresh,
                    lines_payload=lines_payload,
                    user=request.user,
                    membership=request.tenant_membership,
                    discrepancy_note=(request.POST.get("discrepancy_note") or "").strip(),
                    delivery_reference=(request.POST.get("delivery_reference") or "").strip(),
                    note=(request.POST.get("receipt_note") or "").strip(),
                )
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Received all outstanding quantities; stock updated.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "receive":
            if not _purchase_order_can_receive(po):
                messages.error(
                    request,
                    "Goods can only be received while the order is sent or partially received.",
                )
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            lines_payload: list[dict] = []
            for line in po.lines.all():
                raw = (request.POST.get(f"recv_{line.id}") or "").strip()
                if not raw:
                    continue
                try:
                    qty = Decimal(raw)
                except InvalidOperation:
                    messages.error(request, f"Invalid quantity for line {line.menu_item.name}.")
                    return redirect("staff-purchasing-order-detail", po_id=po.id)
                if qty > 0:
                    lines_payload.append({"line_id": line.id, "quantity": qty})

            if not lines_payload:
                messages.error(request, "Enter at least one quantity to receive.")
                return redirect("staff-purchasing-order-detail", po_id=po.id)

            try:
                receive_purchase_order_goods(
                    po=po,
                    lines_payload=lines_payload,
                    user=request.user,
                    membership=request.tenant_membership,
                    discrepancy_note=(request.POST.get("discrepancy_note") or "").strip(),
                    delivery_reference=(request.POST.get("delivery_reference") or "").strip(),
                    note=(request.POST.get("receipt_note") or "").strip(),
                )
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Goods received; stock updated.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        messages.error(request, "Unknown action.")
        return redirect("staff-purchasing-order-detail", po_id=po.id)
