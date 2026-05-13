from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from apps.api.web_password_reset import StaffPasswordResetConfirmView
from apps.api.web_signup import PublicSignupView
from config.admin_site import configure_platform_admin_site

configure_platform_admin_site(admin.site)


def root_entry(request):
    if request.user.is_authenticated:
        return redirect("staff-dashboard")
    return redirect("staff-login")


urlpatterns = [
    path("", root_entry, name="root-entry"),
    path("signup/", PublicSignupView.as_view(), name="public-signup"),
    path("admin/", admin.site.urls),
    path(
        "password-reset/confirm/",
        StaffPasswordResetConfirmView.as_view(),
        name="staff-password-reset-confirm",
    ),
    path("staff/", include("apps.staff.urls")),
    path("console/", include("apps.console.urls")),
    path("api/v1/", include("apps.api.urls")),
]
