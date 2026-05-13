from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, FormView, ListView

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.access.outlets import outlet_belongs_to_membership
from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockBalance, StockCountSession, StockCountStatus, StockMovement, StockReason
from apps.inventory.services import apply_manual_stock_change, complete_stock_count_session, execute_stock_transfer
from apps.pos.services import menu_items_for_outlet_queryset
from apps.tenants.models import Outlet

from .forms import (
    StaffQuickTrackedMenuItemForm,
    StaffStockCountSessionForm,
    StaffStockMovementForm,
    StaffStockMovementUploadForm,
    StaffStockTransferForm,
)
from .middleware import STAFF_SESSION_OUTLET_ALL, STAFF_SESSION_OUTLET_KEY
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets, membership_can_modify_lodging, resolve_staff_outlet

UPLOAD_ERROR_REPORT_SESSION_KEY = "staff_inventory_upload_error_rows"


def _flash_drf_validation(request: HttpRequest, exc: DRFValidationError) -> None:
    d = exc.detail
    if isinstance(d, dict):
        for key, val in d.items():
            parts = val if isinstance(val, list) else [val]
            for p in parts:
                messages.error(request, f"{key}: {str(p)}")
    else:
        messages.error(request, str(d))


def _inventory_requires_outlets(request) -> HttpResponse | None:
    outlets = staff_accessible_outlets(request.tenant_membership)
    if not outlets:
        messages.info(request, "You need at least one outlet to use inventory.")
        return redirect("staff-dashboard")
    return None


def _outlet_filter_ids(request, outlets: list[Outlet]) -> list[uuid.UUID] | None:
    """Return outlet UUIDs for list queries, or None for 'all accessible'."""
    current = resolve_staff_outlet(request, outlets)
    if request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL:
        return [o.id for o in outlets]
    if current:
        return [current.id]
    return [o.id for o in outlets]


def _normalize_reason(value: str) -> str | None:
    token = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not token:
        return None
    aliases = {
        "receive": StockReason.RECEIVE.value,
        "purchase": StockReason.RECEIVE.value,
        "adjust_in": StockReason.ADJUST_IN.value,
        "adjust_out": StockReason.ADJUST_OUT.value,
        "waste": StockReason.WASTE.value,
    }
    if token in aliases:
        return aliases[token]
    valid = {StockReason.RECEIVE.value, StockReason.ADJUST_IN.value, StockReason.ADJUST_OUT.value, StockReason.WASTE.value}
    return token if token in valid else None


class StaffStockBalanceListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/balances.html"
    context_object_name = "balances"
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ids = _outlet_filter_ids(self.request, outlets)
        qs = (
            StockBalance.objects.filter(tenant=self.request.tenant, outlet_id__in=ids)
            .select_related("outlet", "outlet__site", "menu_item")
            .order_by("outlet__name", "menu_item__name")
        )
        if self.request.GET.get("low_stock", "").lower() in ("1", "true", "yes"):
            qs = qs.filter(
                menu_item__track_inventory=True,
                menu_item__reorder_level__isnull=False,
            ).filter(quantity__lte=F("menu_item__reorder_level"))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["low_stock"] = self.request.GET.get("low_stock", "").lower() in ("1", "true", "yes")
        ctx["can_modify_inventory"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffStockMovementListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/movements.html"
    context_object_name = "movements"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ids = _outlet_filter_ids(self.request, outlets)
        return (
            StockMovement.objects.filter(tenant=self.request.tenant, outlet_id__in=ids)
            .select_related("outlet", "menu_item", "created_by")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_modify_inventory"] = membership_can_modify_lodging(self.request.tenant_membership)
        ctx["has_upload_error_report"] = bool(self.request.session.get(UPLOAD_ERROR_REPORT_SESSION_KEY))
        return ctx


class StaffStockMovementCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/movement_form.html"
    form_class = StaffStockMovementForm

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot record stock movements.")
            return redirect("staff-inventory-movements")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        tenant = self.request.tenant
        kw["menu_items_qs"] = MenuItem.objects.filter(
            tenant=tenant,
            is_active=True,
            track_inventory=True,
        ).order_by("name")
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        kw["outlets"] = outlets
        kw["default_outlet"] = resolve_staff_outlet(self.request, outlets)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        frm = ctx.get("form")
        has_items = False
        if frm is not None:
            try:
                has_items = frm.fields["menu_item"].queryset.exists()
            except Exception:
                has_items = False
        ctx["has_tracked_menu_items"] = has_items
        ctx["has_menu_categories"] = MenuCategory.objects.filter(
            tenant=self.request.tenant,
            is_active=True,
        ).exists()
        ctx["quick_item_form"] = kwargs.get("quick_item_form") or StaffQuickTrackedMenuItemForm(tenant=self.request.tenant)
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        if action == "create_tracked_item":
            return self._post_create_tracked_item(request)
        return super().post(request, *args, **kwargs)

    def _post_create_tracked_item(self, request: HttpRequest) -> HttpResponse:
        if not MenuCategory.objects.filter(tenant=request.tenant, is_active=True).exists():
            messages.error(
                request,
                "Create at least one active menu category first before adding tracked items.",
            )
            return redirect("console-org-menu-category-create")
        quick_form = StaffQuickTrackedMenuItemForm(request.POST, tenant=request.tenant)
        if not quick_form.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_form(),
                    quick_item_form=quick_form,
                )
            )
        mi = MenuItem.objects.create(
            tenant=request.tenant,
            category=quick_form.cleaned_data["category"],
            name=(quick_form.cleaned_data["name"] or "").strip(),
            sku=(quick_form.cleaned_data.get("sku") or "").strip(),
            barcode=(quick_form.cleaned_data.get("barcode") or "").strip(),
            unit_price=quick_form.cleaned_data["unit_price"],
            track_inventory=True,
            is_active=True,
        )
        messages.success(request, f"Tracked item created: {mi.name}")
        return redirect("staff-inventory-movement-create")

    def form_valid(self, form):
        outlet: Outlet = form.cleaned_data["outlet"]
        if not outlet_belongs_to_membership(self.request.tenant_membership, outlet.id):
            messages.error(self.request, "You cannot post stock for that outlet.")
            return self.form_invalid(form)
        menu_item = form.cleaned_data["menu_item"]
        reason = form.cleaned_data["reason"]
        qty = form.cleaned_data["quantity"]
        if reason in (StockReason.ADJUST_OUT.value, StockReason.WASTE.value):
            delta = -qty
        else:
            delta = qty
        try:
            apply_manual_stock_change(
                tenant_id=self.request.tenant.id,
                outlet=outlet,
                menu_item=menu_item,
                quantity_change=delta,
                reason=reason,
                user=self.request.user,
                note=form.cleaned_data.get("note") or "",
            )
        except DRFValidationError as e:
            _flash_drf_validation(self.request, e)
            return self.form_invalid(form)
        messages.success(self.request, "Movement recorded.")
        return redirect("staff-inventory-movements")


