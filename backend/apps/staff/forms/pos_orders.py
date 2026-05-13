from decimal import Decimal

from django import forms

from apps.catalog.models import MenuItem, Promotion, ServiceOffering, ServiceOfferingOption
from apps.lodging.models import Folio
from apps.pos.models import PaymentMethod, Table
from apps.pos.services import menu_items_for_outlet_queryset
from apps.tenants.models import Outlet


class StaffTableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ["label", "capacity", "sort_order", "is_active"]
        widgets = {
            "label": forms.TextInput(attrs={"class": "staff-input", "maxlength": 64}),
            "capacity": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
            "sort_order": forms.NumberInput(attrs={"class": "staff-input", "min": 0}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, outlet: Outlet | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._outlet = outlet

    def clean_label(self):
        label = (self.cleaned_data.get("label") or "").strip()
        if not label:
            raise forms.ValidationError("Label is required.")
        outlet = self._outlet or (self.instance.outlet if self.instance.pk else None)
        if outlet is not None:
            qs = Table.objects.filter(outlet=outlet, label__iexact=label)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This label is already used in this section.")
        return label


class StaffOrderAddLineForm(forms.Form):
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.none(),
        empty_label="Select item",
        widget=forms.Select(
            attrs={"class": "staff-input", "id": "staff-pos-add-line-menu-item"},
        ),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=10,
        decimal_places=3,
        initial=Decimal("1"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0.001"}),
    )

    def __init__(self, *args, tenant_id, outlet_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["menu_item"].queryset = menu_items_for_outlet_queryset(tenant_id, outlet_id).order_by(
            "category__sort_order",
            "category__name",
            "name",
        )


class StaffOrderAddServiceForm(forms.Form):
    service_offering = forms.ModelChoiceField(
        queryset=ServiceOffering.objects.none(),
        empty_label="Select service",
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=10,
        decimal_places=3,
        initial=Decimal("1"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0.001"}),
    )
    service_option = forms.ModelChoiceField(
        queryset=ServiceOfferingOption.objects.none(),
        required=False,
        empty_label="Default package",
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, tenant_id, outlet_id, **kwargs):
        from django.db.models import Q

        super().__init__(*args, **kwargs)
        self._tenant_id = tenant_id
        self._outlet_id = outlet_id
        self.fields["service_offering"].queryset = (
            ServiceOffering.objects.filter(tenant_id=tenant_id, is_active=True)
            .filter(Q(outlets__isnull=True) | Q(outlets__id=outlet_id))
            .distinct()
            .order_by("name")
        )
        selected_service_id = (
            self.data.get("service_offering")
            or self.initial.get("service_offering")
            or getattr(getattr(self, "instance", None), "service_offering_id", None)
        )
        option_qs = ServiceOfferingOption.objects.none()
        if selected_service_id:
            option_qs = (
                ServiceOfferingOption.objects.filter(
                    service_offering_id=selected_service_id,
                    service_offering__tenant_id=tenant_id,
                    service_offering__is_active=True,
                    is_active=True,
                )
                .filter(Q(service_offering__outlets__isnull=True) | Q(service_offering__outlets__id=outlet_id))
                .distinct()
                .order_by("sort_order", "name")
            )
        self.fields["service_option"].queryset = option_qs

    def clean(self):
        cleaned = super().clean()
        svc = cleaned.get("service_offering")
        opt = cleaned.get("service_option")
        if opt is None:
            return cleaned
        if svc is None or opt.service_offering_id != svc.id:
            raise forms.ValidationError("Selected package does not belong to the selected service.")
        if opt.service_offering.tenant_id != self._tenant_id:
            raise forms.ValidationError("Selected package is invalid for this workspace.")
        if not opt.service_offering.available_at_outlet(self._outlet_id):
            raise forms.ValidationError("Selected package is not available at this outlet.")
        return cleaned


class StaffOrderApplyPromotionForm(forms.Form):
    promotion = forms.ModelChoiceField(
        queryset=Promotion.objects.none(),
        empty_label="Select promotion",
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, eligible_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["promotion"].queryset = eligible_queryset


class StaffOrderPaymentForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=PaymentMethod.choices,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )


class StaffOrderSetFolioForm(forms.Form):
    folio_id = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, folio_queryset, initial_folio_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = folio_queryset or Folio.objects.none()
        choices = [("__none__", "No folio")] + [(str(f.id), f"{f.guest_name}") for f in qs]
        self.fields["folio_id"].choices = choices
        if initial_folio_id:
            self.initial["folio_id"] = str(initial_folio_id)

    def clean_folio_id(self):
        token = (self.cleaned_data.get("folio_id") or "").strip()
        if token in ("", "__none__"):
            return None
        return token


class StaffOrderVoidLineForm(forms.Form):
    line_id = forms.UUIDField(widget=forms.HiddenInput())
    reason = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "staff-input", "placeholder": "Reason (optional)", "style": "max-width: 10rem;"}
        ),
    )


class StaffOrderAdjustLineQuantityForm(forms.Form):
    line_id = forms.UUIDField(widget=forms.HiddenInput())
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=10,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0.001"}),
    )


