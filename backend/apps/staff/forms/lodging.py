from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from apps.accounts.models import User
from apps.lodging.models import (
    FolioPaymentMethod,
    MaintenancePriority,
    Room,
    RoomMaintenanceRequest,
    Reservation,
)


class StaffReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["customer", "guest_name", "guest_email", "guest_phone", "check_in", "check_out", "notes"]
        widgets = {
            "customer": forms.Select(attrs={"class": "staff-input"}),
            "guest_name": forms.TextInput(attrs={"class": "staff-input"}),
            "guest_email": forms.EmailInput(attrs={"class": "staff-input"}),
            "guest_phone": forms.TextInput(attrs={"class": "staff-input"}),
            "check_in": forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
            "check_out": forms.DateInput(attrs={"type": "date", "class": "staff-input"}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
        }

    def __init__(self, *args, membership=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.staff.services.customers import visible_customers
        self.fields["customer"].queryset = visible_customers(membership, user) if membership and user else self.fields["customer"].queryset.none()
        self.fields["customer"].help_text = "Optional. Confirm identity first; guest details below remain this stay's snapshot."

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


class StaffFolioPaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        widget=forms.NumberInput(attrs={"class": "staff-input", "step": "0.01", "min": "0.01"}),
    )
    method = forms.ChoiceField(
        choices=FolioPaymentMethod.choices,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    reference = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Receipt or transaction reference"}),
    )


class StaffRoomMaintenanceForm(forms.ModelForm):
    class Meta:
        model = RoomMaintenanceRequest
        fields = ["room", "title", "description", "priority", "assigned_to", "expected_by"]
        widgets = {
            "room": forms.Select(attrs={"class": "staff-input"}),
            "title": forms.TextInput(attrs={"class": "staff-input", "placeholder": "e.g. Air conditioner not cooling"}),
            "description": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "priority": forms.Select(attrs={"class": "staff-input"}),
            "assigned_to": forms.Select(attrs={"class": "staff-input"}),
            "expected_by": forms.DateInput(attrs={"class": "staff-input", "type": "date"}),
        }

    def __init__(self, *args, tenant, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = Room.objects.filter(room_type__site=site, is_active=True).select_related("room_type")
        self.fields["assigned_to"].queryset = User.objects.filter(
            memberships__tenant=tenant,
            memberships__is_active=True,
        ).distinct().order_by("email")
        self.fields["assigned_to"].required = False
        self.fields["priority"].choices = MaintenancePriority.choices
