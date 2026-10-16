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

from .catalog_import import CatalogImportProblem, import_catalog_items, parse_catalog_csv
from .mixins import ConsoleOrgAdminRequiredMixin


class CatalogUploadForm(forms.Form):
    file = forms.FileField(
        label="CSV file",
        widget=forms.ClearableFileInput(attrs={"class": "staff-input", "accept": ".csv,text/csv"}),
        help_text="UTF-8 CSV, up to 256 KB and 250 products per import.",
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