class StaffOrderScanAddForm(forms.Form):
    code = forms.CharField(
        max_length=64,
        widget=forms.TextInput(
            attrs={
                "class": "staff-input",
                "maxlength": 64,
                "placeholder": "Scan barcode / enter PLU",
                "autocomplete": "off",
            },
        ),
    )
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=10,
        decimal_places=3,
        initial=Decimal("1"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0.001"}),
    )


class StaffOrderLineDiscountForm(forms.Form):
    line_id = forms.UUIDField(widget=forms.HiddenInput())
    discount_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
    )
    discount_percent = forms.DecimalField(
        required=False,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0", "max": "100"}),
    )

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("discount_amount")
        percent = cleaned.get("discount_percent")
        if amount in (None, Decimal("0")) and percent in (None, Decimal("0")):
            raise forms.ValidationError("Enter discount amount or discount percent.")
        return cleaned


class StaffOrderHoldForm(forms.Form):
    hold_label = forms.CharField(
        max_length=64,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 64}),
    )


class StaffOrderVoidOrderForm(forms.Form):
    reason = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 255}),
    )


class StaffOrderLineReturnForm(forms.Form):
    line_id = forms.UUIDField(widget=forms.HiddenInput())
    quantity = forms.DecimalField(
        min_value=Decimal("0.001"),
        max_digits=10,
        decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.001", "min": "0.001"}),
    )
    reason = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 255}),
    )
    restock = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput())


class StaffOrderReadyHandoffForm(forms.Form):
    line_id = forms.UUIDField(widget=forms.HiddenInput())


class StaffPosShiftOpenForm(forms.Form):
    opening_cash = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 255}),
    )


class StaffPosShiftCloseForm(forms.Form):
    shift_id = forms.UUIDField(widget=forms.HiddenInput())
    counted_cash = forms.DecimalField(
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0"}),
    )
    note = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "maxlength": 255}),
    )


class StaffOrderRefundForm(forms.Form):
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0.01"}),
    )
    reason = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Reason (optional)"}),
    )
    restock = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(),
    )

    def __init__(
        self,
        *args,
        payments: list | None = None,
        max_refund: Decimal | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._max_refund = (max_refund or Decimal("0")).quantize(Decimal("0.01"))
        pays = list(payments or [])
        if len(pays) > 1:
            self.fields["payment_id"] = forms.ChoiceField(
                label="Apply refund to payment",
                choices=[(str(p.id), f"{p.get_method_display()} — {p.amount}") for p in pays],
                widget=forms.Select(attrs={"class": "staff-input"}),
            )

    def clean_amount(self) -> Decimal:
        amt = self.cleaned_data["amount"].quantize(Decimal("0.01"))
        if amt > self._max_refund:
            raise forms.ValidationError(f"Cannot exceed remaining refundable {self._max_refund}.")
        return amt
