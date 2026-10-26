import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import include, path
from django.views.decorators.http import require_safe

from apps.api.web_password_reset import StaffPasswordResetConfirmView, StaffPasswordRecoveryRequestView
from apps.api.web_signup import PublicSignupView
from config.admin_site import configure_platform_admin_site

configure_platform_admin_site(admin.site)


@require_safe
def root_entry(request):
    if request.user.is_authenticated:
        return redirect("staff-dashboard")
    return redirect("staff-login")


@require_safe
def public_product_media(request, path):
    """Serve public product photos when the reverse proxy has no media handler yet."""
    product_root = Path(settings.MEDIA_ROOT) / "products"
    try:
        candidate = (product_root / path).resolve(strict=True)
        root = product_root.resolve(strict=True)
    except (FileNotFoundError, OSError):
        raise Http404
    if root not in candidate.parents or not candidate.is_file():
        raise Http404
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    response = FileResponse(candidate.open("rb"), content_type=content_type)
    response["Cache-Control"] = "public, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


urlpatterns = [
    path("media/products/<path:path>", public_product_media, name="public-product-media"),
    path("", root_entry, name="root-entry"),
    path("signup/", PublicSignupView.as_view(), name="public-signup"),
    path("password-reset/", StaffPasswordRecoveryRequestView.as_view(), name="staff-password-reset-request"),
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
