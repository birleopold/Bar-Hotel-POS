from django import forms
from django.db.models import Q

from apps.accounts.models import CommissionRule, Membership, SalesTarget
from apps.catalog.models import MenuCategory, MenuItem


class StaffCommissionRuleForm(forms.ModelForm):
    class Meta:
        model = CommissionRule
        fields = [
            "name",
            "membership",
            "menu_item",
            "category",
            "rate_percent",
            "effective_from",
            "effective_to",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "membership": forms.Select(attrs={"class": "staff-input"}),
            "menu_item": forms.Select(attrs={"class": "staff-input"}),
            "category": forms.Select(attrs={"class": "staff-input"}),
            "rate_percent": forms.NumberInput(
                attrs={"class": "staff-input", "min": "0", "max": "100", "step": "0.01"}
            ),
            "effective_from": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "effective_to": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is None:
            self.fields["membership"].queryset = Membership.objects.none()
            self.fields["menu_item"].queryset = MenuItem.objects.none()
            self.fields["category"].queryset = MenuCategory.objects.none()
            return
        self.fields["membership"].queryset = (
            Membership.objects.filter(
                tenant=tenant,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .order_by("user__email")
        )
        self.fields["menu_item"].queryset = (
            MenuItem.objects.filter(tenant=tenant, is_active=True)
            .order_by("name")
        )
        self.fields["category"].queryset = (
            MenuCategory.objects.filter(tenant=tenant, is_active=True)
            .order_by("name")
        )
        self.fields["membership"].required = False
        self.fields["menu_item"].required = False
        self.fields["category"].required = False
        self.fields["membership"].empty_label = "Any worker"
        self.fields["menu_item"].empty_label = "Any product"
        self.fields["category"].empty_label = "Any category"

    def clean_rate_percent(self):
        rate = self.cleaned_data.get("rate_percent")
        if rate is None or rate < 0 or rate > 100:
            raise forms.ValidationError("Commission rate must be between 0% and 100%.")
        return rate

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        qs = CommissionRule.objects.filter(tenant=self._tenant, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A commission rule with this name already exists.")
        return name

    def clean(self):
        data = super().clean()
        membership = data.get("membership")
        item = data.get("menu_item")
        category = data.get("category")
        if membership and membership.tenant_id != getattr(self._tenant, "pk", None):
            raise forms.ValidationError({"membership": "Choose a worker from this workspace."})
        if item and item.tenant_id != getattr(self._tenant, "pk", None):
            raise forms.ValidationError({"menu_item": "Choose a product from this workspace."})
        if category and category.tenant_id != getattr(self._tenant, "pk", None):
            raise forms.ValidationError({"category": "Choose a category from this workspace."})
        if item and category:
            raise forms.ValidationError(
                "Choose a product or a category for one rule, not both. "
                "Use separate rules when both are needed."
            )
        start = data.get("effective_from")
        end = data.get("effective_to")
        if start and end and end < start:
            raise forms.ValidationError(
                {"effective_to": "End date must be on or after the start date."}
            )
        if data.get("is_active") and self._tenant is not None:
            same_scope = CommissionRule.objects.filter(
                tenant=self._tenant,
                is_active=True,
                membership=membership,
                menu_item=item,
                category=category,
            )
            if self.instance.pk:
                same_scope = same_scope.exclude(pk=self.instance.pk)
            if start:
                same_scope = same_scope.filter(
                    Q(effective_to__isnull=True) | Q(effective_to__gte=start)
                )
            if end:
                same_scope = same_scope.filter(
                    Q(effective_from__isnull=True) | Q(effective_from__lte=end)
                )
            if same_scope.exists():
                raise forms.ValidationError(
                    "An active commission rule with the same worker/product/category scope "
                    "already overlaps this effective period."
                )
        return data


class StaffSalesTargetForm(forms.ModelForm):
    class Meta:
        model = SalesTarget
        fields = ["membership", "period_start", "period_end", "target_amount", "note"]
        widgets = {
            "membership": forms.Select(attrs={"class": "staff-input"}),
            "period_start": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "period_end": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "target_amount": forms.NumberInput(
                attrs={"class": "staff-input", "min": "0", "step": "0.01"}
            ),
            "note": forms.TextInput(attrs={"class": "staff-input"}),
        }

    def __init__(self, *args, tenant=None, memberships=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if memberships is None:
            memberships = Membership.objects.none()
        self.fields["membership"].queryset = memberships

    def clean(self):
        data = super().clean()
        membership = data.get("membership")
        start = data.get("period_start")
        end = data.get("period_end")
        if membership and membership.tenant_id != getattr(self._tenant, "pk", None):
            raise forms.ValidationError({"membership": "Choose a worker in your scope."})
        if start and end:
            if end < start:
                raise forms.ValidationError({"period_end": "End date must be on or after start date."})
            if (end - start).days > 366:
                raise forms.ValidationError({"period_end": "A target period cannot exceed 367 days."})
        if membership and start and end:
            overlap = SalesTarget.objects.filter(
                tenant=self._tenant,
                membership=membership,
                period_start__lte=end,
                period_end__gte=start,
            )
            if self.instance.pk:
                overlap = overlap.exclude(pk=self.instance.pk)
            if overlap.exists():
                raise forms.ValidationError(
                    "This worker already has a sales target overlapping that period."
                )
        return data
