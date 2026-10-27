from decimal import Decimal

from django import forms
from django.db.models import QuerySet

from apps.catalog.models import MenuCategory, MenuItem
from apps.inventory.models import StockReason
from apps.tenants.models import Outlet

_STAFF_STOCK_REASONS = [
    (StockReason.RECEIVE.value, "Stock receive / purchase"),
    (StockReason.ADJUST_IN.value, "Adjustment increase"),
    (StockReason.ADJUST_OUT.value, "Adjustment decrease"),
    (StockReason.WASTE.value, "Waste / shrink"),
]


class StaffStockMovementForm(forms.Form):
    outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.none(),
        empty_label="Select tracked item",
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    reason = forms.ChoiceField(
        choices=_STAFF_STOCK_REASONS,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    quantity = forms.DecimalField(
        max_digits=14,
        decimal_places=3,
        min_value=Decimal("0.001"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001"}),
        help_text="Enter a positive amount. Adjust-out and waste are stored as negative movement.",
    )
    note = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    approval_request_key = forms.UUIDField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(
        self,
        *args,
        menu_items_qs: QuerySet | None = None,
        outlets: list | None = None,
        default_outlet=None,
        approvers=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        from .pos_orders import _add_sensitive_approval_fields
        _add_sensitive_approval_fields(self, approvers, required=False)
        if "approver_id" in self.fields:
            self.fields["approver_id"].help_text = "Required only for adjustment decrease or waste."
            self.fields["approver_pin"].help_text = "Required only for adjustment decrease or waste."
        if outlets is not None:
            self.fields["outlet"].queryset = Outlet.objects.filter(
                pk__in=[o.id for o in outlets],
                is_active=True,
            ).select_related("site")
        if menu_items_qs is not None:
            self.fields["menu_item"].queryset = menu_items_qs
            self.fields["menu_item"].label_from_instance = lambda item: (
                f"{item.name} ({item.units_per_carton} pieces per carton)"
                if item.units_per_carton > 1 else item.name
            )
            if not menu_items_qs.exists():
                self.fields["menu_item"].empty_label = "No tracked items available"
                self.fields["menu_item"].help_text = (
                    "No active items with inventory tracking are available yet. "
                    "Create/edit an item and enable inventory tracking first."
                )
        if default_outlet is not None and "outlet" not in self.initial:
            self.initial["outlet"] = default_outlet.pk
        self.fields["outlet"].label = "Section"

    def clean(self):
        cleaned = super().clean()
        reason = cleaned.get("reason")
        if reason in {StockReason.ADJUST_OUT.value, StockReason.WASTE.value}:
            note = (cleaned.get("note") or "").strip()
            if not note:
                self.add_error("note", "Explain the stock decrease or waste.")
            if not cleaned.get("approval_request_key"):
                self.add_error(None, "Approval request identity is missing. Reload the form and try again.")
            if "approver_id" not in self.fields:
                self.add_error(None, "A different PIN-enabled manager is required for this stock write-off.")
            else:
                if not cleaned.get("approver_id"):
                    self.add_error("approver_id", "Select a different manager to approve this stock write-off.")
                if not cleaned.get("approver_pin"):
                    self.add_error("approver_pin", "Enter the approving manager's PIN.")
        return cleaned


class StaffStockTransferForm(forms.Form):
    from_outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    to_outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    quantity = forms.DecimalField(
        label="Loose units", max_digits=14, decimal_places=3, min_value=Decimal("0"),
        required=False,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0"}),
    )
    cartons = forms.IntegerField(
        label="Whole cartons (optional)", min_value=1, required=False,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "1", "min": "1"}),
    )
    needed_by = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
        help_text="Optional date the receiving section needs this stock.",
    )
    note = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )

    def __init__(
        self,
        *args,
        outlets: list | None = None,
        from_outlets: list | None = None,
        to_outlets: list | None = None,
        menu_items_qs: QuerySet | None = None,
        request_mode: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if outlets is not None:
            from_outlets = from_outlets if from_outlets is not None else outlets
            to_outlets = to_outlets if to_outlets is not None else outlets
        if from_outlets is not None:
            self.fields["from_outlet"].queryset = Outlet.objects.filter(
                pk__in=[o.id for o in from_outlets], is_active=True
            ).select_related("site")
        if to_outlets is not None:
            self.fields["to_outlet"].queryset = Outlet.objects.filter(
                pk__in=[o.id for o in to_outlets], is_active=True
            ).select_related("site")
        if menu_items_qs is not None:
            self.fields["menu_item"].queryset = menu_items_qs
        self.fields["from_outlet"].label = (
            "Request stock from" if request_mode else "From section"
        )
        self.fields["to_outlet"].label = (
            "Receiving section" if request_mode else "To section"
        )
        if request_mode:
            self.fields["note"].label = "Request note"
            self.fields["note"].widget.attrs["placeholder"] = (
                "Why this stock is needed or any transfer instructions"
            )
        else:
            self.fields.pop("needed_by", None)

    def clean(self):
        data = super().clean()
        f = data.get("from_outlet")
        t = data.get("to_outlet")
        if f and t and f.id == t.id:
            raise forms.ValidationError("Source and destination sections must differ.")
        if data.get("menu_item") is not None:
            from apps.catalog.packaging import to_stock_units
            from rest_framework.exceptions import ValidationError as DRFValidationError
            try:
                data["quantity"] = to_stock_units(
                    units=data.get("quantity") or 0,
                    cartons=data.get("cartons") or 0,
                    units_per_carton=data["menu_item"].units_per_carton,
                )
            except DRFValidationError as exc:
                raise forms.ValidationError(str(exc.detail)) from exc
        return data


class StaffStockCountSessionForm(forms.Form):
    outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    note = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
    )

    def __init__(self, *args, outlets_qs: QuerySet | None = None, default_outlet=None, **kwargs):
        super().__init__(*args, **kwargs)
        if outlets_qs is not None:
            self.fields["outlet"].queryset = outlets_qs
        if default_outlet is not None and "outlet" not in self.initial:
            self.initial["outlet"] = default_outlet.pk
        self.fields["outlet"].label = "Section"


class StaffStockMovementUploadForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "staff-input", "accept": ".csv,text/csv"}),
        help_text="CSV columns: outlet, menu_item, sku, barcode, reason, quantity, note",
    )
    default_outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "staff-input"}),
        help_text="Optional fallback outlet when CSV row has no outlet value.",
    )
    default_reason = forms.ChoiceField(
        choices=_STAFF_STOCK_REASONS,
        required=False,
        widget=forms.Select(attrs={"class": "staff-input"}),
        help_text="Optional fallback reason when CSV row has no reason value.",
    )

    def __init__(self, *args, outlets: list | None = None, default_outlet=None, **kwargs):
        super().__init__(*args, **kwargs)
        if outlets is not None:
            self.fields["default_outlet"].queryset = Outlet.objects.filter(
                pk__in=[o.id for o in outlets],
                is_active=True,
            ).select_related("site")
        if default_outlet is not None and "default_outlet" not in self.initial:
            self.initial["default_outlet"] = default_outlet.pk

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        name = (f.name or "").lower()
        if not name.endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        return f


class StaffQuickTrackedMenuItemForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=MenuCategory.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
    )
    sku = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    barcode = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = MenuCategory.objects.filter(
                tenant=tenant,
                is_active=True,
            ).order_by("sort_order", "name")
