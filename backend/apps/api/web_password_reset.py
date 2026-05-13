"""Minimal staff-facing password reset page (Django templates + form POST)."""

from __future__ import annotations

from django import forms
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from apps.api.password_reset_core import attempt_password_reset_confirm


class StaffPasswordResetForm(forms.Form):
    uid = forms.CharField(widget=forms.HiddenInput)
    token = forms.CharField(widget=forms.HiddenInput)
    new_password = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "class": "staff-input"}
        ),
    )


class StaffPasswordResetConfirmView(View):
    """
    GET: show form when ``uid`` and ``token`` query params are present (from email link).
    POST: same fields plus ``new_password``; uses shared logic as ``/api/v1/auth/password/reset/confirm/``.
    """

    template_name = "password_reset/confirm.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        uid = (request.GET.get("uid") or "").strip()
        token = (request.GET.get("token") or "").strip()
        if not uid or not token:
            return render(
                request,
                self.template_name,
                {
                    "invalid_link": True,
                    "form": None,
                },
            )
        form = StaffPasswordResetForm(initial={"uid": uid, "token": token})
        return render(
            request,
            self.template_name,
            {
                "invalid_link": False,
                "form": form,
                "success": False,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not (request.POST.get("uid") or "").strip() or not (request.POST.get("token") or "").strip():
            return render(
                request,
                self.template_name,
                {
                    "invalid_link": True,
                    "form": None,
                },
            )
        form = StaffPasswordResetForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "invalid_link": False,
                    "form": form,
                    "success": False,
                },
            )
        cd = form.cleaned_data
        status_code, body = attempt_password_reset_confirm(
            uid=cd["uid"],
            token=cd["token"],
            new_password=cd["new_password"],
        )
        if status_code == 200:
            return render(
                request,
                self.template_name,
                {
                    "invalid_link": False,
                    "form": None,
                    "success": True,
                    "success_message": body.get("detail", ""),
                },
            )
        err = body.get("error") or {}
        code = err.get("code")
        if code == "validation_error":
            for msg in err.get("fields", {}).get("new_password", []):
                form.add_error("new_password", msg)
        elif code == "invalid_reset":
            form.add_error(None, err.get("message", "Invalid or expired reset link."))
        elif code == "invalid_input":
            fields = err.get("fields") or {}
            for field_name, msgs in fields.items():
                msgs_list = list(msgs) if isinstance(msgs, (list, tuple)) else [msgs]
                if field_name == "new_password":
                    for m in msgs_list:
                        form.add_error("new_password", str(m))
                elif field_name in ("uid", "token"):
                    form.add_error(None, "Invalid reset link. Open the link from your email again.")
                else:
                    for m in msgs_list:
                        form.add_error(None, str(m))
        else:
            form.add_error(None, "Something went wrong. Try again or request a new reset email.")
        return render(
            request,
            self.template_name,
            {
                "invalid_link": False,
                "form": form,
                "success": False,
            },
        )
