from __future__ import annotations

from django import forms
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemOutlet,
    MenuItemRecipeLine,
    ModifierGroup,
    ModifierOption,
    ServiceOffering,
    ServiceOfferingOption,
)
from apps.lodging.models import Room, RoomRateWindow, RoomType
from apps.tenants.models import (
    BillingInvoice,
    BillingInvoiceStatus,
    Outlet,
    Plan,
    Site,
    SubscriptionStatus,
    Tenant,
    TenantSettings,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSubscription,
    staff_module_choices,
)
from apps.tenants.business_lines import BUSINESS_LINES, normalize_business_lines, outlet_types_for_business_lines


class ConsoleTenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ("name", "slug", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "slug": forms.TextInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": ""}),
        }

    def clean_slug(self):
        s = (self.cleaned_data.get("slug") or "").strip().lower()
        if not s:
            raise forms.ValidationError("Slug is required.")
        qs = Tenant.objects.filter(slug=s)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This slug is already in use.")
        return s


class ConsolePlanForm(forms.ModelForm):
    included_modules = forms.MultipleChoiceField(
        required=False,
        choices=staff_module_choices(),
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Plan
        fields = ("name", "code", "is_active", "monthly_price", "included_modules", "notes")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "code": forms.TextInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
            "monthly_price": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            raw = self.instance.included_modules if isinstance(self.instance.included_modules, list) else []
            self.fields["included_modules"].initial = [m for m in raw if m in dict(staff_module_choices())]
        self.fields["notes"].required = False


class ConsoleTenantSubscriptionForm(forms.ModelForm):
    class Meta:
        model = TenantSubscription
        fields = (
            "plan",
            "status",
            "started_at",
            "trial_ends_at",
            "current_period_ends_at",
            "cancelled_at",
        )
        widgets = {
            "plan": forms.Select(attrs={"class": "staff-input"}),
            "status": forms.Select(attrs={"class": "staff-input"}),
            "started_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "trial_ends_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "current_period_ends_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "cancelled_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True).order_by("name")
        for name in ("started_at", "trial_ends_at", "current_period_ends_at", "cancelled_at"):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        if status == SubscriptionStatus.CANCELLED and not cleaned.get("cancelled_at"):
            self.add_error("cancelled_at", "Cancelled subscriptions require a cancelled timestamp.")
        return cleaned


class ConsoleTenantEntitlementsForm(forms.Form):
    """Per-tenant module override toggles; checked means enabled override."""

    def __init__(self, *args, tenant: Tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        existing = {
            e.module_key: e.is_enabled
            for e in TenantFeatureEntitlement.objects.filter(tenant=tenant)
        }
        for key, label in staff_module_choices():
            self.fields[f"module_{key}"] = forms.BooleanField(
                required=False,
                label=label,
                initial=existing.get(key, True),
            )


class ConsoleOutletModulePolicyForm(forms.Form):
    PRESET_CHOICES = (
        ("", "Custom"),
        ("supermarket", "Supermarket template"),
        ("retail", "Retail template"),
        ("restaurant", "Restaurant template"),
        ("bar", "Bar template"),
        ("lodging", "Lodging front desk template"),
        ("events", "Event space template"),
    )
    PRESET_MAP = {
        "supermarket": ("supermarket", ["pos", "inventory", "purchasing", "promotions", "workspace"]),
        "retail": ("retail", ["pos", "inventory", "purchasing", "promotions", "workspace"]),
        "restaurant": ("restaurant", ["pos", "kitchen", "inventory", "purchasing", "promotions", "workspace"]),
        "bar": ("bar", ["pos", "kitchen", "inventory", "purchasing", "promotions", "workspace"]),
        "lodging": ("lodging_front_desk", ["lodging", "workspace", "pos"]),
        "events": ("event_space", ["events", "workspace", "pos"]),
    }

    policy_preset = forms.ChoiceField(
        required=False,
        choices=PRESET_CHOICES,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    outlet_type = forms.ChoiceField(
        choices=Outlet._meta.get_field("outlet_type").choices,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, tenant: Tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        for key, label in staff_module_choices():
            self.fields[f"module_{key}"] = forms.BooleanField(
                required=False,
                label=label,
                initial=True,
            )

    def apply_initial_from_policy(self, policy: TenantOutletModulePolicy | None) -> None:
        selected = set(policy.enabled_modules if (policy and isinstance(policy.enabled_modules, list)) else [])
        for key, _ in staff_module_choices():
            self.fields[f"module_{key}"].initial = key in selected if policy is not None else True
        self.fields["is_active"].initial = policy.is_active if policy is not None else True

    def apply_preset(self, preset_key: str) -> bool:
        preset = self.PRESET_MAP.get((preset_key or "").strip())
        if not preset:
            return False
        outlet_type, modules = preset
        selected = set(modules)
        self.fields["policy_preset"].initial = preset_key
        self.fields["outlet_type"].initial = outlet_type
        self.fields["is_active"].initial = True
        for key, _ in staff_module_choices():
            self.fields[f"module_{key}"].initial = key in selected
        return True


class ConsoleBillingInvoiceForm(forms.ModelForm):
    class Meta:
        model = BillingInvoice
        fields = (
            "invoice_number",
            "amount",
            "currency",
            "status",
            "issued_at",
            "due_at",
            "paid_at",
            "external_ref",
            "note",
        )
        widgets = {
            "invoice_number": forms.TextInput(attrs={"class": "staff-input"}),
            "amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
            "currency": forms.TextInput(attrs={"class": "staff-input", "maxlength": 3}),
            "status": forms.Select(attrs={"class": "staff-input"}),
            "issued_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "due_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "paid_at": forms.DateTimeInput(attrs={"class": "staff-input", "type": "datetime-local"}),
            "external_ref": forms.TextInput(attrs={"class": "staff-input"}),
            "note": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice_number"].help_text = "Unique per workspace."
        self.fields["currency"].initial = (self.fields["currency"].initial or "USD")
        self.fields["external_ref"].required = False
        self.fields["note"].required = False
        for field in ("issued_at", "due_at", "paid_at"):
            self.fields[field].required = False

    def clean_currency(self):
        return (self.cleaned_data.get("currency") or "USD").upper().strip()[:3]

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        if status == BillingInvoiceStatus.PAID and not cleaned.get("paid_at"):
            cleaned["paid_at"] = timezone.now()
        return cleaned


class ConsoleBillingStatusTransitionForm(forms.Form):
    target_status = forms.ChoiceField(
        choices=SubscriptionStatus.choices,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    reason = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 255, "placeholder": "Reason (optional)"}),
    )


class ConsoleBillingNoteForm(forms.Form):
    message = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 2, "placeholder": "Add billing ops note"}),
    )


class ConsoleSiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ("name", "address_line", "city", "country_code", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "address_line": forms.TextInput(attrs={"class": "staff-input"}),
            "city": forms.TextInput(attrs={"class": "staff-input"}),
            "country_code": forms.TextInput(attrs={"class": "staff-input", "maxlength": "2"}),
            "is_active": forms.CheckboxInput(),
        }


class ConsoleBusinessProfileForm(forms.Form):
    business_lines = forms.MultipleChoiceField(
        label="What does this business offer?",
        required=True,
        choices=[(key, profile.label) for key, profile in BUSINESS_LINES.items()],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "staff-checklist"}),
        help_text="Only the selected areas and their related setup, navigation, cards, and pages are shown.",
    )

    def clean_business_lines(self) -> list[str]:
        lines = normalize_business_lines(list(self.cleaned_data.get("business_lines") or []))
        if not lines:
            raise forms.ValidationError("Choose at least one service area.")
        return lines


class ConsoleOutletForm(forms.ModelForm):
    class Meta:
        model = Outlet
        fields = ("name", "outlet_type", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "outlet_type": forms.Select(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is None:
            return
        try:
            lines = normalize_business_lines(tenant.settings.business_lines)
        except TenantSettings.DoesNotExist:
            lines = []
        allowed = set(outlet_types_for_business_lines(lines))
        self.fields["outlet_type"].choices = [
            choice
            for choice in self.fields["outlet_type"].choices
            if str(choice[0]) in allowed
        ]


class ConsoleRoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ("site", "name", "description", "max_occupancy", "is_active")
        widgets = {
            "site": forms.Select(attrs={"class": "staff-input"}),
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "max_occupancy": forms.NumberInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, allowed_site_ids: list, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        qs = Site.objects.filter(tenant=tenant, pk__in=allowed_site_ids).order_by("name")
        self.fields["site"].queryset = qs
        if qs.count() == 1:
            self.fields["site"].initial = qs.first().pk
            self.fields["site"].widget = forms.HiddenInput()


class ConsoleRoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ("room_type", "name", "status", "is_active")
        widgets = {
            "room_type": forms.Select(attrs={"class": "staff-input"}),
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "status": forms.Select(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, allowed_room_type_ids: list, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self.fields["room_type"].queryset = RoomType.objects.filter(
            tenant=tenant,
            pk__in=allowed_room_type_ids,
        ).order_by("site__name", "name")


def suggest_tenant_slug(name: str) -> str:
    base = slugify(name)[:80] or "workspace"
    return base


class ConsoleMenuCategoryForm(forms.ModelForm):
    class Meta:
        model = MenuCategory
        fields = ("name", "sort_order", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }


class ConsoleMenuItemForm(forms.ModelForm):
    """Outlets are not in ``Meta.fields`` so we can sync through rows without wiping ``price_override``."""

    outlets = forms.ModelMultipleChoiceField(
        label="Limit to outlets",
        queryset=Outlet.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "staff-input", "size": 8}),
        help_text=(
            "Optional. Empty = every outlet. If you set per-outlet prices below, keep those outlets selected here."
        ),
    )
    modifier_groups = forms.ModelMultipleChoiceField(
        label="Modifier groups",
        queryset=ModifierGroup.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "staff-input", "size": 6}),
        help_text="Optional. Option groups (size, toppings, etc.) staff can pick when adding this item on POS.",
    )

    class Meta:
        model = MenuItem
        fields = (
            "category",
            "name",
            "description",
            "sku",
            "barcode",
            "unit_of_measure",
            "track_inventory",
            "reorder_level",
            "unit_price",
            "tax_rate_percent",
            "is_active",
            "kds_station",
            "consume_recipe_on_sale",
        )
        widgets = {
            "category": forms.Select(attrs={"class": "staff-input"}),
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "sku": forms.TextInput(attrs={"class": "staff-input"}),
            "barcode": forms.TextInput(attrs={"class": "staff-input"}),
            "unit_of_measure": forms.Select(attrs={"class": "staff-input"}),
            "track_inventory": forms.CheckboxInput(),
            "reorder_level": forms.NumberInput(attrs={"class": "staff-input", "step": "any"}),
            "unit_price": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
            "tax_rate_percent": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
            "is_active": forms.CheckboxInput(),
            "kds_station": forms.TextInput(attrs={"class": "staff-input"}),
            "consume_recipe_on_sale": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = MenuCategory.objects.filter(tenant=tenant).order_by(
            "sort_order",
            "name",
        )
        oq = Outlet.objects.filter(site__tenant=tenant).order_by("site__name", "name")
        self.fields["outlets"].queryset = oq
        self.fields["modifier_groups"].queryset = ModifierGroup.objects.filter(tenant=tenant).order_by("name")
        if self.instance.pk:
            self.fields["outlets"].initial = list(self.instance.outlets.all())
            ordered_group_ids = list(
                MenuItemModifierGroup.objects.filter(menu_item=self.instance)
                .order_by("sort_order", "group__name")
                .values_list("group_id", flat=True)
            )
            self.fields["modifier_groups"].initial = ordered_group_ids
        self.fields["description"].required = False
        self.fields["tax_rate_percent"].required = False
        self.fields["reorder_level"].required = False


class ConsoleModifierGroupForm(forms.ModelForm):
    class Meta:
        model = ModifierGroup
        fields = ("name", "min_selections", "max_selections")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "min_selections": forms.NumberInput(attrs={"class": "staff-input", "min": 0}),
            "max_selections": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["max_selections"].required = False
        self.fields["max_selections"].help_text = "Leave blank for no upper limit."


class ConsoleModifierOptionForm(forms.ModelForm):
    class Meta:
        model = ModifierOption
        fields = ("name", "price_delta", "sort_order", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "price_delta": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
            "sort_order": forms.NumberInput(attrs={"class": "staff-input", "min": 0}),
            "is_active": forms.CheckboxInput(),
        }


class ConsoleMenuItemOutletCreateForm(forms.ModelForm):
    class Meta:
        model = MenuItemOutlet
        fields = ("outlet", "price_override")
        widgets = {
            "outlet": forms.Select(attrs={"class": "staff-input"}),
            "price_override": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
        }

    def __init__(self, *args, menu_item: MenuItem, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        base = Outlet.objects.filter(site__tenant=tenant).order_by("site__name", "name")
        linked = MenuItemOutlet.objects.filter(menu_item=menu_item).values_list("outlet_id", flat=True)
        self.fields["outlet"].queryset = base.exclude(pk__in=linked)
        self.fields["price_override"].required = False
        self.fields["price_override"].help_text = "Leave blank to use the item’s default unit price at this outlet."


class ConsoleMenuItemOutletUpdateForm(forms.ModelForm):
    class Meta:
        model = MenuItemOutlet
        fields = ("price_override",)
        widgets = {
            "price_override": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price_override"].required = False
        self.fields["price_override"].help_text = "Leave blank to use the item’s default unit price at this outlet."


class ConsoleMenuItemRecipeLineForm(forms.ModelForm):
    class Meta:
        model = MenuItemRecipeLine
        fields = ("ingredient_item", "quantity_per_unit")
        widgets = {
            "ingredient_item": forms.Select(attrs={"class": "staff-input"}),
            "quantity_per_unit": forms.NumberInput(attrs={"class": "staff-input", "step": "0.001"}),
        }

    def __init__(self, *args, parent_item: MenuItem, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_item = parent_item
        self.fields["ingredient_item"].queryset = MenuItem.objects.filter(tenant=tenant).exclude(
            pk=parent_item.pk,
        ).order_by("name")

    def clean_ingredient_item(self):
        ing = self.cleaned_data.get("ingredient_item")
        if ing and ing.pk == self._parent_item.pk:
            raise forms.ValidationError("An item cannot be an ingredient of itself.")
        return ing


class ConsoleServiceOfferingForm(forms.ModelForm):
    outlets = forms.ModelMultipleChoiceField(
        label="Limit to outlets",
        queryset=Outlet.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "staff-input", "size": 8}),
        help_text="Optional. Empty = every outlet.",
    )

    class Meta:
        model = ServiceOffering
        fields = (
            "name",
            "description",
            "default_price",
            "tax_rate_percent",
            "duration_minutes",
            "kds_station",
            "is_active",
            "outlets",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "default_price": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
            "tax_rate_percent": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0", "max": "100"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "staff-input", "min": "1"}),
            "kds_station": forms.TextInput(attrs={"class": "staff-input", "maxlength": 32}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["outlets"].queryset = Outlet.objects.filter(site__tenant=tenant).order_by("site__name", "name")
        self.fields["description"].required = False
        self.fields["tax_rate_percent"].required = False
        self.fields["duration_minutes"].required = False
        self.fields["kds_station"].required = False
        if self.instance and self.instance.pk:
            self.fields["outlets"].initial = list(self.instance.outlets.all())


class ConsoleServiceOfferingOptionForm(forms.ModelForm):
    class Meta:
        model = ServiceOfferingOption
        fields = (
            "name",
            "description",
            "price",
            "duration_minutes",
            "kds_station",
            "sort_order",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
            "price": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "staff-input", "min": "1"}),
            "kds_station": forms.TextInput(attrs={"class": "staff-input", "maxlength": 32}),
            "sort_order": forms.NumberInput(attrs={"class": "staff-input", "min": "0"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False
        self.fields["duration_minutes"].required = False
        self.fields["kds_station"].required = False


class ConsoleRoomRateWindowForm(forms.ModelForm):
    class Meta:
        model = RoomRateWindow
        fields = ("room_type", "label", "valid_from", "valid_to", "nightly_amount")
        widgets = {
            "room_type": forms.Select(attrs={"class": "staff-input"}),
            "label": forms.TextInput(attrs={"class": "staff-input"}),
            "valid_from": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
            "nightly_amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
        }

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["room_type"].queryset = RoomType.objects.filter(tenant=tenant).select_related(
            "site",
        ).order_by("site__name", "name")
        self.fields["label"].required = False
        self.fields["valid_to"].required = False
