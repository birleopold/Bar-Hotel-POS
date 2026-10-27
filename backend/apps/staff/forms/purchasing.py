from django import forms
from django.db.models import QuerySet

from apps.catalog.models import MenuItem, ProductPackage
from apps.purchasing.models import Supplier, SupplierPriceRecord, SupplierProductCode
from apps.tenants.models import Outlet


class StaffSupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "email", "phone", "address_line", "notes", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "email": forms.EmailInput(attrs={"class": "staff-input"}),
            "phone": forms.TextInput(attrs={"class": "staff-input"}),
            "address_line": forms.TextInput(attrs={"class": "staff-input"}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
            "is_active": forms.CheckboxInput(),
        }


class StaffSupplierProductCodeForm(forms.ModelForm):
    class Meta:
        model = SupplierProductCode
        fields = [
            "menu_item", "product_package", "code", "description",
            "default_unit_cost", "minimum_order_quantity", "expected_lead_days",
            "is_preferred", "is_active",
        ]
        widgets = {
            "menu_item": forms.Select(attrs={"class": "staff-input"}),
            "product_package": forms.Select(attrs={"class": "staff-input"}),
            "code": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.TextInput(attrs={"class": "staff-input"}),
            "default_unit_cost": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0", "step": "0.01",
                "placeholder": "Optional cost per base unit",
            }),
            "minimum_order_quantity": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0.001", "step": "0.001",
                "placeholder": "Optional base-unit minimum",
            }),
            "expected_lead_days": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0", "step": "1",
                "placeholder": "Optional days",
            }),
            "is_preferred": forms.CheckboxInput(),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, supplier, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.supplier = supplier
        self.fields["menu_item"].queryset = MenuItem.objects.filter(
            tenant=tenant, is_active=True, track_inventory=True
        ).order_by("name")
        self.fields["product_package"].queryset = ProductPackage.objects.filter(
            tenant=tenant, is_active=True, is_purchasable=True
        ).select_related("menu_item").order_by("menu_item__name", "name")
        self.fields["product_package"].required = False

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise forms.ValidationError("Enter the supplier's product or package code.")
        qs = SupplierProductCode.objects.filter(supplier=self.supplier, code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This supplier code is already in use.")
        return code

    def clean(self):
        data = super().clean()
        item = data.get("menu_item")
        package = data.get("product_package")
        if item and item.tenant_id != self.tenant.pk:
            self.add_error("menu_item", "Choose a product from this business.")
        if data.get("is_preferred") and package:
            self.add_error(
                "is_preferred",
                "Set preferred supplier on the base product relationship, not a package-specific code.",
            )
        if data.get("is_preferred") and item:
            existing = SupplierProductCode.objects.filter(
                tenant=self.tenant,
                menu_item=item,
                is_preferred=True,
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error(
                    "is_preferred",
                    "Another supplier is already preferred for this product. Clear it there first.",
                )
        if package:
            if package.tenant_id != self.tenant.pk:
                self.add_error("product_package", "Choose a package from this business.")
            elif item and package.menu_item_id != item.pk:
                self.add_error("product_package", "Choose a package that belongs to the selected product.")
        return data


class StaffPOHeaderForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    reference = forms.CharField(
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    expected_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
        help_text="Supplier/delivery expectation. This is separate from when the business needs the stock.",
    )
    needed_by = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
        help_text="Optional business need date used during approval and prioritization.",
    )
    request_reason = forms.CharField(
        required=False,
        max_length=512,
        widget=forms.Textarea(attrs={
            "class": "staff-input",
            "rows": 2,
            "placeholder": "Optional: low stock, promotion, customer order, new branch, event…",
        }),
        help_text="Optional context for the approving manager. Keep supplier instructions in Notes.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
    )

    def __init__(self, *args, tenant=None, outlets_qs: QuerySet | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True).order_by(
                "name"
            )
        if outlets_qs is not None:
            self.fields["outlet"].queryset = outlets_qs

class StaffRfqForm(forms.Form):
    outlet = forms.ModelChoiceField(
        queryset=Outlet.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    reference = forms.CharField(
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={
            "class": "staff-input", "placeholder": "Optional; generated if blank",
        }),
    )
    needed_by = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
    )

    def __init__(self, *args, outlets_qs=None, **kwargs):
        super().__init__(*args, **kwargs)
        if outlets_qs is not None:
            self.fields["outlet"].queryset = outlets_qs


class StaffRfqInviteForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.none(),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, tenant=None, rfq=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Supplier.objects.none()
        if tenant is not None:
            qs = Supplier.objects.filter(tenant=tenant, is_active=True)
            if rfq is not None:
                qs = qs.exclude(
                    pk__in=rfq.quotes.values_list("supplier_id", flat=True)
                )
            qs = qs.order_by("name")
        self.fields["supplier"].queryset = qs


class StaffSupplierQuoteForm(forms.Form):
    reference = forms.CharField(
        required=False,
        max_length=128,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    shipping_cost = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0", "step": "0.01"}),
    )
    other_cost = forms.DecimalField(
        required=False,
        initial=0,
        min_value=0,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0", "step": "0.01"}),
    )
    lead_time_days = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=3650,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0"}),
    )
    valid_until = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
    )
    payment_terms = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    availability_note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )

class StaffSupplierPriceRecordForm(forms.ModelForm):
    class Meta:
        model = SupplierPriceRecord
        fields = [
            "menu_item", "product_package", "unit_cost", "minimum_quantity",
            "valid_from", "valid_until", "source_reference", "note", "is_active",
        ]
        widgets = {
            "menu_item": forms.Select(attrs={"class": "staff-input"}),
            "product_package": forms.Select(attrs={"class": "staff-input"}),
            "unit_cost": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0", "step": "0.01",
            }),
            "minimum_quantity": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0.001", "step": "0.001",
            }),
            "valid_from": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "valid_until": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "source_reference": forms.TextInput(attrs={
                "class": "staff-input", "placeholder": "Contract / supplier price-list reference",
            }),
            "note": forms.TextInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, supplier, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.supplier = supplier
        self.fields["menu_item"].queryset = MenuItem.objects.filter(
            tenant=tenant, is_active=True, track_inventory=True
        ).order_by("name")
        self.fields["product_package"].queryset = ProductPackage.objects.filter(
            tenant=tenant, is_active=True, is_purchasable=True
        ).select_related("menu_item").order_by("menu_item__name", "name")
        self.fields["product_package"].required = False
        self.fields["minimum_quantity"].help_text = (
            "Base-stock quantity threshold for this price."
        )

    def clean(self):
        data = super().clean()
        item = data.get("menu_item")
        package = data.get("product_package")
        valid_from = data.get("valid_from")
        valid_until = data.get("valid_until")
        if item and item.tenant_id != self.tenant.pk:
            self.add_error("menu_item", "Choose a product from this business.")
        if package:
            if package.tenant_id != self.tenant.pk:
                self.add_error("product_package", "Choose a package from this business.")
            elif item and package.menu_item_id != item.pk:
                self.add_error(
                    "product_package",
                    "Choose a package that belongs to the selected product.",
                )
        if valid_from and valid_until and valid_until < valid_from:
            self.add_error("valid_until", "End date cannot be earlier than start date.")
        return data

