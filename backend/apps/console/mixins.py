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
        has_tenant_scope = bool(getattr(request, "tenant", None))
        has_member_access = bool(getattr(request, "tenant_membership", None))
        platform_scope = user_is_platform_operator(request.user) and has_tenant_scope
        if not has_tenant_scope or (not has_member_access and not platform_scope):
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
            if (
                t is not None
                and tm is not None
                and not user_is_platform_operator(request.user)
                and not membership_can_manage_org_console(tm)
            ):
                messages.error(
                    request,
                    "Only an owner or tenant admin can manage organization setup here.",
                )
                return redirect("console-index")
            if t is not None and tm is not None:
                from .services import console_business_line_flags

                url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
                flags = console_business_line_flags(t)
                try:
                    configured_lines = list(t.settings.business_lines or [])
                except Exception:
                    configured_lines = []
                if not configured_lines and url_name != "console-org-setup":
                    messages.error(request, "Choose the business areas for this workspace first.")
                    return redirect("console-org-setup")
                url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
                lodging_page = url_name.startswith("console-org-room")
                catalog_page = url_name.startswith("console-org-menu-") or url_name.startswith(
                    "console-org-modifier-"
                )
                service_page = url_name.startswith("console-org-service-")
                if lodging_page and not flags["console_has_lodging"]:
                    messages.error(request, "Lodging is not enabled for this business.")
                    return redirect("console-org-setup")
                if catalog_page and not (
                    flags["console_has_fnb"] or flags["console_has_retail"]
                ):
                    messages.error(request, "Item and menu setup is not enabled for this business.")
                    return redirect("console-org-setup")
                if service_page and not flags["console_has_services"]:
                    messages.error(request, "Services are not enabled for this business.")
                    return redirect("console-org-setup")
        return super().dispatch(request, *args, **kwargs)


class PlatformOperatorRequiredMixin(ConsoleLoginMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not user_is_platform_operator(request.user):
            messages.error(request, "You do not have platform operator access.")
            return redirect("console-index")
        return super().dispatch(request, *args, **kwargs)
