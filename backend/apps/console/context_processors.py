from __future__ import annotations

from apps.staff.services import membership_queryset_for
from apps.tenants.models import Tenant

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
    platform_tenants = (
        list(Tenant.objects.filter(is_active=True).order_by("name")) if platform_operator else []
    )

    base_ctx = {
        "console_nav": None,
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
    return {**base_ctx, "console_nav": flags, **flags}
