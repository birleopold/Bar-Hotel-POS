from django import forms

from apps.customers.models import Customer


class StaffCustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "email", "phone", "preferences", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "staff-input"}),
            "email": forms.EmailInput(attrs={"class": "staff-input"}),
            "phone": forms.TextInput(attrs={"class": "staff-input"}),
            "preferences": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
            "notes": forms.Textarea(attrs={"class": "staff-input", "rows": 2}),
        }

    def clean_name(self):
        value = self.cleaned_data["name"].strip()
        if not value:
            raise forms.ValidationError("Enter a customer name.")
        return value

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
