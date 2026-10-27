from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, QuerySet, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, FormView, ListView, UpdateView, TemplateView

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.catalog.models import MenuItem, ProductPackage
from apps.pos.services import default_currency_for_tenant
from apps.purchasing.models import PurchaseApprovalStatus, PurchaseOrder, PurchaseOrderStatus, Supplier, SupplierPaymentMethod, SupplierProductCode
from apps.purchasing.serializers import PurchaseOrderCreateSerializer, PurchaseOrderStatusUpdateSerializer, RecordSupplierPaymentSerializer, LinkSupplierPaymentInvoiceSerializer, ConfirmMissingUnitCostSerializer, RecordSupplierInvoiceSerializer, RecordSupplierReturnSerializer, RecordSupplierCreditNoteSerializer, ReceivePurchaseOrderSerializer
from apps.purchasing.services import confirm_missing_unit_cost, receive_purchase_order_goods, record_supplier_payment, link_existing_supplier_payment_to_invoice, record_supplier_invoice, return_received_goods_to_supplier, record_supplier_credit_note, received_goods_value, has_legacy_receipt_expenses
from apps.purchasing.supplier_catalog import supplier_cost_histories
from apps.purchasing.approvals import (
    review_purchase_order_request,
    withdraw_purchase_order_request,
)
from apps.tenants.models import Outlet, TenantSettings

