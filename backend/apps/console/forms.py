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
    ProductFamily,
    ProductPackage,
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
        if getattr(self.instance, "pk", None):
            self.fields["status"].disabled = True
            self.fields["status"].help_text = "Use Subscription transition below to change status with audit evidence."
        for name in ("started_at", "trial_ends_at", "current_period_ends_at", "cancelled_at"):
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        started_at = cleaned.get("started_at")
        trial_ends_at = cleaned.get("trial_ends_at")
        period_ends_at = cleaned.get("current_period_ends_at")
        if status == SubscriptionStatus.CANCELLED and not cleaned.get("cancelled_at"):
            self.add_error("cancelled_at", "Cancelled subscriptions require a cancelled timestamp.")
        elif status != SubscriptionStatus.CANCELLED:
            cleaned["cancelled_at"] = None
        if started_at and trial_ends_at and trial_ends_at < started_at:
            self.add_error("trial_ends_at", "Trial end cannot be before the subscription start.")
        if started_at and period_ends_at and period_ends_at < started_at:
            self.add_error("current_period_ends_at", "Current period end cannot be before the subscription start.")
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
        amount = cleaned.get("amount")
        issued_at = cleaned.get("issued_at")
        due_at = cleaned.get("due_at")
        if amount is not None and amount <= 0:
            self.add_error("amount", "Invoice amount must be greater than zero.")
        if issued_at and due_at and due_at < issued_at:
            self.add_error("due_at", "Due date cannot be before the issue date.")
        if status == BillingInvoiceStatus.PAID:
            if not cleaned.get("paid_at"):
                cleaned["paid_at"] = timezone.now()
        else:
            cleaned["paid_at"] = None
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
            "product_image": forms.ClearableFileInput(attrs={"class": "staff-input", "accept": "image/jpeg,image/png,image/webp"}),
            "display_image_url": forms.URLInput(attrs={"class": "staff-input", "placeholder": "https://... (optional alternative)"}),
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
            "product_family",
            "name",
            "description",
            "product_image",
            "display_image_url",
            "sku",
            "barcode",
            "unit_of_measure",
            "units_per_carton",
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
            "product_family": forms.Select(attrs={"class": "staff-input"}),
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "sku": forms.TextInput(attrs={"class": "staff-input"}),
            "barcode": forms.TextInput(attrs={"class": "staff-input"}),
            "unit_of_measure": forms.Select(attrs={"class": "staff-input"}),
            "units_per_carton": forms.NumberInput(attrs={"class": "staff-input", "min": "1", "max": "10000", "step": "1"}),
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
        self.tenant = tenant
        self.fields["category"].queryset = MenuCategory.objects.filter(tenant=tenant).order_by(
            "sort_order",
            "name",
        )
        self.fields["product_family"].queryset = ProductFamily.objects.filter(
            tenant=tenant, is_active=True,
        ).select_related("category").order_by("category__name", "name")
        self.fields["product_family"].required = False
        self.fields["product_family"].help_text = "Optional. Group concrete size/colour/style variants under one parent product."
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
        if self.instance._state.adding:
            try:
                from apps.tenants.business_lines import normalize_business_lines
                lines = set(normalize_business_lines(tenant.settings.business_lines))
            except Exception:
                lines = set()
            if lines & {"retail", "supermarket"}:
                self.fields["track_inventory"].initial = True
        # Existing owners/API clients can omit this newly optional setting.
        self.fields["units_per_carton"].required = False

    def clean_product_image(self):
        image = self.cleaned_data.get("product_image")
        if image and hasattr(image, "size") and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Product image must be 5 MB or smaller.")
        if image and hasattr(image, "content_type") and image.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise forms.ValidationError("Upload a JPEG, PNG or WebP image.")
        return image

    def clean_units_per_carton(self):
        return self.cleaned_data.get("units_per_carton") or 1

    def clean(self):
        values = super().clean()
        if values.get("units_per_carton", 1) > 1:
            if values.get("unit_of_measure") != "each":
                self.add_error("units_per_carton", "Carton quantities require an item stocked by the piece.")
            if not values.get("track_inventory"):
                self.add_error("units_per_carton", "Turn on stock tracking before configuring cartons.")
        family = values.get("product_family")
        category = values.get("category")
        if family and category and family.category_id != category.id:
            self.add_error("product_family", "Choose a product family in the same category as this sellable variant.")
        barcode = (values.get("barcode") or "").strip()
        if barcode and ProductPackage.objects.filter(tenant=self.tenant, barcode=barcode).exists():
            self.add_error("barcode", "This barcode is already assigned to a product package.")
        sku = (values.get("sku") or "").strip()
        if sku and ProductPackage.objects.filter(tenant=self.tenant, sku_alias__iexact=sku).exists():
            self.add_error("sku", "This SKU is already assigned as a product package code.")
        return values


