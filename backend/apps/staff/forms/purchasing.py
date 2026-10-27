from django import forms
from django.db.models import QuerySet

from apps.catalog.models import MenuItem, ProductPackage
from apps.purchasing.models import Supplier, SupplierProductCode
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
        fields = ["menu_item", "product_package", "code", "description", "is_active"]
        widgets = {
            "menu_item": forms.Select(attrs={"class": "staff-input"}),
            "product_package": forms.Select(attrs={"class": "staff-input"}),
            "code": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.TextInput(attrs={"class": "staff-input"}),
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
