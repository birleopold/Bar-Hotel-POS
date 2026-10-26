from __future__ import annotations

from apps.staff.services import membership_queryset_for
from apps.tenants.business_lines import normalize_business_lines
from apps.tenants.models import Tenant, TenantSettings

from .mixins import membership_can_manage_org_console, user_is_platform_operator
from .services import console_business_line_flags


def console_nav(request):
    path = getattr(request, "path", "") or ""
    if not path.startswith("/console"):
        return {"console_nav": None}

    user = getattr(request, "user", None)
    memberships = list(membership_queryset_for(user)) if getattr(user, "is_authenticated", False) else []
    tm = getattr(request, "tenant_membership", None)
    active_tenant = getattr(request, "tenant", None)
    platform_operator = user_is_platform_operator(user) if getattr(user, "is_authenticated", False) else False
    url_name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    platform_control_page = platform_operator and url_name.startswith("console-platform-")
    if platform_control_page:
        # The platform control plane is the owner's neutral workspace manager.
        # A previously selected tenant may remain in the shared staff session for
        # organization administration, but must never brand or scope platform pages.
        active_tenant = None
    platform_tenants = (
        list(Tenant.objects.filter(is_active=True).order_by("name")) if platform_operator else []
    )

    base_ctx = {
        "console_nav": None,
        "grocery_console_shell": False,
        "hospitality_console_shell": False,
        "fizo_setup_area": path.startswith("/console/org/"),
        "console_memberships": memberships,
        "console_platform_tenants": platform_tenants,
        "console_is_platform_operator": platform_operator,
        "console_active_tenant": active_tenant,
        "console_can_org_admin": bool(
            (tm and membership_can_manage_org_console(tm)) or platform_operator
        ),
    }

    if active_tenant is None:
        return base_ctx

    flags = console_business_line_flags(active_tenant)
    try:
        business_lines = normalize_business_lines(active_tenant.settings.business_lines)
    except TenantSettings.DoesNotExist:
        business_lines = []
    # A store keeps its familiar administration shell when hospitality
    # features are enabled alongside retail, rather than dropping to an
    # unrelated console layout.
    has_store_line = bool(set(business_lines) & {"retail", "supermarket"})
    base_ctx["grocery_console_shell"] = bool(
        tm and membership_can_manage_org_console(tm)
        and has_store_line
        and not platform_operator
    )
    has_hospitality_line = bool(set(business_lines) & {"bar", "lounge", "restaurant", "cafeteria", "kitchen", "lodging"})
    base_ctx["hospitality_console_shell"] = bool(
        tm and membership_can_manage_org_console(tm)
        and has_hospitality_line and not has_store_line and not platform_operator
    )
    return {**base_ctx, "console_nav": flags, **flags}
