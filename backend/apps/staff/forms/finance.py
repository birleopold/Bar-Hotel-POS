from __future__ import annotations

from django import forms

from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind


class StaffFinanceCategoryForm(forms.ModelForm):
    class Meta:
        model = FinanceCategory
        fields = ("name", "kind")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input", "placeholder": "e.g. Utilities"}),
            "kind": forms.Select(attrs={"class": "staff-input"}),
        }

    def __init__(self, *args, tenant_id, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant_id = tenant_id

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tenant_id = self._tenant_id
        if commit:
            obj.save()
        return obj


class StaffCashbookEntryForm(forms.ModelForm):
    class Meta:
        model = CashbookEntry
        fields = ("category", "site", "amount", "transaction_date", "reference", "note")
        widgets = {
            "category": forms.Select(attrs={"class": "staff-input"}),
            "site": forms.Select(attrs={"class": "staff-input"}),
            "amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0.01"}),
            "transaction_date": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "reference": forms.TextInput(attrs={"class": "staff-input", "placeholder": "Optional ref."}),
            "note": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
        }

    def __init__(self, *args, tenant_id, sites, categories, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = categories
        self.fields["site"].queryset = sites
        self.fields["site"].required = False
        self.fields["site"].empty_label = "All branches / unallocated"
        self.fields["site"].label = "Branch"
        self._tenant_id = tenant_id

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tenant_id = self._tenant_id
        if commit:
            obj.save()
        return obj
