from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from apps.lodging.models import Reservation


class StaffReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["guest_name", "guest_email", "guest_phone", "check_in", "check_out", "notes"]
        widgets = {
            "guest_name": forms.TextInput(attrs={"class": "staff-input"}),
            "guest_email": forms.EmailInput(attrs={"class": "staff-input"}),
            "guest_phone": forms.TextInput(attrs={"class": "staff-input"}),
            "check_in": forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
            "check_out": forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
        }

    def clean(self):
        data = super().clean()
        ci = data.get("check_in")
        co = data.get("check_out")
        if ci and co and co <= ci:
            raise forms.ValidationError("Check-out must be after check-in.")
        return data


class StaffFolioManualLineForm(forms.Form):
    description = forms.CharField(max_length=512, widget=forms.TextInput(attrs={"class": "staff-input"}))
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
    )
    tax_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
    )