from .forms import StaffPOHeaderForm, StaffSupplierForm, StaffSupplierProductCodeForm
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets, membership_can_modify_lodging, resolve_staff_outlet
from .services.permissions import membership_has_purchasing_capability

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
        qs = Supplier.objects.filter(tenant=self.request.tenant)
        query = self.request.GET.get("q", "").strip()[:80]
        if query:
            qs = qs.filter(
                Q(name__icontains=query) | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_modify_purchasing"] = membership_has_purchasing_capability(self.request.tenant_membership, "manage")
        ctx["supplier_search_q"] = self.request.GET.get("q", "").strip()[:80]
        return ctx


class StaffSupplierCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/supplier_form.html"
    form_class = StaffSupplierForm
    success_url = reverse_lazy("staff-purchasing-suppliers")

    def dispatch(self, request, *args, **kwargs):
        if not membership_has_purchasing_capability(request.tenant_membership, "manage") or not staff_accessible_outlets(request.tenant_membership):
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
        if not membership_has_purchasing_capability(request.tenant_membership, "manage") or not staff_accessible_outlets(request.tenant_membership):
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


class StaffSupplierProductCodeView(StaffTenantRequiredMixin, TemplateView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/supplier_codes.html"

    def dispatch(self, request, *args, **kwargs):
        if not membership_has_purchasing_capability(request.tenant_membership, "manage"):
            messages.error(request, "Your role cannot manage supplier product codes.")
            return redirect("staff-purchasing-suppliers")
        self.supplier = Supplier.objects.filter(
            tenant=request.tenant, pk=kwargs["supplier_id"]
        ).first()
        if self.supplier is None:
            messages.error(request, "Supplier was not found.")
            return redirect("staff-purchasing-suppliers")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        edit_id = (self.request.GET.get("edit") or "").strip()
        instance = None
        if edit_id:
            try:
                code_id = uuid.UUID(edit_id)
            except ValueError:
                code_id = None
            if code_id is not None:
                instance = SupplierProductCode.objects.filter(
                    tenant=self.request.tenant,
                    supplier=self.supplier,
                    pk=code_id,
                ).first()
        ctx["supplier"] = self.supplier
        supplier_codes = list(
            SupplierProductCode.objects.filter(
                tenant=self.request.tenant,
                supplier=self.supplier,
            )
            .select_related("menu_item", "product_package")
            .order_by("menu_item__name", "code")
        )
        history_cache = supplier_cost_histories(
            tenant_id=self.request.tenant.pk,
            supplier_id=self.supplier.pk,
            menu_item_ids={row.menu_item_id for row in supplier_codes},
        )
        for row in supplier_codes:
            history = history_cache.get(row.menu_item_id)
            row.latest_received_unit_cost = history.latest_unit_cost if history else None
            row.previous_received_unit_cost = history.previous_unit_cost if history else None
            row.cost_change_amount = history.change_amount if history else None
            row.cost_change_percent = history.change_percent if history else None
            row.latest_cost_received_at = history.latest_received_at if history else None
        ctx["supplier_codes"] = supplier_codes
        ctx["code_form"] = StaffSupplierProductCodeForm(
            tenant=self.request.tenant,
            supplier=self.supplier,
            instance=instance,
        )
        ctx["editing_code"] = instance
        return ctx

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "save").strip()
        if action == "delete":
            try:
                code_id = uuid.UUID((request.POST.get("code_id") or "").strip())
            except ValueError:
                code_id = None
            obj = SupplierProductCode.objects.filter(
                tenant=request.tenant,
                supplier=self.supplier,
                pk=code_id,
            ).first()
            if obj is None:
                messages.error(request, "Supplier code was not found.")
            else:
                obj.delete()
                messages.success(request, "Supplier product code removed.")
            return redirect("staff-purchasing-supplier-codes", supplier_id=self.supplier.pk)

        instance = None
        raw_id = (request.POST.get("code_id") or "").strip()
        if raw_id:
            try:
                code_id = uuid.UUID(raw_id)
            except ValueError:
                code_id = None
            instance = SupplierProductCode.objects.filter(
                tenant=request.tenant,
                supplier=self.supplier,
                pk=code_id,
            ).first()
        if instance is None:
            instance = SupplierProductCode(
                tenant=request.tenant,
                supplier=self.supplier,
            )
        else:
            instance.tenant = request.tenant
            instance.supplier = self.supplier
        form = StaffSupplierProductCodeForm(
            request.POST,
            tenant=request.tenant,
            supplier=self.supplier,
            instance=instance,
        )
        if not form.is_valid():
            ctx = self.get_context_data()
            ctx["code_form"] = form
            ctx["editing_code"] = instance
            return render(request, self.template_name, ctx, status=400)
        obj = form.save(commit=False)
        obj.tenant = request.tenant
        obj.supplier = self.supplier
        obj.full_clean()
        obj.save()
        messages.success(request, "Supplier product code saved.")
        return redirect("staff-purchasing-supplier-codes", supplier_id=self.supplier.pk)


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
        lane = self.request.GET.get("lane")
        if lane == "receiving":
            qs = qs.filter(
                status__in=[
                    PurchaseOrderStatus.SENT,
                    PurchaseOrderStatus.PARTIALLY_RECEIVED,
                ]
            ).order_by("expected_date", "created_at")
        elif lane == "approval":
            qs = qs.filter(
                status=PurchaseOrderStatus.DRAFT,
                approval_status=PurchaseApprovalStatus.PENDING,
            ).order_by("created_at")
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
        ctx["approval_lane"] = self.request.GET.get("lane") == "approval"
        ctx["can_receive_stock"] = membership_has_purchasing_capability(self.request.tenant_membership, "receive")
        ctx["can_request_purchasing"] = membership_has_purchasing_capability(self.request.tenant_membership, "request")
        ctx["can_modify_purchasing"] = membership_has_purchasing_capability(self.request.tenant_membership, "manage")
        ctx["can_approve_purchasing"] = membership_has_purchasing_capability(self.request.tenant_membership, "approve")
        return ctx


class StaffPurchaseOrderCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/purchase_order_create.html"
    form_class = StaffPOHeaderForm

    def dispatch(self, request, *args, **kwargs):
        bad = _purchasing_requires_outlets(request)
        if bad:
            return bad
        if not membership_has_purchasing_capability(request.tenant_membership, "request"):
            messages.error(request, "Your role cannot prepare purchase requests.")
            return redirect("staff-purchasing-orders")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        oids = [o.id for o in outlets]
        kw["tenant"] = self.request.tenant
        kw["outlets_qs"] = Outlet.objects.filter(pk__in=oids, is_active=True).select_related("site")
        if self.request.method == "GET":
            initial = kw.setdefault("initial", {})
            try:
                chosen = uuid.UUID(self.request.GET.get("outlet", ""))
            except (ValueError, TypeError):
                chosen = None
            if chosen in oids:
                initial["outlet"] = chosen
            try:
                supplier_id = uuid.UUID(self.request.GET.get("supplier", ""))
            except (ValueError, TypeError):
                supplier_id = None
            if (
                supplier_id is not None
                and Supplier.objects.filter(
                    tenant=self.request.tenant,
                    pk=supplier_id,
                    is_active=True,
                ).exists()
            ):
                initial["supplier"] = supplier_id
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["line_slots"] = range(PO_LINE_SLOTS)
        ctx["prefill_menu_item"] = None
        ctx["prefill_qty"] = ""
        if self.request.method == "GET":
            try:
                item_id = uuid.UUID(self.request.GET.get("menu_item", ""))
                quantity = Decimal(self.request.GET.get("quantity", ""))
            except (ValueError, TypeError, InvalidOperation):
                item_id, quantity = None, None
            if (item_id is not None and quantity is not None
                    and quantity.is_finite() and 0 < quantity <= Decimal("999999")):
                item = MenuItem.objects.filter(
                    pk=item_id, tenant=self.request.tenant,
                    is_active=True, track_inventory=True,
                ).first()
                if item is not None:
                    ctx["prefill_menu_item"] = item.pk
                    ctx["prefill_qty"] = str(quantity)
        menu_items = list(
            MenuItem.objects.filter(
                tenant=self.request.tenant,
                is_active=True,
                track_inventory=True,
            ).order_by("name")
        )
        ctx["menu_items"] = menu_items
        product_packages = list(
            ProductPackage.objects.filter(
                tenant=self.request.tenant,
                is_active=True,
                is_purchasable=True,
                menu_item__is_active=True,
                menu_item__track_inventory=True,
            ).select_related("menu_item").order_by("menu_item__name", "units_per_package", "name")
        )
        selected_supplier = None
        supplier_raw = self.request.POST.get("supplier") if self.request.method == "POST" else self.request.GET.get("supplier")
        if supplier_raw:
            try:
                supplier_id = uuid.UUID(str(supplier_raw))
            except (ValueError, TypeError):
                supplier_id = None
            if supplier_id is not None:
                selected_supplier = Supplier.objects.filter(
                    tenant=self.request.tenant, pk=supplier_id, is_active=True
                ).first()
        supplier_codes = list(
            SupplierProductCode.objects.filter(
                tenant=self.request.tenant,
                supplier=selected_supplier,
                is_active=True,
            )
            .select_related("menu_item", "product_package")
            .order_by("menu_item__name", "code")
        ) if selected_supplier is not None else []
        package_codes = {
            row.product_package_id: row.code
            for row in supplier_codes
            if row.product_package_id is not None
        }
        product_codes = {}
        for row in supplier_codes:
            if row.product_package_id is None:
                product_codes.setdefault(row.menu_item_id, row.code)
        for package in product_packages:
            package.supplier_code_display = (
                package_codes.get(package.pk)
                or product_codes.get(package.menu_item_id)
                or ""
            )
        ctx["product_packages"] = product_packages
        ctx["selected_supplier"] = selected_supplier
        supplier_by_item = {}
        for row in supplier_codes:
            if row.product_package_id is None:
                supplier_by_item.setdefault(row.menu_item_id, row)
        menu_histories = (
            supplier_cost_histories(
                tenant_id=self.request.tenant.pk,
                supplier_id=selected_supplier.pk,
                menu_item_ids=[item.pk for item in menu_items],
            )
            if selected_supplier is not None else {}
        )
        for item in menu_items:
            relation = supplier_by_item.get(item.pk)
            item.supplier_reference_display = relation.code if relation else ""
            item.supplier_default_cost_display = (
                relation.default_unit_cost if relation and relation.default_unit_cost is not None else None
            )
            item.supplier_preferred_display = bool(relation and relation.is_preferred)
            history = menu_histories.get(item.pk)
            item.supplier_latest_cost_display = history.latest_unit_cost if history else None
            item.supplier_previous_cost_display = history.previous_unit_cost if history else None
        ctx["supplier_product_codes"] = supplier_codes
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, outlets)
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_approve_purchasing"] = membership_has_purchasing_capability(
            self.request.tenant_membership, "approve"
        )
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
            cartons_raw = (request.POST.get(f"line_{i}_cartons") or "").strip()
            package_raw = (request.POST.get(f"line_{i}_product_package") or "").strip()
            package_count_raw = (request.POST.get(f"line_{i}_package_count") or "").strip()
            cost_raw = (request.POST.get(f"line_{i}_unit_cost") or "").strip()
            if not mid_raw and not qty_raw and not cartons_raw and not package_raw and not package_count_raw and not cost_raw:
                continue
            if not mid_raw or not (qty_raw or cartons_raw or package_count_raw):
                line_errors.append(f"Row {i + 1}: choose an item and enter loose units, cartons or packages.")
                continue
            if cartons_raw and package_count_raw:
                line_errors.append(f"Row {i + 1}: use either the selected package or legacy cartons, not both.")
                continue
            if bool(package_raw) != bool(package_count_raw):
                line_errors.append(f"Row {i + 1}: choose a package and enter its package count together.")
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
                qty = Decimal(qty_raw) if qty_raw else Decimal("0")
            except InvalidOperation:
                line_errors.append(f"Row {i + 1}: invalid quantity.")
                continue
            if not qty.is_finite() or qty < 0:
                line_errors.append(f"Row {i + 1}: quantity must be finite and non-negative.")
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
            if cartons_raw:
                row["cartons"] = cartons_raw
            if package_raw:
                try:
                    package_id = uuid.UUID(package_raw)
                except ValueError:
                    line_errors.append(f"Row {i + 1}: invalid package.")
                    continue
                row["product_package"] = str(package_id)
                row["package_count"] = package_count_raw
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
            context={
                "request": request,
                "auto_approve": membership_has_purchasing_capability(
                    request.tenant_membership, "approve"
                ),
            },
        )
        if not ser.is_valid():
            _flash_serializer_errors(request, ser.errors)
            ctx = self.get_context_data(form=form)
            return render(request, self.template_name, ctx)

        try:
            po = ser.save()
        except DRFValidationError as exc:
            _flash_drf_validation(request, exc)
            return render(request, self.template_name, self.get_context_data(form=form))
        if po.approval_status == PurchaseApprovalStatus.PENDING:
            messages.success(
                self.request,
                "Purchase request submitted for manager approval. Nothing has been sent to the supplier.",
            )
        else:
            messages.success(self.request, "Manager-created purchase order saved as an approved draft.")
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
        ctx["can_modify_purchasing"] = membership_has_purchasing_capability(self.request.tenant_membership, "manage")
        ctx["can_approve_purchasing"] = bool(
            membership_has_purchasing_capability(self.request.tenant_membership, "approve")
            and self.object.status == PurchaseOrderStatus.DRAFT
            and self.object.approval_status == PurchaseApprovalStatus.PENDING
            and self.object.created_by_id != self.request.user.pk
        )
        ctx["can_withdraw_purchase_request"] = bool(
            self.object.status == PurchaseOrderStatus.DRAFT
            and self.object.approval_status == PurchaseApprovalStatus.PENDING
            and self.object.created_by_id == self.request.user.pk
        )
        ctx["can_receive"] = membership_has_purchasing_capability(self.request.tenant_membership, "receive") and self.object.status in (
            PurchaseOrderStatus.SENT,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        )
        ctx["received_value"] = received_goods_value(self.object)
        ctx["supplier_paid"] = self.object.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        ctx["supplier_invoiced"] = self.object.invoices.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        ctx["supplier_credited"] = self.object.credits.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        ctx["supplier_net_invoiced"] = ctx["supplier_invoiced"] - ctx["supplier_credited"]
        ctx["supplier_due"] = ctx["received_value"] - ctx["supplier_paid"] - ctx["supplier_credited"]
        # Use the same net invoice ceiling as the payment service.
        ctx["supplier_invoice_due"] = max(Decimal("0"), ctx["supplier_net_invoiced"] - ctx["supplier_paid"])
        ctx["supplier_payment_limit"] = min(
            ctx["supplier_due"],
            ctx["supplier_invoice_due"] if ctx["supplier_invoiced"] > 0 else ctx["supplier_due"],
        )
        ctx["legacy_receipt_expenses"] = has_legacy_receipt_expenses(self.object)
        ctx["uncosted_received"] = self.object.lines.filter(quantity_received__gt=0, unit_cost__isnull=True).exists()
        ctx["supplier_payment_methods"] = SupplierPaymentMethod.choices
        ctx["purchase_currency"] = default_currency_for_tenant(self.object.tenant)
        from apps.purchasing.services_exposure import supplier_invoice_settlement_rows
        ctx["invoice_settlement_rows"], ctx["unallocated_supplier_payments"] = supplier_invoice_settlement_rows(po=self.object)
        ctx["supplier_returns"] = self.object.returns_to_supplier.select_related("receipt_line__purchase_order_line__menu_item", "returned_by").all()
        ctx["supplier_payment_key"] = uuid.uuid4()
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        po: PurchaseOrder = self.object

        action = request.POST.get("action", "").strip()
        receiving = action in {"receive", "receive_all"}
        if action == "withdraw_request":
            permitted = membership_has_purchasing_capability(
                request.tenant_membership, "request"
            )
        elif action in {"approve_request", "reject_request"}:
            permitted = membership_has_purchasing_capability(
                request.tenant_membership, "approve"
            )
        else:
            permitted = (
                membership_has_purchasing_capability(
                    request.tenant_membership, "receive"
                )
                if receiving
                else membership_has_purchasing_capability(
                    request.tenant_membership, "manage"
                )
            )
        if not permitted:
            messages.error(request, "Your role cannot perform that purchasing action.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action in {"approve_request", "reject_request"}:
            try:
                review_purchase_order_request(
                    po=po,
                    membership=request.tenant_membership,
                    user=request.user,
                    decision=(
                        PurchaseApprovalStatus.APPROVED
                        if action == "approve_request"
                        else PurchaseApprovalStatus.REJECTED
                    ),
                    note=(request.POST.get("review_note") or "").strip(),
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(
                    request,
                    "Purchase request approved; the draft may now be sent."
                    if action == "approve_request"
                    else "Purchase request rejected; nothing was sent to the supplier.",
                )
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "withdraw_request":
            try:
                withdraw_purchase_order_request(
                    po=po,
                    membership=request.tenant_membership,
                    user=request.user,
                )
            except DRFValidationError as exc:
                _flash_drf_validation(request, exc)
            else:
                messages.success(request, "Purchase request withdrawn.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

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

        if action == "supplier_credit":
            ser = RecordSupplierCreditNoteSerializer(data=request.POST)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    _, replay = record_supplier_credit_note(
                        po=po, user=request.user, membership=request.tenant_membership,
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(request, "Credit already recorded." if replay else "Supplier credit recorded. No stock or cash was changed.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "supplier_return":
            ser = RecordSupplierReturnSerializer(data=request.POST)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    _, replay = return_received_goods_to_supplier(
                        po=po, user=request.user, membership=request.tenant_membership,
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(request, "Supplier return was already recorded." if replay else "Goods returned: stock reduced and audited. Supplier credit/cash are separate.")
            return redirect("staff-purchasing-order-detail", po_id=po.pk)

        if action == "supplier_invoice":
            invoice_payload = request.POST.dict()
            invoice_lines = []
            for line in po.lines.all():
                qty = (request.POST.get(f"invoice_qty_{line.pk}") or "").strip()
                cost = (request.POST.get(f"invoice_cost_{line.pk}") or "").strip()
                if qty:
                    invoice_lines.append({"line_id": str(line.pk), "quantity": qty, "unit_cost": cost})
            if not invoice_lines:
                messages.error(request, "Enter at least one received item and its quantity from the supplier invoice. Header-only invoices are not a verified three-way match.")
                return redirect("staff-purchasing-order-detail", po_id=po.pk)
            invoice_payload["lines"] = invoice_lines
            ser = RecordSupplierInvoiceSerializer(data=invoice_payload)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    _, replay = record_supplier_invoice(
                        po=po, user=request.user, membership=request.tenant_membership,
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(request, "Invoice already recorded." if replay else "Supplier invoice recorded.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        if action == "supplier_payment_link":
            ser = LinkSupplierPaymentInvoiceSerializer(data=request.POST)
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
            else:
                try:
                    _, replay = link_existing_supplier_payment_to_invoice(
                        po=po, user=request.user, membership=request.tenant_membership,
                        **ser.validated_data,
                    )
                except DRFValidationError as exc:
                    _flash_drf_validation(request, exc)
                else:
                    messages.success(
                        request,
                        "Payment already linked to this invoice." if replay else
                        "Historical payment linked to the verified invoice; no new payment or stock movement was recorded.",
                    )
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
            if request.POST.get("verified_physical_delivery") != "yes":
                messages.error(request, "Confirm that every outstanding item was physically counted before receiving all.")
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            delivery_reference = (request.POST.get("delivery_reference") or "").strip()
            if not delivery_reference:
                messages.error(request, "Enter the supplier delivery note or shipment reference before receiving all.")
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            po_fresh = (
                PurchaseOrder.objects.filter(pk=po.pk)
                .prefetch_related("lines__menu_item")
                .first()
            )
            if po_fresh is not None and any(
                line.quantity_remaining > 0 and line.menu_item.serial_tracking
                for line in po_fresh.lines.all()
            ):
                messages.error(
                    request,
                    "Serialized products need their exact serial / IMEI values. Use Partial goods received for this delivery.",
                )
                return redirect("staff-purchasing-order-detail", po_id=po.id)
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
                    delivery_reference=delivery_reference,
                    note=(request.POST.get("receipt_note") or "").strip(),
                    shipping_cost=request.POST.get("shipping_cost") or "0",
                    duty_cost=request.POST.get("duty_cost") or "0",
                    landed_cost_allocation=(
                        request.POST.get("landed_cost_allocation")
                        or "exclude"
                    ),
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
                cartons_raw = (request.POST.get(f"recv_cartons_{line.id}") or "").strip()
                packages_raw = (request.POST.get(f"recv_packages_{line.id}") or "").strip()
                serials_raw = (request.POST.get(f"recv_serials_{line.id}") or "").strip()
                serial_numbers = [
                    value.strip()
                    for value in serials_raw.replace(",", "\n").splitlines()
                    if value.strip()
                ]
                if not raw and not cartons_raw and not packages_raw and not serial_numbers:
                    continue
                if cartons_raw and packages_raw:
                    messages.error(request, f"Use packages or cartons for {line.menu_item.name}, not both.")
                    return redirect("staff-purchasing-order-detail", po_id=po.id)
                if packages_raw and not line.package_units_snapshot:
                    messages.error(request, f"{line.menu_item.name} was not ordered with a package definition.")
                    return redirect("staff-purchasing-order-detail", po_id=po.id)
                try:
                    qty = Decimal(raw) if raw else (
                        Decimal(len(serial_numbers))
                        if line.menu_item.serial_tracking and serial_numbers and not cartons_raw and not packages_raw
                        else Decimal("0")
                    )
                except InvalidOperation:
                    messages.error(request, f"Invalid quantity for line {line.menu_item.name}.")
                    return redirect("staff-purchasing-order-detail", po_id=po.id)
                if not qty.is_finite() or qty < 0:
                    messages.error(request, f"Enter a valid positive quantity for {line.menu_item.name}.")
                    return redirect("staff-purchasing-order-detail", po_id=po.id)
                if qty > 0 or cartons_raw or packages_raw:
                    entry = {"line_id": line.id, "quantity": qty}
                    if cartons_raw:
                        entry["cartons"] = cartons_raw
                    if packages_raw:
                        entry["packages"] = packages_raw
                    if serial_numbers:
                        entry["serial_numbers"] = serial_numbers
                    code = (request.POST.get(f"batch_{line.id}") or "").strip()
                    expiry_raw = (request.POST.get(f"expiry_{line.id}") or "").strip()
                    if code:
                        entry["batch_code"] = code
                    if expiry_raw:
                        entry["expiry_date"] = expiry_raw
                    lines_payload.append(entry)

            if not lines_payload:
                messages.error(request, "Enter at least one quantity to receive.")
                return redirect("staff-purchasing-order-detail", po_id=po.id)

            ser = ReceivePurchaseOrderSerializer(data={"lines": lines_payload})
            if not ser.is_valid():
                _flash_serializer_errors(request, ser.errors)
                return redirect("staff-purchasing-order-detail", po_id=po.id)
            try:
                receive_purchase_order_goods(
                    po=po,
                    lines_payload=ser.validated_data["lines"],
                    user=request.user,
                    membership=request.tenant_membership,
                    discrepancy_note=(request.POST.get("discrepancy_note") or "").strip(),
                    delivery_reference=(request.POST.get("delivery_reference") or "").strip(),
                    note=(request.POST.get("receipt_note") or "").strip(),
                    shipping_cost=request.POST.get("shipping_cost") or "0",
                    duty_cost=request.POST.get("duty_cost") or "0",
                    landed_cost_allocation=(
                        request.POST.get("landed_cost_allocation")
                        or "exclude"
                    ),
                )
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Goods received; stock updated.")
            return redirect("staff-purchasing-order-detail", po_id=po.id)

        messages.error(request, "Unknown action.")
        return redirect("staff-purchasing-order-detail", po_id=po.id)



class StaffSupplierBalancesView(StaffTenantRequiredMixin, TemplateView):
    """Purchase-order supplier payables for the member's permitted outlets."""
    staff_nav_capability = "purchasing"
    template_name = "staff/purchasing/supplier_balances.html"

    def get_context_data(self, **kwargs):
        from apps.purchasing.services_exposure import purchase_order_exposure
        ctx = super().get_context_data(**kwargs)
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ids = _po_outlet_ids(self.request, outlets)
        ctx["exposure_rows"] = purchase_order_exposure(
            tenant=self.request.tenant, outlet_ids=ids,
        )
        ctx["purchase_currency"] = default_currency_for_tenant(self.request.tenant)
        ctx["missing_cost_count"] = sum(
            int(row["missing_cost_data"]) for row in ctx["exposure_rows"]
        )
        ctx["known_supplier_due"] = sum(
            (row["unpaid_received_value"] or Decimal("0") for row in ctx["exposure_rows"]),
            Decimal("0"),
        )
        ctx["known_unbilled_received"] = sum(
            (row["unbilled_received_value"] or Decimal("0") for row in ctx["exposure_rows"]),
            Decimal("0"),
        )
        ctx["known_unpaid_invoiced"] = sum(
            (row["unpaid_invoiced_value"] for row in ctx["exposure_rows"]),
            Decimal("0"),
        )
        ctx["known_overdue_invoiced"] = sum(
            (
                row["overdue_invoiced_value"] or Decimal("0")
                for row in ctx["exposure_rows"]
                if row["invoice_aging_exact"]
            ),
            Decimal("0"),
        )
        ctx["invoice_allocation_required_count"] = sum(
            int(
                row["invoiced_value"] > 0
                and not row["invoice_aging_exact"]
            )
            for row in ctx["exposure_rows"]
        )
        return ctx
