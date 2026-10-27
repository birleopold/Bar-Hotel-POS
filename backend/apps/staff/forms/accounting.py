from django import forms

from apps.catalog.models import MenuCategory
from apps.finance.models import AccountingMapping, AccountingMappingKind
from apps.pos.models import PaymentMethod


CATEGORY_KINDS = {
    AccountingMappingKind.REVENUE_CATEGORY,
    AccountingMappingKind.INVENTORY_CATEGORY,
    AccountingMappingKind.COGS_CATEGORY,
}
DEFAULT_KINDS = {
    AccountingMappingKind.REVENUE_DEFAULT,
    AccountingMappingKind.RETURNS,
    AccountingMappingKind.TAX_LIABILITY,
    AccountingMappingKind.INVENTORY_DEFAULT,
    AccountingMappingKind.COGS_DEFAULT,
}


class StaffAccountingMappingForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=MenuCategory.objects.none(),
        required=False,
        empty_label="Choose category",
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    tender_method = forms.ChoiceField(
        required=False,
        choices=[("", "Choose tender")] + list(PaymentMethod.choices),
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    class Meta:
        model = AccountingMapping
        fields = ["kind", "account_code", "account_name", "is_active"]
        widgets = {
            "kind": forms.Select(attrs={"class": "staff-input"}),
            "account_code": forms.TextInput(attrs={"class": "staff-input"}),
            "account_name": forms.TextInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self.fields["category"].queryset = (
            MenuCategory.objects.filter(tenant=tenant, is_active=True).order_by("name")
            if tenant is not None else MenuCategory.objects.none()
        )
        if self.instance.pk:
            if self.instance.kind in CATEGORY_KINDS and self.instance.source_key:
                self.fields["category"].initial = self.instance.source_key
            if self.instance.kind == AccountingMappingKind.TENDER:
                self.fields["tender_method"].initial = self.instance.source_key

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        category = data.get("category")
        tender = data.get("tender_method")
        if kind in CATEGORY_KINDS:
            if category is None:
                raise forms.ValidationError({"category": "Choose the product category for this mapping."})
            if category.tenant_id != getattr(self._tenant, "pk", None):
                raise forms.ValidationError({"category": "Choose a category in this workspace."})
            source_key = str(category.pk)
            source_label = category.name
        elif kind == AccountingMappingKind.TENDER:
            if not tender:
                raise forms.ValidationError({"tender_method": "Choose the payment method for this mapping."})
            source_key = tender
            source_label = dict(PaymentMethod.choices).get(tender, tender)
        elif kind in DEFAULT_KINDS:
            source_key = ""
            source_label = ""
        else:
            raise forms.ValidationError({"kind": "Choose a supported accounting mapping type."})

        if self._tenant is not None:
            duplicate = AccountingMapping.objects.filter(
                tenant=self._tenant,
                kind=kind,
                source_key=source_key,
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError(
                    "A mapping already exists for this type and source."
                )
        data["_source_key"] = source_key
        data["_source_label"] = source_label
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.source_key = self.cleaned_data["_source_key"]
        obj.source_label = self.cleaned_data["_source_label"]
        if commit:
            obj.save()
        return obj
