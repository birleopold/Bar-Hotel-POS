"""Printable retail shelf/price labels using the existing catalog and outlet prices."""
from __future__ import annotations

from io import BytesIO
import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import ListView

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from apps.catalog.label_queue import (
    dismiss_product_label_entries,
    mark_product_labels_printed,
    queue_product_label,
)
from apps.catalog.models import MenuItem, ProductLabelQueueEntry
from apps.pos.services.menu import menu_items_for_outlet_queryset
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets
from .services.permissions import membership_has_inventory_capability


MAX_LABELS_PER_PDF = 120
LABEL_TEMPLATES = {
    "shelf": "Shelf / price",
    "product": "Product identity",
    "markdown": "Markdown",
    "receiving": "Receiving",
}


class StaffShelfLabelView(StaffTenantRequiredMixin, ListView):
    """Select current catalog items and print generic A4 shelf labels."""

    staff_nav_capability = "inventory"
    template_name = "staff/inventory/shelf_labels.html"
    context_object_name = "label_items"
    paginate_by = 60
    http_method_names = ["get", "post", "head", "options"]

    def _retail_outlets(self):
        return [
            outlet for outlet in staff_accessible_outlets(self.request.tenant_membership)
            if outlet.outlet_type in {OutletType.RETAIL, OutletType.SUPERMARKET}
        ]

    def _selected_outlet(self):
        outlets = self._retail_outlets()
        if not outlets:
            raise Http404
        requested = str(self.request.GET.get("outlet") or self.request.POST.get("outlet") or "").strip()
        if requested:
            return next((outlet for outlet in outlets if str(outlet.pk) == requested), None)
        return outlets[0] if len(outlets) == 1 else None

    def get_queryset(self):
        outlet = self._selected_outlet()
        if outlet is None:
            return MenuItem.objects.none()
        qs = (
            menu_items_for_outlet_queryset(self.request.tenant.pk, outlet.pk)
            .filter(is_active=True)
            .select_related("category")
            .prefetch_related("outlet_links")
            .order_by("name", "pk")
        )
        if (self.request.GET.get("queue") or "").strip() in {"1", "true", "yes"}:
            pending_ids = ProductLabelQueueEntry.objects.filter(
                tenant=self.request.tenant,
                outlet=outlet,
                status=ProductLabelQueueEntry.Status.PENDING,
            ).values_list("menu_item_id", flat=True)
            qs = qs.filter(pk__in=pending_ids)
        q = (self.request.GET.get("q") or "").strip()[:80]
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(barcode__icontains=q)
                | Q(brand__icontains=q)
                | Q(model_number__icontains=q)
                | Q(reference_code__icontains=q)
                | Q(
                    alternate_codes__code__icontains=q,
                    alternate_codes__tenant=self.request.tenant,
                    alternate_codes__is_active=True,
                )
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlet = self._selected_outlet()
        ctx["label_outlets"] = self._retail_outlets()
        ctx["label_outlet"] = outlet
        ctx["label_q"] = (self.request.GET.get("q") or "").strip()[:80]
        ctx["label_queue_only"] = (self.request.GET.get("queue") or "").strip() in {"1", "true", "yes"}
        requested_template = (
            self.request.GET.get("template")
            or self.request.POST.get("template")
            or "shelf"
        ).strip()
        ctx["label_template"] = requested_template if requested_template in LABEL_TEMPLATES else "shelf"
        ctx["label_templates"] = LABEL_TEMPLATES
        ctx["pending_label_count"] = 0
        ctx["pending_label_entries"] = []
        ctx["recent_label_history"] = []
        ctx["can_manage_label_queue"] = membership_has_inventory_capability(
            self.request.tenant_membership, "adjust"
        )
        if outlet:
            pending = list(
                ProductLabelQueueEntry.objects.filter(
                    tenant=self.request.tenant,
                    outlet=outlet,
                    status=ProductLabelQueueEntry.Status.PENDING,
                ).select_related("menu_item").order_by("-created_at")
            )
            ctx["pending_label_count"] = len(pending)
            ctx["pending_label_entries"] = pending
            ctx["recent_label_history"] = list(
                ProductLabelQueueEntry.objects.filter(
                    tenant=self.request.tenant,
                    outlet=outlet,
                    status__in=[
                        ProductLabelQueueEntry.Status.PRINTED,
                        ProductLabelQueueEntry.Status.DISMISSED,
                    ],
                )
                .select_related("menu_item", "completed_by")
                .order_by("-completed_at", "-updated_at")[:20]
            )
            reasons_by_item = {}
            for entry in pending:
                reasons_by_item.setdefault(entry.menu_item_id, []).append(entry.get_reason_display())
            for item in ctx["label_items"]:
                item.label_price = item.unit_price_for_outlet(outlet.pk)
                item.label_queue_reasons = reasons_by_item.get(item.pk, [])
        return ctx

    def post(self, request, *args, **kwargs):
        outlet = self._selected_outlet()
        if outlet is None:
            messages.error(request, "Choose the retail outlet whose prices should be printed.")
            return redirect(reverse("staff-inventory-shelf-labels"))

        action = (request.POST.get("action") or "print").strip()
        if action in {"manual_queue", "dismiss_queue"} and not membership_has_inventory_capability(
            request.tenant_membership, "adjust"
        ):
            messages.error(request, "Your role cannot manage the merchandise label queue.")
            return self._return_to_list(request, outlet)

        if action == "manual_queue":
            item_raw = (request.POST.get("manual_item_id") or "").strip()
            try:
                item_id = uuid.UUID(item_raw)
            except (TypeError, ValueError):
                messages.error(request, "Choose a valid product for the label request.")
                return self._return_to_list(request, outlet)
            item = (
                menu_items_for_outlet_queryset(request.tenant.pk, outlet.pk)
                .filter(pk=item_id, is_active=True)
                .first()
            )
            if item is None:
                messages.error(request, "Choose an active product available at this outlet.")
                return self._return_to_list(request, outlet)
            entry = queue_product_label(
                tenant_id=request.tenant.pk,
                outlet=outlet,
                menu_item=item,
                reason=ProductLabelQueueEntry.Reason.MANUAL,
                user=request.user,
                note=(request.POST.get("queue_note") or "Manual shelf-label request").strip(),
            )
            if entry is None:
                messages.error(request, "This outlet does not support retail merchandise labels.")
            else:
                messages.success(request, f"Queued a shelf label for {item.name}.")
            return self._return_to_list(request, outlet)

        if action == "dismiss_queue":
            raw_entry_ids = request.POST.getlist("queue_entry_ids")
            try:
                entry_ids = [uuid.UUID(value) for value in raw_entry_ids]
            except (TypeError, ValueError):
                messages.error(request, "Choose valid pending label tasks to dismiss.")
                return self._return_to_list(request, outlet)
            changed = dismiss_product_label_entries(
                tenant_id=request.tenant.pk,
                outlet=outlet,
                entry_ids=entry_ids,
                user=request.user,
                note=(request.POST.get("dismiss_note") or "Dismissed from shelf-label queue").strip(),
            )
            if changed:
                messages.success(
                    request,
                    f"Dismissed {changed} label task{'s' if changed != 1 else ''}.",
                )
            else:
                messages.info(request, "No pending label tasks were changed.")
            return self._return_to_list(request, outlet)

        if action != "print":
            messages.error(request, "Unknown label action.")
            return self._return_to_list(request, outlet)

        selected_ids = request.POST.getlist("item_ids")
        allowed = {
            str(item.pk): item
            for item in (
                menu_items_for_outlet_queryset(request.tenant.pk, outlet.pk)
                .filter(pk__in=selected_ids, is_active=True)
                .select_related("category")
                .prefetch_related("outlet_links")
            )
        }
        labels = []
        for raw_id in selected_ids:
            item = allowed.get(str(raw_id))
            if item is None:
                continue
            try:
                copies = int(request.POST.get(f"copies_{item.pk}", "1"))
            except (TypeError, ValueError):
                copies = 1
            if copies < 1 or copies > 20:
                messages.error(request, "Copies per item must be between 1 and 20.")
                return self._return_to_list(request, outlet)
            labels.extend([item] * copies)
            if len(labels) > MAX_LABELS_PER_PDF:
                messages.error(request, f"Print at most {MAX_LABELS_PER_PDF} labels at a time.")
                return self._return_to_list(request, outlet)

        if not labels:
            messages.error(request, "Select at least one product to print.")
            return self._return_to_list(request, outlet)

        template_key = (request.POST.get("template") or "shelf").strip()
        if template_key not in LABEL_TEMPLATES:
            messages.error(request, "Choose a supported label template.")
            return self._return_to_list(request, outlet)
        pdf = self._build_pdf(labels, outlet, template_key)
        queue_reason = None
        if template_key == "markdown":
            queue_reason = ProductLabelQueueEntry.Reason.MARKDOWN
        elif template_key == "receiving":
            queue_reason = ProductLabelQueueEntry.Reason.RECEIVING
        mark_product_labels_printed(
            tenant_id=request.tenant.pk,
            outlet=outlet,
            menu_item_ids=[item.pk for item in labels],
            user=request.user,
            reason=queue_reason,
        )
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{template_key}-labels.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response

    def _return_to_list(self, request, outlet):
        query = {"outlet": str(outlet.pk)}
        q = (request.POST.get("return_q") or "").strip()[:80]
        if q:
            query["q"] = q
        if (request.POST.get("return_queue") or "").strip() in {"1", "true", "yes"}:
            query["queue"] = "1"
        template_key = (request.POST.get("template") or "").strip()
        if template_key in LABEL_TEMPLATES and template_key != "shelf":
            query["template"] = template_key
        return redirect(reverse("staff-inventory-shelf-labels") + "?" + urlencode(query))

    def _build_pdf(self, labels, outlet, template_key="shelf"):
        output = BytesIO()
        canvas = Canvas(output, pagesize=A4)
        page_w, page_h = A4
        cols, rows = 3, 8
        margin_x, margin_y = 7 * mm, 8 * mm
        gap_x, gap_y = 2 * mm, 2 * mm
        cell_w = (page_w - (2 * margin_x) - ((cols - 1) * gap_x)) / cols
        cell_h = (page_h - (2 * margin_y) - ((rows - 1) * gap_y)) / rows
        currency = getattr(request_settings := getattr(self.request.tenant, "settings", None), "default_currency", "USD")

        markdown_prices = {}
        if template_key == "markdown":
            pending_markdowns = (
                ProductLabelQueueEntry.objects.filter(
                    tenant=self.request.tenant,
                    outlet=outlet,
                    menu_item_id__in={item.pk for item in labels},
                    reason=ProductLabelQueueEntry.Reason.MARKDOWN,
                    status=ProductLabelQueueEntry.Status.PENDING,
                )
                .order_by("menu_item_id", "-updated_at")
            )
            for entry in pending_markdowns:
                markdown_prices.setdefault(entry.menu_item_id, entry.price_snapshot)

        for index, item in enumerate(labels):
            slot = index % (cols * rows)
            if slot == 0 and index:
                canvas.showPage()
            row, col = divmod(slot, cols)
            x = margin_x + col * (cell_w + gap_x)
            y = page_h - margin_y - (row + 1) * cell_h - row * gap_y
            regular_price = item.unit_price_for_outlet(outlet.pk)
            price = (
                markdown_prices.get(item.pk)
                if template_key == "markdown" and markdown_prices.get(item.pk) is not None
                else regular_price
            )
            self._draw_label(
                canvas, x, y, cell_w, cell_h, item, price, currency, outlet.name,
                template_key=template_key,
                regular_price=regular_price,
            )

        canvas.save()
        return output.getvalue()

    @staticmethod
    def _draw_label(
        canvas, x, y, width, height, item, price, currency, outlet_name,
        *, template_key="shelf", regular_price=None,
    ):
        canvas.setLineWidth(0.25)
        canvas.roundRect(x, y, width, height, 2 * mm)
        pad = 3 * mm
        code = (item.barcode or item.sku or "").strip()
        brand_model = " · ".join(
            part for part in ((item.brand or "").strip(), (item.model_number or "").strip())
            if part
        )
        reference = (item.reference_code or "").strip()
        uom = getattr(item, "get_unit_of_measure_display", lambda: item.unit_of_measure)()

        if template_key == "receiving":
            canvas.setFont("Helvetica-Bold", 6)
            canvas.drawString(x + pad, y + height - 4 * mm, "RECEIVED STOCK")
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(x + pad, y + height - 9 * mm, str(item.name)[:34])
            canvas.setFont("Helvetica", 6)
            if brand_model:
                canvas.drawString(x + pad, y + height - 13 * mm, brand_model[:50])
            canvas.drawString(
                x + pad, y + height - 17 * mm,
                f"SKU: {(item.sku or '—')} · {outlet_name}"[:55],
            )
        elif template_key == "product":
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(x + pad, y + height - 5 * mm, str(item.name)[:34])
            canvas.setFont("Helvetica", 6)
            if brand_model:
                canvas.drawString(x + pad, y + height - 9 * mm, brand_model[:50])
            if reference:
                canvas.drawString(x + pad, y + height - 13 * mm, f"Ref: {reference}"[:52])
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(x + pad, y + height - 18 * mm, f"{currency} {price}")
        elif template_key == "markdown":
            canvas.setFont("Helvetica-Bold", 6)
            canvas.drawString(x + pad, y + height - 4 * mm, "MARKDOWN")
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawString(x + pad, y + height - 8 * mm, str(item.name)[:34])
            was_price = regular_price
            if was_price is None or was_price <= price:
                was_price = item.msrp if item.msrp is not None and item.msrp > price else None
            if was_price is not None and was_price > price:
                canvas.setFont("Helvetica", 7)
                canvas.drawString(x + pad, y + height - 13 * mm, f"Was {currency} {was_price}")
            canvas.setFont("Helvetica-Bold", 16)
            canvas.drawString(x + pad, y + height - 19 * mm, f"Now {currency} {price}")
        else:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawString(x + pad, y + height - 5 * mm, str(item.name)[:34])
            canvas.setFont("Helvetica-Bold", 15)
            canvas.drawString(x + pad, y + height - 12 * mm, f"{currency} {price}")
            canvas.setFont("Helvetica", 6)
            canvas.drawString(x + pad, y + height - 16 * mm, f"{uom} · {outlet_name}"[:52])

        if code:
            available = width - 2 * pad
            bar = Code128(code, barHeight=7 * mm, barWidth=0.23 * mm, humanReadable=False)
            if bar.width > available:
                bar.barWidth *= available / bar.width
            bar.drawOn(canvas, x + pad, y + 6 * mm)
            canvas.setFont("Helvetica", 6)
            canvas.drawCentredString(x + width / 2, y + 3.4 * mm, code[:45])
        else:
            canvas.setFont("Helvetica-Oblique", 6)
            canvas.drawString(x + pad, y + 5 * mm, "No barcode or SKU stored")
