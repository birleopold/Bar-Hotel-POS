from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy


class StaffTenantRequiredMixin(LoginRequiredMixin):
    """Require login and an active staff session tenant (``request.tenant``)."""

    login_url = reverse_lazy("staff-login")
    #: If set, require this nav capability (or any of the tuple) for the active tenant + role.
    staff_nav_capability: str | tuple[str, ...] | None = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not getattr(request, "tenant", None) or not getattr(request, "tenant_membership", None):
            messages.info(request, "Choose a workspace from the home page first.")
            return redirect("staff-dashboard")
        cap = getattr(self, "staff_nav_capability", None)
        if cap is not None:
            from .services import (
                get_tenant_staff_modules,
                resolve_staff_outlet,
                staff_accessible_outlets,
                staff_nav_capability_allowed,
                staff_nav_visibility_scoped,
            )

            outlets = staff_accessible_outlets(request.tenant_membership)
            current_outlet = resolve_staff_outlet(request, outlets)
            vis = staff_nav_visibility_scoped(
                request.tenant_membership,
                modules=get_tenant_staff_modules(request.tenant, outlet=current_outlet),
                tenant=request.tenant,
                outlet=current_outlet,
            )
            if (
                request.tenant_membership.role == "cleaner"
                and cap in {"lodging", ("lodging", "events")}
                and not getattr(self, "housekeeping_only", False)
            ):
                messages.error(request, "That area is not available for your role.")
                return redirect("staff-dashboard")
            # Some backend pages have stricter manager-only controls even though they
            # share a broader read-only section (for example housekeeping and team admin).
            housekeeping_access = (
                getattr(self, "housekeeping_only", False)
                and request.tenant_membership.role == "cleaner"
                and "lodging" in get_tenant_staff_modules(request.tenant)
                and request.tenant_membership.sites.filter(
                    tenant=request.tenant,
                    is_active=True,
                    outlets__outlet_type="lodging_front_desk",
                    outlets__is_active=True,
                ).exists()
            )
            if not housekeeping_access and not staff_nav_capability_allowed(vis, cap):
                messages.error(
                    request,
                    "That area is not available for your role or your workspace plan.",
                )
                return redirect("staff-dashboard")
        return super().dispatch(request, *args, **kwargs)
