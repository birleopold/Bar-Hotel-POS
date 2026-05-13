from django import forms
from django.utils import timezone

from apps.catalog.models import Promotion
from apps.tenants.models import Outlet


class StaffPromotionForm(forms.ModelForm):
    """Exactly one of ``discount_percent`` or ``discount_amount`` (matches API serializer)."""

    class Meta:
        model = Promotion
        fields = [
            "name",
            "discount_percent",
            "discount_amount",
            "min_order_subtotal",
            "starts_at",
            "ends_at",
            "is_active",
            "outlets",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input", "maxlength": 128}),
            "discount_percent": forms.NumberInput(
                attrs={"class": "staff-input", "step": "0.01", "min": 0, "max": 100}
            ),
            "discount_amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": 0}),
            "min_order_subtotal": forms.NumberInput(
                attrs={"class": "staff-input", "step": "0.01", "min": 0},
            ),
            "is_active": forms.CheckboxInput(),
            "outlets": forms.SelectMultiple(attrs={"class": "staff-input", "size": 6}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["discount_percent"].required = False
        self.fields["discount_amount"].required = False
        self.fields["min_order_subtotal"].required = False
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
        pct = data.get("discount_percent")
        amt = data.get("discount_amount")
        has_pct = pct is not None
        has_amt = amt is not None
        if has_pct == has_amt:
            raise forms.ValidationError(
                "Set either a percent discount or a fixed amount — exactly one.",
            )
        raw_end = self.data.get("ends_at")
        if raw_end is not None and str(raw_end).strip() == "":
            data["ends_at"] = None
        return data
