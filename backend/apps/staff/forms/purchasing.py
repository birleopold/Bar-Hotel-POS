from django import forms
from django.db.models import QuerySet

from apps.purchasing.models import Supplier
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
