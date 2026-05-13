"""Django Admin gates: tenant data editable in the web console, not by customer admins."""

from __future__ import annotations

from django.contrib import admin


class PlatformOperatorModelAdmin(admin.ModelAdmin):
    """
    Only superusers and users with ``is_platform_staff`` may access this model in Django Admin.
    Tenant administrators use the Staff app and ``/console/`` instead.
    """

    def _platform_operator(self, request) -> bool:
        u = request.user
        return bool(
            u.is_authenticated and (u.is_superuser or getattr(u, "is_platform_staff", False)),
        )

    def has_module_permission(self, request) -> bool:
        return self._platform_operator(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self._platform_operator(request)

    def has_add_permission(self, request) -> bool:
        return self._platform_operator(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._platform_operator(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._platform_operator(request)