class StaffStockMovementUploadView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/movement_upload.html"
    form_class = StaffStockMovementUploadForm

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot upload stock movements.")
            return redirect("staff-inventory-movements")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        kw["outlets"] = outlets
        kw["default_outlet"] = resolve_staff_outlet(self.request, outlets)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["has_error_report"] = bool(self.request.session.get(UPLOAD_ERROR_REPORT_SESSION_KEY))
        return ctx

    def form_valid(self, form):
        outlets = list(staff_accessible_outlets(self.request.tenant_membership))
        outlet_by_id = {str(o.id): o for o in outlets}
        outlet_by_name = {o.name.strip().lower(): o for o in outlets}
        default_outlet = form.cleaned_data.get("default_outlet")
        default_reason = _normalize_reason(form.cleaned_data.get("default_reason") or "")

        item_qs = MenuItem.objects.filter(
            tenant=self.request.tenant,
            is_active=True,
            track_inventory=True,
        )
        item_by_id = {str(i.id): i for i in item_qs}
        item_by_name = {i.name.strip().lower(): i for i in item_qs}
        item_by_sku = {i.sku.strip().lower(): i for i in item_qs if (i.sku or "").strip()}
        item_by_barcode = {i.barcode.strip().lower(): i for i in item_qs if (i.barcode or "").strip()}

        raw = form.cleaned_data["csv_file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(self.request, "CSV must be UTF-8 encoded.")
            return self.form_invalid(form)

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            messages.error(self.request, "CSV is empty.")
            return self.form_invalid(form)

        success_count = 0
        errors: list[str] = []
        failed_rows: list[dict[str, str]] = []
        for row_num, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            outlet_raw = (row.get("outlet_id") or row.get("outlet") or "").strip()
            menu_id_raw = (row.get("menu_item_id") or "").strip()
            sku_raw = (row.get("sku") or "").strip().lower()
            barcode_raw = (row.get("barcode") or "").strip().lower()
            name_raw = (row.get("menu_item") or row.get("item") or "").strip().lower()
            reason_raw = (row.get("reason") or "").strip()
            qty_raw = (row.get("quantity") or "").strip()
            note = (row.get("note") or "").strip()

            outlet = None
            if outlet_raw:
                outlet = outlet_by_id.get(outlet_raw) or outlet_by_name.get(outlet_raw.lower())
            else:
                outlet = default_outlet
            if outlet is None:
                errors.append(f"Row {row_num}: outlet missing or not allowed.")
                failed_rows.append({"row": str(row_num), "error": "outlet missing or not allowed", "raw": str(row)})
                continue

            menu_item = None
            if menu_id_raw:
                menu_item = item_by_id.get(menu_id_raw)
            elif sku_raw:
                menu_item = item_by_sku.get(sku_raw)
            elif barcode_raw:
                menu_item = item_by_barcode.get(barcode_raw)
            elif name_raw:
                menu_item = item_by_name.get(name_raw)
            if menu_item is None:
                errors.append(f"Row {row_num}: item not found (use menu_item_id/sku/barcode/menu_item).")
                failed_rows.append({"row": str(row_num), "error": "item not found", "raw": str(row)})
                continue

            reason = _normalize_reason(reason_raw) or default_reason
            if reason is None:
                errors.append(f"Row {row_num}: reason missing/invalid.")
                failed_rows.append({"row": str(row_num), "error": "reason missing/invalid", "raw": str(row)})
                continue
            try:
                qty = Decimal(qty_raw)
            except InvalidOperation:
                errors.append(f"Row {row_num}: invalid quantity.")
                failed_rows.append({"row": str(row_num), "error": "invalid quantity", "raw": str(row)})
                continue
            if qty <= Decimal("0"):
                errors.append(f"Row {row_num}: quantity must be positive.")
                failed_rows.append({"row": str(row_num), "error": "quantity must be positive", "raw": str(row)})
                continue
            delta = -qty if reason in (StockReason.ADJUST_OUT.value, StockReason.WASTE.value) else qty
            try:
                apply_manual_stock_change(
                    tenant_id=self.request.tenant.id,
                    outlet=outlet,
                    menu_item=menu_item,
                    quantity_change=delta,
                    reason=reason,
                    user=self.request.user,
                    note=note,
                )
            except DRFValidationError as exc:
                errors.append(f"Row {row_num}: {str(exc.detail)}")
                failed_rows.append({"row": str(row_num), "error": str(exc.detail), "raw": str(row)})
                continue
            success_count += 1

        if success_count:
            messages.success(self.request, f"Imported {success_count} stock movement row(s).")
        if errors:
            self.request.session[UPLOAD_ERROR_REPORT_SESSION_KEY] = failed_rows
            preview = " | ".join(errors[:5])
            suffix = " (showing first 5)" if len(errors) > 5 else ""
            messages.error(
                self.request,
                f"{len(errors)} row(s) failed{suffix}: {preview} Download error report CSV from this page.",
            )
        else:
            self.request.session.pop(UPLOAD_ERROR_REPORT_SESSION_KEY, None)
        if success_count == 0:
            return self.form_invalid(form)
        return redirect("staff-inventory-movements")


class StaffStockMovementUploadTemplateCsvView(StaffTenantRequiredMixin, FormView):
    """Download CSV template for inventory movement uploads."""

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock-movement-template.csv"'
        writer = csv.writer(response)
        writer.writerow(["outlet", "outlet_id", "menu_item", "menu_item_id", "sku", "barcode", "reason", "quantity", "note"])
        writer.writerow(["Main Bar", "", "", "", "BEER-001", "", "receive", "24", "supplier delivery"])
        writer.writerow(["Main Spa", "", "Massage oil", "", "", "", "adjust_in", "6", "manual top-up"])
        writer.writerow(["Main Bar", "", "", "", "BEER-001", "", "waste", "2", "broken bottles"])
        return response


class StaffStockMovementUploadErrorCsvView(StaffTenantRequiredMixin, FormView):
    """Download failed-row error report from latest CSV upload."""

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        rows = list(request.session.get(UPLOAD_ERROR_REPORT_SESSION_KEY) or [])
        if not rows:
            messages.info(request, "No failed upload rows to export.")
            return redirect("staff-inventory-movement-upload")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock-movement-upload-errors.csv"'
        writer = csv.writer(response)
        writer.writerow(["row", "error", "raw"])
        for r in rows:
            writer.writerow([r.get("row", ""), r.get("error", ""), r.get("raw", "")])
        return response


class StaffStockTransferView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/transfer_form.html"
    form_class = StaffStockTransferForm

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot transfer stock.")
            return redirect("staff-inventory-balances")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        tenant = self.request.tenant
        outlets = list(staff_accessible_outlets(self.request.tenant_membership))
        kw["outlets"] = outlets
        kw["menu_items_qs"] = MenuItem.objects.filter(
            tenant=tenant,
            is_active=True,
            track_inventory=True,
        ).order_by("name")
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        return ctx

    def form_valid(self, form):
        try:
            execute_stock_transfer(
                tenant_id=self.request.tenant.id,
                membership=self.request.tenant_membership,
                from_outlet=form.cleaned_data["from_outlet"],
                to_outlet=form.cleaned_data["to_outlet"],
                menu_item=form.cleaned_data["menu_item"],
                quantity=form.cleaned_data["quantity"],
                user=self.request.user,
                note=form.cleaned_data.get("note") or "",
            )
        except DRFValidationError as e:
            _flash_drf_validation(self.request, e)
            return self.form_invalid(form)
        messages.success(self.request, "Transfer completed.")
        return redirect("staff-inventory-movements")


class StaffStockCountListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/counts_list.html"
    context_object_name = "sessions"
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        ids = _outlet_filter_ids(self.request, outlets)
        return (
            StockCountSession.objects.filter(tenant=self.request.tenant, outlet_id__in=ids)
            .select_related("outlet", "created_by")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_modify_inventory"] = membership_can_modify_lodging(self.request.tenant_membership)
        return ctx


class StaffStockCountCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "inventory"
    template_name = "staff/inventory/count_create.html"
    form_class = StaffStockCountSessionForm

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot start stock counts.")
            return redirect("staff-inventory-counts")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        kw["outlets_qs"] = Outlet.objects.filter(
            pk__in=[o.id for o in outlets],
            is_active=True,
        ).select_related("site")
        kw["default_outlet"] = resolve_staff_outlet(self.request, outlets)
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        return ctx

    def form_valid(self, form):
        outlet = form.cleaned_data["outlet"]
        if not outlet_belongs_to_membership(self.request.tenant_membership, outlet.id):
            messages.error(self.request, "You cannot start a count for that outlet.")
            return self.form_invalid(form)
        session = StockCountSession.objects.create(
            tenant=self.request.tenant,
            outlet=outlet,
            note=(form.cleaned_data.get("note") or "")[:512],
            created_by=self.request.user,
            status=StockCountStatus.DRAFT,
        )
        messages.success(self.request, "Count session started — enter counted quantities.")
        return redirect("staff-inventory-count-detail", session_id=session.id)


class StaffStockCountDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "inventory"
    model = StockCountSession
    template_name = "staff/inventory/count_detail.html"
    context_object_name = "count_session"
    pk_url_kwarg = "session_id"
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        bad = _inventory_requires_outlets(request)
        if bad:
            return bad
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        outlets = staff_accessible_outlets(self.request.tenant_membership)
        allowed = {o.id for o in outlets}
        return (
            StockCountSession.objects.filter(tenant=self.request.tenant, outlet_id__in=allowed)
            .select_related("outlet", "created_by")
            .prefetch_related("lines__menu_item")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sess: StockCountSession = ctx["count_session"]
        ctx["outlets"] = staff_accessible_outlets(self.request.tenant_membership)
        ctx["current_outlet"] = resolve_staff_outlet(self.request, ctx["outlets"])
        ctx["all_outlets_mode"] = self.request.session.get(STAFF_SESSION_OUTLET_KEY) == STAFF_SESSION_OUTLET_ALL
        ctx["can_modify_inventory"] = membership_can_modify_lodging(self.request.tenant_membership)
        rows = []
        if sess.status == StockCountStatus.DRAFT:
            items = (
                menu_items_for_outlet_queryset(self.request.tenant.id, sess.outlet_id)
                .filter(track_inventory=True)
                .order_by("name")
            )
            bal_map = {
                b.menu_item_id: b.quantity
                for b in StockBalance.objects.filter(outlet_id=sess.outlet_id, tenant=self.request.tenant)
            }
            for mi in items:
                rows.append(
                    {
                        "menu_item": mi,
                        "system_qty": bal_map.get(mi.id, Decimal("0")),
                    }
                )
        ctx["count_rows"] = rows
        return ctx

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.object = self.get_object()
        sess: StockCountSession = self.object
        if not membership_can_modify_lodging(request.tenant_membership):
            messages.error(request, "Your role cannot change stock counts.")
            return redirect("staff-inventory-count-detail", session_id=sess.id)

        action = request.POST.get("action", "").strip()
        if action == "cancel":
            if sess.status != StockCountStatus.DRAFT:
                messages.error(request, "Only draft sessions can be cancelled.")
            elif not outlet_belongs_to_membership(request.tenant_membership, sess.outlet_id):
                messages.error(request, "You cannot cancel this session.")
            else:
                sess.status = StockCountStatus.CANCELLED
                sess.save(update_fields=["status", "updated_at"])
                messages.success(request, "Count session cancelled.")
            return redirect("staff-inventory-count-detail", session_id=sess.id)

        if action == "complete":
            if sess.status != StockCountStatus.DRAFT:
                messages.error(request, "Only draft sessions can be completed.")
                return redirect("staff-inventory-count-detail", session_id=sess.id)
            if not outlet_belongs_to_membership(request.tenant_membership, sess.outlet_id):
                messages.error(request, "You cannot complete this session.")
                return redirect("staff-inventory-count-detail", session_id=sess.id)

            items = list(
                menu_items_for_outlet_queryset(request.tenant.id, sess.outlet_id)
                .filter(track_inventory=True)
                .order_by("name")
            )
            if not items:
                messages.error(request, "No tracked items are available at this outlet.")
                return redirect("staff-inventory-count-detail", session_id=sess.id)

            bal_map = {
                b.menu_item_id: b.quantity
                for b in StockBalance.objects.filter(outlet_id=sess.outlet_id, tenant=request.tenant)
            }
            resolved: list[dict] = []
            for mi in items:
                key = f"counted_{mi.id}"
                raw = request.POST.get(key, "").strip()
                if raw == "":
                    counted = bal_map.get(mi.id, Decimal("0"))
                else:
                    try:
                        counted = Decimal(raw)
                    except InvalidOperation:
                        messages.error(request, f"Invalid quantity for {mi.name}.")
                        return redirect("staff-inventory-count-detail", session_id=sess.id)
                    if counted < 0:
                        messages.error(request, "Counted quantities cannot be negative.")
                        return redirect("staff-inventory-count-detail", session_id=sess.id)
                resolved.append({"menu_item": mi, "counted_quantity": counted})

            try:
                complete_stock_count_session(
                    session=sess,
                    resolved_lines=resolved,
                    user=request.user,
                    membership=request.tenant_membership,
                )
            except DRFValidationError as e:
                _flash_drf_validation(request, e)
            else:
                messages.success(request, "Stock take completed and ledger updated.")
            return redirect("staff-inventory-count-detail", session_id=sess.id)

        messages.error(request, "Unknown action.")
        return redirect("staff-inventory-count-detail", session_id=sess.id)
