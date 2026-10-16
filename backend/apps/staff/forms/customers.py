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

    def clean_phone(self):
        """Normalize harmless formatting without guessing international prefixes.

        Do not fabricate a country code: historic customer phone values may be
        local, and wrong assumptions could merge distinct customers.
        """
        raw = (self.cleaned_data.get("phone") or "").strip()
        if not raw:
            return ""
        allowed = set("0123456789+ ()-./")
        if any(char not in allowed for char in raw):
            raise forms.ValidationError("Enter a phone number using digits and standard separators.")
        digits = "".join(char for char in raw if char.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            raise forms.ValidationError("Enter a phone number with 7–15 digits.")
        return ("+" if raw.startswith("+") else "") + digits
