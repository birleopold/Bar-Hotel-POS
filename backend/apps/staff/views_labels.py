"""Printable retail shelf/price labels using the existing catalog and outlet prices."""
from __future__ import annotations

from io import BytesIO
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

from apps.catalog.models import MenuItem
from apps.pos.services.menu import menu_items_for_outlet_queryset
from apps.tenants.models import OutletType
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


MAX_LABELS_PER_PDF = 120


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
        q = (self.request.GET.get("q") or "").strip()[:80]
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        outlet = self._selected_outlet()
        ctx["label_outlets"] = self._retail_outlets()
        ctx["label_outlet"] = outlet
        ctx["label_q"] = (self.request.GET.get("q") or "").strip()[:80]
        if outlet:
            for item in ctx["label_items"]:
                item.label_price = item.unit_price_for_outlet(outlet.pk)
        return ctx

    def post(self, request, *args, **kwargs):
        outlet = self._selected_outlet()
        if outlet is None:
            messages.error(request, "Choose the retail outlet whose prices should be printed.")
            return redirect(reverse("staff-inventory-shelf-labels"))

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

        pdf = self._build_pdf(labels, outlet)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="shelf-labels.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response

    def _return_to_list(self, request, outlet):
        query = {"outlet": str(outlet.pk)}
        q = (request.POST.get("return_q") or "").strip()[:80]
        if q:
            query["q"] = q
        return redirect(reverse("staff-inventory-shelf-labels") + "?" + urlencode(query))

    def _build_pdf(self, labels, outlet):
        output = BytesIO()
        canvas = Canvas(output, pagesize=A4)
        page_w, page_h = A4
        cols, rows = 3, 8
        margin_x, margin_y = 7 * mm, 8 * mm
        gap_x, gap_y = 2 * mm, 2 * mm
        cell_w = (page_w - (2 * margin_x) - ((cols - 1) * gap_x)) / cols
        cell_h = (page_h - (2 * margin_y) - ((rows - 1) * gap_y)) / rows
        currency = getattr(request_settings := getattr(self.request.tenant, "settings", None), "default_currency", "USD")

        for index, item in enumerate(labels):
            slot = index % (cols * rows)
            if slot == 0 and index:
                canvas.showPage()
            row, col = divmod(slot, cols)
            x = margin_x + col * (cell_w + gap_x)
            y = page_h - margin_y - (row + 1) * cell_h - row * gap_y
            price = item.unit_price_for_outlet(outlet.pk)
            self._draw_label(canvas, x, y, cell_w, cell_h, item, price, currency, outlet.name)

        canvas.save()
        return output.getvalue()

    @staticmethod
    def _draw_label(canvas, x, y, width, height, item, price, currency, outlet_name):
        canvas.setLineWidth(0.25)
        canvas.roundRect(x, y, width, height, 2 * mm)
        pad = 3 * mm
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(x + pad, y + height - 5 * mm, str(item.name)[:34])
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(x + pad, y + height - 12 * mm, f"{currency} {price}")
        canvas.setFont("Helvetica", 6)
        uom = getattr(item, "get_unit_of_measure_display", lambda: item.unit_of_measure)()
        canvas.drawString(x + pad, y + height - 16 * mm, f"{uom} · {outlet_name}"[:52])

        code = (item.barcode or "").strip()
        if code:
            available = width - 2 * pad
            bar = Code128(code, barHeight=8 * mm, barWidth=0.23 * mm, humanReadable=False)
            if bar.width > available:
                bar.barWidth *= available / bar.width
            bar.drawOn(canvas, x + pad, y + 6 * mm)
            canvas.setFont("Helvetica", 6)
            canvas.drawCentredString(x + width / 2, y + 3.4 * mm, code[:45])
        else:
            ref = (item.sku or "No barcode").strip()
            canvas.setFont("Helvetica", 7)
            canvas.drawString(x + pad, y + 7 * mm, f"SKU: {ref}"[:48])
            canvas.setFont("Helvetica-Oblique", 6)
            canvas.drawString(x + pad, y + 3.5 * mm, "No scannable barcode stored")
