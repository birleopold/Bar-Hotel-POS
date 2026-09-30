from django import forms

from apps.events.models import EventBooking, EventSpace

_EVENT_DT_FORMATS = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


class StaffEventSpaceForm(forms.ModelForm):
    class Meta:
        model = EventSpace
        fields = ["name", "capacity", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "capacity": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
            "is_active": forms.CheckboxInput(),
        }


class StaffEventBookingForm(forms.ModelForm):
    class Meta:
        model = EventBooking
        fields = [
            "space",
            "customer",
            "title",
            "customer_name",
            "customer_email",
            "customer_phone",
            "start_at",
            "end_at",
            "status",
            "headcount",
            "notes",
            "deposit_amount",
        ]
        widgets = {
            "space": forms.Select(attrs={"class": "staff-input"}),
            "customer": forms.Select(attrs={"class": "staff-input"}),
            "title": forms.TextInput(attrs={"class": "staff-input"}),
            "customer_name": forms.TextInput(attrs={"class": "staff-input"}),
            "customer_email": forms.EmailInput(attrs={"class": "staff-input"}),
            "customer_phone": forms.TextInput(attrs={"class": "staff-input"}),
            "start_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "staff-input"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "staff-input"},
                format="%Y-%m-%dT%H:%M",
            ),
            "status": forms.Select(attrs={"class": "staff-input"}),
            "headcount": forms.NumberInput(attrs={"class": "staff-input", "min": 1}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "deposit_amount": forms.NumberInput(attrs={"class": "staff-input", "step": "0.01"}),
        }

    def __init__(self, *args, tenant=None, event_site=None, membership=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.staff.services.customers import visible_customers
        self.fields["customer"].queryset = visible_customers(membership, user) if membership and user else self.fields["customer"].queryset.none()
        self.fields["customer"].help_text = "Optional. Confirm identity first; booking contact below remains its snapshot."
        self.fields["start_at"].input_formats = list(_EVENT_DT_FORMATS)
        self.fields["end_at"].input_formats = list(_EVENT_DT_FORMATS)
        if tenant is not None and event_site is not None:
            self.fields["space"].queryset = EventSpace.objects.filter(
                tenant=tenant,
                site=event_site,
                is_active=True,
            ).order_by("name")

    def clean(self):
        data = super().clean()
        start = data.get("start_at")
        end = data.get("end_at")
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after start time.")
        return data
