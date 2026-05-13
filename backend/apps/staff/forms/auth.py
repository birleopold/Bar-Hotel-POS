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
