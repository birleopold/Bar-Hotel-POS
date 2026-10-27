from django import forms
from django.utils import timezone

from apps.catalog.models import MenuCategory, MenuItem, ProductFamily, Promotion
from apps.tenants.models import Outlet


class StaffPromotionForm(forms.ModelForm):
    """Exactly one of ``discount_percent`` or ``discount_amount`` (matches API serializer)."""

    class Meta:
        model = Promotion
        fields = [
            "name",
            "offer_type",
            "menu_item",
            "product_family",
            "category",
            "brand",
            "discount_percent",
            "discount_amount",
            "min_order_subtotal",
            "min_target_quantity",
            "coupon_code",
            "max_redemptions",
            "max_redemptions_per_customer",
            "buy_quantity",
            "get_quantity",
            "max_uses_per_order",
            "starts_at",
            "ends_at",
            "is_active",
            "outlets",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input", "maxlength": 128}),
            "offer_type": forms.Select(attrs={"class": "staff-input"}),
            "menu_item": forms.Select(attrs={"class": "staff-input"}),
            "product_family": forms.Select(attrs={"class": "staff-input"}),
            "category": forms.Select(attrs={"class": "staff-input"}),
            "brand": forms.TextInput(attrs={"class": "staff-input", "placeholder": "e.g. Samsung"}),
            "discount_percent": forms.NumberInput(
                attrs={"class": "staff-input", "step": "0.01", "min": 0, "max": 100}
            ),
            "discount_amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": 0}),
            "min_order_subtotal": forms.NumberInput(
                attrs={"class": "staff-input", "step": "0.01", "min": 0},
            ),
            "min_target_quantity": forms.NumberInput(
                attrs={"class": "staff-input", "step": "0.001", "min": "0.001"},
            ),
            "coupon_code": forms.TextInput(
                attrs={"class": "staff-input", "maxlength": 64, "placeholder": "Optional coupon code"},
            ),
            "max_redemptions": forms.NumberInput(
                attrs={"class": "staff-input", "min": 1, "step": 1},
            ),
            "max_redemptions_per_customer": forms.NumberInput(
                attrs={"class": "staff-input", "min": 1, "step": 1},
            ),
            "buy_quantity": forms.NumberInput(
                attrs={"class": "staff-input", "min": 1, "step": 1},
            ),
            "get_quantity": forms.NumberInput(
                attrs={"class": "staff-input", "min": 1, "step": 1},
            ),
            "max_uses_per_order": forms.NumberInput(
                attrs={"class": "staff-input", "min": 1, "step": 1},
            ),
            "is_active": forms.CheckboxInput(),
            "outlets": forms.SelectMultiple(attrs={"class": "staff-input", "size": 6}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["menu_item"].required = False
        self.fields["product_family"].required = False
        self.fields["category"].required = False
        self.fields["brand"].required = False
        self.fields["discount_percent"].required = False
        self.fields["discount_amount"].required = False
        self.fields["min_order_subtotal"].required = False
        self.fields["min_target_quantity"].required = False
        self.fields["coupon_code"].required = False
        self.fields["max_redemptions"].required = False
        self.fields["max_redemptions_per_customer"].required = False
        self.fields["buy_quantity"].required = False
        self.fields["get_quantity"].required = False
        self.fields["max_uses_per_order"].required = False
        self.fields["ends_at"].required = False
        self.fields["outlets"].required = False
        self.fields["outlets"].label = "Limit to sections"
        self.fields["outlets"].help_text = "Leave empty to apply in every section."
        dt = forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "staff-input"},
            format="%Y-%m-%dT%H:%M",
        )
        self.fields["starts_at"].widget = dt
        self.fields["starts_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        self.fields["ends_at"].widget = dt
        self.fields["ends_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        if tenant is not None:
            self.fields["outlets"].queryset = Outlet.objects.filter(
                site__tenant=tenant,
                is_active=True,
            ).select_related("site").order_by("site__name", "name")
            self.fields["menu_item"].queryset = MenuItem.objects.filter(
                tenant=tenant,
                is_active=True,
            ).order_by("name")
            self.fields["product_family"].queryset = ProductFamily.objects.filter(
                tenant=tenant,
                is_active=True,
            ).select_related("category").order_by("category__name", "name")
            self.fields["category"].queryset = MenuCategory.objects.filter(
                tenant=tenant,
                is_active=True,
            ).order_by("sort_order", "name")
        self.fields["menu_item"].help_text = "Optional. Most specific target."
        self.fields["product_family"].help_text = "Optional. Applies to all matching variants."
        self.fields["category"].help_text = "Optional. Applies to all products in this category."
        self.fields["brand"].help_text = "Optional case-insensitive brand target. Leave all targets blank for the whole basket."
        self.fields["min_target_quantity"].help_text = "Optional qualifying quantity. For targeted offers this counts matching units; for whole-basket offers it counts all sellable basket units."
        self.fields["coupon_code"].help_text = "Optional. Coupon offers are not shown in the normal checkout offer list; the cashier must enter the code."
        self.fields["max_redemptions"].help_text = "Optional global limit counted only after orders are fully paid."
        self.fields["max_redemptions_per_customer"].help_text = "Optional limit for identified customers; anonymous sales do not consume a customer-specific allowance."
        self.fields["buy_quantity"].help_text = "Buy X Get Y only: whole qualifying units the customer pays for in each set."
        self.fields["get_quantity"].help_text = "Buy X Get Y only: whole additional qualifying units made free in each set."
        self.fields["max_uses_per_order"].help_text = "Buy X Get Y only: optional cap on qualifying sets per order."
        if self.instance.pk:
            if self.instance.starts_at:
                st = self.instance.starts_at
                if timezone.is_aware(st):
                    st = timezone.localtime(st)
                self.initial["starts_at"] = st.replace(second=0, microsecond=0).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            if self.instance.ends_at:
                et = self.instance.ends_at
                if timezone.is_aware(et):
                    et = timezone.localtime(et)
                self.initial["ends_at"] = et.replace(second=0, microsecond=0).strftime(
                    "%Y-%m-%dT%H:%M"
                )

    def clean(self):
        data = super().clean()
        offer_type = data.get("offer_type") or Promotion.OfferType.STANDARD
        pct = data.get("discount_percent")
        amt = data.get("discount_amount")
        has_pct = pct is not None
        has_amt = amt is not None
        if offer_type == Promotion.OfferType.BUY_X_GET_Y:
            if has_pct or has_amt:
                raise forms.ValidationError(
                    "Buy X Get Y uses buy/get quantities; leave percent and amount discount blank.",
                )
            if not data.get("buy_quantity") or not data.get("get_quantity"):
                raise forms.ValidationError(
                    "Buy X Get Y requires both buy quantity and get quantity.",
                )
        else:
            if has_pct == has_amt:
                raise forms.ValidationError(
                    "Set either a percent discount or a fixed amount — exactly one.",
                )
            if data.get("buy_quantity") or data.get("get_quantity") or data.get("max_uses_per_order"):
                raise forms.ValidationError(
                    "Buy/get quantities are only available for Buy X Get Y offers.",
                )
        targets = [
            bool(data.get("menu_item")),
            bool(data.get("product_family")),
            bool(data.get("category")),
            bool((data.get("brand") or "").strip()),
        ]
        if sum(targets) > 1:
            raise forms.ValidationError(
                "Choose only one promotion target: product, product family, category, or brand.",
            )
        if offer_type == Promotion.OfferType.BUY_X_GET_Y and sum(targets) != 1:
            raise forms.ValidationError(
                "Buy X Get Y requires exactly one product, product family, category, or brand target.",
            )
        if data.get("brand") is not None:
            data["brand"] = (data.get("brand") or "").strip()
        if data.get("coupon_code") is not None:
            data["coupon_code"] = (data.get("coupon_code") or "").strip()
        if (
            data.get("max_redemptions") is not None
            and data.get("max_redemptions_per_customer") is not None
            and data["max_redemptions_per_customer"] > data["max_redemptions"]
        ):
            self.add_error(
                "max_redemptions_per_customer",
                "Per-customer limit cannot exceed the total redemption limit.",
            )
        raw_end = self.data.get("ends_at")
        if raw_end is not None and str(raw_end).strip() == "":
            data["ends_at"] = None
        return data
