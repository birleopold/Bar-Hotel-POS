from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy

from apps.accounts.models import MembershipRole


def user_is_platform_operator(user) -> bool:
    return bool(user.is_superuser or getattr(user, "is_platform_staff", False))


def membership_can_manage_org_console(membership) -> bool:
    """Sites, outlets, and lodging inventory setup (no Django Admin)."""
    return membership.role in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)


class ConsoleLoginMixin(LoginRequiredMixin):
    login_url = reverse_lazy("staff-login")


class ConsoleTenantRequiredMixin(ConsoleLoginMixin):
    """Require the same workspace session as Staff (``request.tenant``)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not getattr(request, "tenant", None) or not getattr(request, "tenant_membership", None):
            messages.info(
                request,
                "Choose a workspace on the Staff home page first, then open Console again.",
            )
            return redirect("staff-dashboard")
        if not getattr(request.tenant, "is_active", True):
            messages.info(request, "This workspace is pending platform approval.")
            return redirect("staff-pending-approval")
        return super().dispatch(request, *args, **kwargs)


class ConsoleOrgAdminRequiredMixin(ConsoleTenantRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            tm = getattr(request, "tenant_membership", None)
            t = getattr(request, "tenant", None)
            if t is not None and tm is not None and not membership_can_manage_org_console(tm):
                messages.error(
                    request,
                    "Only an owner or tenant admin can manage organization setup here.",
                )
                return redirect("console-index")
        return super().dispatch(request, *args, **kwargs)


class PlatformOperatorRequiredMixin(ConsoleLoginMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not user_is_platform_operator(request.user):
            messages.error(request, "You do not have platform operator access.")
            return redirect("console-index")
        return super().dispatch(request, *args, **kwargs)
