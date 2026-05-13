from __future__ import annotations

from django import forms
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.staff.middleware import STAFF_SESSION_TENANT_KEY
from apps.tenants.business_lines import BUSINESS_LINES, normalize_business_lines

from .signup_service import create_pending_workspace_signup


class PublicSignupForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "staff-input", "autofocus": True}),
    )
    workspace_name = forms.CharField(
        label="Workspace name",
        widget=forms.TextInput(attrs={"autocomplete": "organization", "class": "staff-input"}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "staff-input"}),
    )
    business_lines = forms.MultipleChoiceField(
        label="Business lines",
        required=True,
        choices=[(k, v.label) for k, v in BUSINESS_LINES.items()],
        widget=forms.CheckboxSelectMultiple,
    )


class PublicSignupView(View):
    template_name = "public/signup.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = PublicSignupForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = PublicSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        email = (form.cleaned_data.get("email") or "").strip().lower()
        workspace_name = (form.cleaned_data.get("workspace_name") or "").strip()
        password = form.cleaned_data.get("password") or ""
        business_lines = normalize_business_lines(list(form.cleaned_data.get("business_lines") or []))

        if not password or len(password) < 8:
            form.add_error("password", "Password must be at least 8 characters.")
            return render(request, self.template_name, {"form": form})

        if not business_lines:
            form.add_error("business_lines", "Choose at least one business line.")
            return render(request, self.template_name, {"form": form})

        try:
            user, tenant = create_pending_workspace_signup(
                email=email,
                password=password,
                workspace_name=workspace_name,
                business_lines=business_lines,
            )
        except Exception:
            form.add_error(None, "Something went wrong. Please try again.")
            return render(request, self.template_name, {"form": form})

        login(request, user)
        request.session[STAFF_SESSION_TENANT_KEY] = str(tenant.id)
        return redirect("staff-pending-approval")