class ConsoleProductFamilyForm(forms.ModelForm):
    class Meta:
        model = ProductFamily
        fields = ("category", "name", "description", "is_active")
        widgets = {
            "category": forms.Select(attrs={"class": "staff-input"}),
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.fields["category"].queryset = MenuCategory.objects.filter(
            tenant=tenant,
        ).order_by("sort_order", "name")

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        qs = ProductFamily.objects.filter(tenant=self.tenant, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A product family with this name already exists.")
        return name


class ConsoleVariantMatrixForm(forms.Form):
    option_1_name = forms.CharField(
        max_length=40, label="Option 1", initial="Colour",
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Colour"}),
    )
    option_1_values = forms.CharField(
        max_length=500, label="Option 1 values",
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Black, White, Blue"}),
        help_text="Separate values with commas.",
    )
    option_2_name = forms.CharField(
        max_length=40, label="Option 2", required=False, initial="Size",
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Size"}),
    )
    option_2_values = forms.CharField(
        max_length=500, label="Option 2 values", required=False,
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "S, M, L, XL"}),
        help_text="Leave both option 2 fields blank if this family has one dimension.",
    )
    option_3_name = forms.CharField(
        max_length=40, label="Option 3", required=False,
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Material"}),
    )
    option_3_values = forms.CharField(
        max_length=500, label="Option 3 values", required=False,
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Cotton, Polyester"}),
    )
    sku_prefix = forms.CharField(
        max_length=32, label="SKU prefix",
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "POLO"}),
        help_text="Generated SKUs append normalized variant values to this prefix.",
    )
    unit_price = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2, label="Default selling price",
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0", "step": "0.01"}),
    )
    tax_rate_percent = forms.DecimalField(
        required=False, min_value=0, max_value=100, max_digits=5, decimal_places=2,
        label="Tax rate %",
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0", "max": "100", "step": "0.01"}),
    )
    reorder_level = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": "0", "step": "0.001"}),
    )
    track_inventory = forms.BooleanField(required=False, initial=True, label="Track stock for generated variants")
    is_active = forms.BooleanField(required=False, initial=True, label="Generated variants are active")

    def _split_values(self, raw):
        result = []
        seen = set()
        for value in (raw or "").split(","):
            value = value.strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def clean_sku_prefix(self):
        import re
        prefix = (self.cleaned_data.get("sku_prefix") or "").strip().upper()
        prefix = re.sub(r"[^A-Z0-9_-]+", "-", prefix).strip("-_")
        if not prefix:
            raise forms.ValidationError("Enter a SKU prefix using letters or numbers.")
        return prefix[:32]

    def clean(self):
        data = super().clean()
        schema = []
        names = set()
        for index in (1, 2, 3):
            name = (data.get(f"option_{index}_name") or "").strip()
            values = self._split_values(data.get(f"option_{index}_values"))
            if bool(name) != bool(values):
                self.add_error(
                    f"option_{index}_values" if name else f"option_{index}_name",
                    "Enter both the option name and its values.",
                )
                continue
            if not name:
                continue
            key = name.casefold()
            if key in names:
                self.add_error(f"option_{index}_name", "Variant option names must be unique.")
                continue
            names.add(key)
            if len(values) > 20:
                self.add_error(f"option_{index}_values", "Use no more than 20 values per option.")
                continue
            schema.append({"name": name, "values": values})
        if not schema:
            self.add_error("option_1_values", "Add at least one variant option and value.")
        combinations = 1
        for row in schema:
            combinations *= len(row["values"])
        if combinations > 120:
            raise forms.ValidationError(
                f"This matrix would create {combinations} combinations. Keep one batch to 120 or fewer."
            )
        data["variant_schema"] = schema
        data["combination_count"] = combinations
        return data


class ConsoleProductPackageForm(forms.ModelForm):
    class Meta:
        model = ProductPackage
        fields = (
            "name", "units_per_package", "barcode", "sku_alias", "sell_price",
            "is_sellable", "is_purchasable", "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "units_per_package": forms.NumberInput(attrs={"class": "staff-input", "min": "0.001", "step": "0.001"}),
            "barcode": forms.TextInput(attrs={"class": "staff-input"}),
            "sku_alias": forms.TextInput(attrs={"class": "staff-input"}),
            "sell_price": forms.NumberInput(attrs={"class": "staff-input", "min": "0", "step": "0.01"}),
            "is_sellable": forms.CheckboxInput(),
            "is_purchasable": forms.CheckboxInput(),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, menu_item, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.menu_item = menu_item
        self.fields["sell_price"].required = False

    def clean_barcode(self):
        barcode = (self.cleaned_data.get("barcode") or "").strip()
        if not barcode:
            return ""
        if MenuItem.objects.filter(tenant=self.tenant, barcode=barcode).exists():
            raise forms.ValidationError("This barcode is already registered to another product.")
        qs = ProductPackage.objects.filter(tenant=self.tenant, barcode=barcode)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This barcode is already registered to another package.")
        return barcode

    def clean_sku_alias(self):
        code = (self.cleaned_data.get("sku_alias") or "").strip()
        if not code:
            return ""
        if MenuItem.objects.filter(tenant=self.tenant, sku__iexact=code).exists():
            raise forms.ValidationError("This package code is already used by another product SKU.")
        qs = ProductPackage.objects.filter(tenant=self.tenant, sku_alias__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This package code is already in use.")
        return code

    def clean(self):
        data = super().clean()
        units = data.get("units_per_package")
        price = data.get("sell_price")
        if units and price is not None:
            per_base = price / units
            if per_base != per_base.quantize(Decimal("0.01")):
                self.add_error(
                    "sell_price",
                    "For this R1 package flow, the package price must divide exactly into a two-decimal base-unit price. Leave it blank to use the normal product price; richer pack discounts are handled in R2 pricing.",
                )
        return data


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
