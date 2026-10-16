"""Owner-facing catalog import and a downloadable example CSV."""
import csv

from django import forms
from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect
from django.http import Http404
from apps.tenants.business_lines import normalize_business_lines
from django.urls import reverse
from django.views.generic import FormView

from apps.audit.services import log_audit
from apps.catalog.models import MenuItem

from .catalog_import import (CatalogImportProblem, import_catalog_items, parse_catalog_csv,
    parse_price_update_csv, apply_price_updates)
from .mixins import ConsoleOrgAdminRequiredMixin


def _spreadsheet_safe(value):
    """Prevent imported product text from executing as a spreadsheet formula."""
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


class CatalogUploadForm(forms.Form):
    file = forms.FileField(
        label="CSV file",
        widget=forms.ClearableFileInput(attrs={"class": "staff-input", "accept": ".csv,text/csv"}),
        help_text="UTF-8 CSV, up to 1 MB and 1,000 products per import.",
    )


class OrgCatalogImportView(ConsoleOrgAdminRequiredMixin, FormView):
    template_name = "console/org/catalog_import.html"
    form_class = CatalogUploadForm

    def dispatch(self, request, *args, **kwargs):
        from apps.tenants.models import TenantSettings
        try:
            lines = normalize_business_lines(request.tenant.settings.business_lines)
        except TenantSettings.DoesNotExist:
            lines = []
        if lines and not set(lines) & {
            "retail", "supermarket", "bar", "lounge", "restaurant",
            "cafeteria", "kitchen",
        }:
            raise Http404("Product catalog import is not enabled for this business type.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if request.GET.get("price_template") == "1":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="price-updates.csv"'
            response["Cache-Control"] = "private, no-store"
            writer = csv.writer(response)
            writer.writerow(["sku", "old_price", "new_price"])
            for item in MenuItem.objects.filter(
                tenant=request.tenant,
            ).exclude(sku="").order_by("sku").iterator(chunk_size=500):
                writer.writerow([
                    _spreadsheet_safe(item.sku), item.unit_price, item.unit_price,
                ])
            return response
        if request.GET.get("export") == "1":
            # Owner-only, tenant-scoped export for review before catalog changes.
            # Export product metadata only, never stock quantities or sales.
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="catalog-current.csv"'
            response["Cache-Control"] = "private, no-store"
            writer = csv.writer(response)
            writer.writerow([
                "category", "name", "unit_price", "sku", "barcode",
                "track_inventory", "reorder_level", "unit_of_measure",
                "tax_rate_percent", "description",
            ])
            items = MenuItem.objects.filter(
                tenant=request.tenant,
            ).select_related("category").order_by("name", "pk")
            for item in items.iterator(chunk_size=500):
                writer.writerow([
                    _spreadsheet_safe(item.category.name), _spreadsheet_safe(item.name), item.unit_price,
                    _spreadsheet_safe(item.sku), _spreadsheet_safe(item.barcode), "yes" if item.track_inventory else "no",
                    item.reorder_level if item.reorder_level is not None else "",
                    item.unit_of_measure,
                    item.tax_rate_percent if item.tax_rate_percent is not None else "",
                    _spreadsheet_safe(item.description),
                ])
            return response
        if request.GET.get("sample") == "1":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="catalog-example.csv"'
            writer = csv.writer(response)
            writer.writerow([
                "category", "name", "unit_price", "sku", "barcode",
                "track_inventory", "reorder_level", "unit_of_measure",
                "tax_rate_percent", "description",
            ])
            writer.writerow([
                "Drinks", "Bottled Water 500ml", "1500.00", "WATER-500",
                "6001234567890", "yes", "12", "each", "0", "Sample only",
            ])
            writer.writerow([
                "Services", "Laundry Service", "12000.00", "LAUNDRY-01",
                "", "no", "", "each", "", "Sample only",
            ])
            response["Cache-Control"] = "private, no-store"
            return response
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        action = (self.request.POST.get("action") or "").strip()
        if action in {"preview_prices", "apply_prices"}:
            try:
                rows = parse_price_update_csv(
                    tenant=self.request.tenant, uploaded=form.cleaned_data["file"],
                )
                if action == "preview_prices":
                    return self.render_to_response(self.get_context_data(
                        form=CatalogUploadForm(),
                        price_preview_count=len(rows),
                        price_preview_rows=rows[:25],
                        price_preview_more=max(0, len(rows) - 25),
                    ))
                if self.request.POST.get("confirm_price_changes") != "yes":
                    raise CatalogImportProblem(["Confirm that you reviewed the new prices before applying them."])
                changed = apply_price_updates(
                    tenant=self.request.tenant, rows=rows, user=self.request.user,
                )
            except CatalogImportProblem as exc:
                return self.render_to_response(self.get_context_data(
                    form=CatalogUploadForm(), import_issues=exc.issues,
                ))
            messages.success(
                self.request,
                f"Updated {changed} base prices. Stock and past receipts were not changed.",
            )
            return redirect("console-org-menu-items")
        try:
            rows = parse_catalog_csv(
                tenant=self.request.tenant, uploaded=form.cleaned_data["file"],
            )
            action = (self.request.POST.get("action") or "").strip()
            if action == "preview":
                return self.render_to_response(self.get_context_data(
                    form=CatalogUploadForm(),
                    preview_count=len(rows),
                    preview_rows=rows[:15],
                    preview_more=max(0, len(rows)-15),
                ))
            if action != "import":
                form.add_error(None, "Choose Check file or Import items.")
                return self.form_invalid(form)
            count = import_catalog_items(tenant=self.request.tenant, rows=rows)
        except CatalogImportProblem as exc:
            return self.render_to_response(self.get_context_data(
                form=CatalogUploadForm(),
                import_issues=exc.issues,
            ))
        except IntegrityError:
            form.add_error(None, "Another catalog change was saved. Refresh the file and retry.")
            return self.form_invalid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="catalog.csv_items_imported",
            entity_type="menu_items", entity_id=str(self.request.tenant.pk),
            payload={"count": count, "source": "setup_csv"},
        )
        messages.success(self.request, f"Imported {count} items. Stock quantities have not been changed.")
        return redirect("console-org-menu-items")
