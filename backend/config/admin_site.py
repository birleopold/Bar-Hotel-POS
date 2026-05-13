from __future__ import annotations

import types

from django.contrib.admin.forms import AdminAuthenticationForm


class PlatformAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_superuser or getattr(user, "is_platform_staff", False)):
            raise self.get_invalid_login_error()


def _has_platform_admin_permission(self, request) -> bool:
    user = request.user
    return bool(
        user.is_active
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "is_platform_staff", False))
    )


def configure_platform_admin_site(admin_site) -> None:
    admin_site.login_form = PlatformAdminAuthenticationForm
    admin_site.has_permission = types.MethodType(_has_platform_admin_permission, admin_site)
