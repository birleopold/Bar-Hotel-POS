"""Read-only checkout rehearsal for first-time owners.

Uses the same POS quantity and pricing helpers as real checkout; it never
creates an Order, Payment, StockMovement or EFRIS submission.
"""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.catalog.models import MenuItem
from apps.pos.services.orders import normalize_supermarket_quantity
from apps.pos.services.pricing import line_total, line_tax
from apps.tenants.models import Outlet, TenantSetupProgress
from apps.tenants.business_lines import (
    normalize_business_lines, outlet_types_for_business_lines,
)

from .mixins import ConsoleOrgAdminRequiredMixin


class PracticeSaleForm(forms.Form):
    outlet = forms.ModelChoiceField(
        label="Section or till", queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    menu_item = forms.ModelChoiceField(
        label="Item", queryset=MenuItem.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    quantity = forms.DecimalField(
        label="Quantity", min_value=Decimal("0.001"),
        max_value=Decimal("999.999"), max_digits=6, decimal_places=3,
        initial=Decimal("1"),
        widget=forms.NumberInput(attrs={
            "class": "staff-input", "step": "0.001", "min": "0.001",
        }),
    )

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            business_lines = normalize_business_lines(tenant.settings.business_lines)
        except Exception:
            business_lines = []
        allowed_types = outlet_types_for_business_lines(business_lines)
        self.fields["outlet"].queryset = Outlet.objects.filter(
            site__tenant=tenant, site__is_active=True, is_active=True,
            outlet_type__in=allowed_types,
        ).select_related("site").order_by("site__name", "name")
        self.fields["menu_item"].queryset = MenuItem.objects.filter(
            tenant=tenant, is_active=True,
        ).order_by("name")

    def clean(self):
        data = super().clean()
        outlet = data.get("outlet")
        item = data.get("menu_item")
        if outlet and item:
            links = item.outlet_links.all()
            if links.exists() and not links.filter(outlet=outlet).exists():
                self.add_error("menu_item", "This item is not offered at the chosen section.")
        return data


class OrgPracticeSaleView(ConsoleOrgAdminRequiredMixin, FormView):
    template_name = "console/org/practice_sale.html"
    form_class = PracticeSaleForm
    success_url = reverse_lazy("console-org-setup")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        progress = TenantSetupProgress.objects.filter(
            tenant=self.request.tenant,
        ).select_related("practice_sale_checked_by").first()
        ctx["practice_checked_at"] = (
            progress.practice_sale_checked_at if progress else None
        )
        ctx["practice_checked_by"] = (
            progress.practice_sale_checked_by if progress else None
        )
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        item = form.cleaned_data["menu_item"]
        outlet = form.cleaned_data["outlet"]
        quantity = form.cleaned_data["quantity"]
        try:
            quantity = normalize_supermarket_quantity(
                menu_item=item, quantity=quantity,
            )
        except DRFValidationError as exc:
            form.add_error("quantity", str(exc.detail))
            return self.form_invalid(form)

        unit_price = item.unit_price_for_outlet(outlet.pk)
        subtotal = line_total(quantity, unit_price)
        tax = line_tax(subtotal, item.tax_rate_percent)
        total = subtotal + tax

        progress, _ = TenantSetupProgress.objects.select_for_update().get_or_create(
            tenant=self.request.tenant,
        )
        progress.practice_sale_checked_at = timezone.now()
        progress.practice_sale_checked_by = self.request.user
        progress.save(update_fields=[
            "practice_sale_checked_at", "practice_sale_checked_by", "updated_at",
        ])

        messages.success(
            self.request,
            "Practice calculation complete. No payment, stock or receipt was posted.",
        )
        return render(self.request, self.template_name, self.get_context_data(
            form=PracticeSaleForm(tenant=self.request.tenant),
            result={
                "outlet": outlet, "item": item,
                "quantity": quantity, "unit_price": unit_price,
                "subtotal": subtotal, "tax": tax, "total": total,
            },
        ))
