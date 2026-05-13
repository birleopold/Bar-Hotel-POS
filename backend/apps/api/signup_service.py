from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import Membership, MembershipRole, User
from apps.tenants.business_lines import BUSINESS_LINES, DEFAULT_MODULES_ALL
from apps.tenants.models import Outlet, Site, Tenant, TenantSettings


def _unique_tenant_slug(name: str) -> str:
    base = (slugify(name)[:80] or "workspace").strip("-") or "workspace"
    slug = base
    i = 2
    while Tenant.objects.filter(slug=slug).exists():
        suffix = f"-{i}"
        slug = f"{base[: (80 - len(suffix))]}{suffix}"
        i += 1
    return slug


def create_pending_workspace_signup(*, email: str, password: str, workspace_name: str, business_lines: list[str]):
    with transaction.atomic():
        user = User.objects.create_user(email=email, password=password)
        tenant = Tenant.objects.create(
            name=workspace_name,
            slug=_unique_tenant_slug(workspace_name),
            is_active=False,
        )
        Membership.objects.create(user=user, tenant=tenant, role=MembershipRole.OWNER, is_active=True)

        settings_obj, _ = TenantSettings.objects.get_or_create(tenant=tenant)
        settings_obj.business_lines = business_lines
        settings_obj.enabled_staff_modules = list(DEFAULT_MODULES_ALL)
        settings_obj.save(update_fields=["business_lines", "enabled_staff_modules", "updated_at"])

        site = Site.objects.create(tenant=tenant, name="Main site", is_active=True)
        for bl in business_lines:
            p = BUSINESS_LINES.get(bl)
            if not p:
                continue
            Outlet.objects.create(
                site=site,
                name=p.default_outlet_name,
                outlet_type=p.default_outlet_type,
                is_active=True,
            )

    return user, tenant
