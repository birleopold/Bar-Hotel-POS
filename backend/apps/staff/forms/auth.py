from django import forms
from django.contrib.auth.forms import AuthenticationForm


class StaffLoginForm(AuthenticationForm):
    """Email + password; ``username`` field holds the email (``User.USERNAME_FIELD``)."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "class": "staff-input",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": "staff-input",
            }
        ),
    )


class StaffPinSetupForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "staff-input", "autocomplete": "current-password"}))
    pin = forms.RegexField(
        regex=r"^[0-9]{6,8}$", label="New PIN (6 to 8 digits)",
        widget=forms.PasswordInput(attrs={"class": "staff-input", "inputmode": "numeric", "autocomplete": "new-password", "minlength": 6, "maxlength": 8}),
    )
    confirm_pin = forms.CharField(
        label="Confirm PIN", widget=forms.PasswordInput(attrs={"class": "staff-input", "inputmode": "numeric", "autocomplete": "new-password"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        data = super().clean()
        if not self.user.check_password(data.get("password", "")):
            self.add_error("password", "Enter your account password to set a PIN.")
        if data.get("pin") and data.get("pin") != data.get("confirm_pin"):
            self.add_error("confirm_pin", "PINs do not match.")
        if data.get("pin") and len(set(data["pin"])) == 1:
            self.add_error("pin", "Choose a less predictable PIN.")
        return data


class StaffTerminalUnlockForm(forms.Form):
    worker = forms.UUIDField(widget=forms.Select(attrs={"class": "staff-input", "autocomplete": "username"}))
    pin = forms.RegexField(
        regex=r"^[0-9]{6,8}$", label="PIN",
        widget=forms.PasswordInput(attrs={"class": "staff-input", "inputmode": "numeric", "autocomplete": "off", "minlength": 6, "maxlength": 8, "autofocus": True}),
    )

    def __init__(self, *args, workers=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["worker"].widget.choices = [("", "Select your name")] + [
            (str(m.id), m.user.get_full_name() or m.user.email) for m in workers
        ]
