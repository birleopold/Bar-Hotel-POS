from __future__ import annotations

import uuid

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import Membership
from apps.staff.middleware import (
    STAFF_SESSION_OUTLET_KEY,
    STAFF_SESSION_SITE_KEY,
    STAFF_SESSION_TENANT_KEY,
)
from apps.staff.services import membership_queryset_for
from apps.tenants.models import Tenant

from .mixins import (
    ConsoleLoginMixin,
    membership_can_manage_org_console,
    user_is_platform_operator,
)


class ConsoleIndexView(ConsoleLoginMixin, TemplateView):
    template_name = "console/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["is_platform_operator"] = user_is_platform_operator(user)
        ctx["memberships"] = list(membership_queryset_for(user)) if user.is_authenticated else []
        ctx["platform_tenants"] = (
            list(Tenant.objects.filter(is_active=True).order_by("name"))
            if ctx["is_platform_operator"]
            else []
        )
        tm = getattr(self.request, "tenant_membership", None)
        ctx["active_tenant"] = getattr(self.request, "tenant", None)
        ctx["can_org_admin"] = bool(
            (tm and membership_can_manage_org_console(tm)) or ctx["is_platform_operator"]
        )
        return ctx


class ConsoleSelectTenantView(ConsoleLoginMixin, View):
    def post(self, request: HttpRequest) -> HttpResponse:
        tid = (request.POST.get("tenant_id") or "").strip()
        try:
            tenant_uuid = uuid.UUID(tid)
        except ValueError:
            messages.error(request, "Invalid workspace.")
            return redirect("console-index")

        if user_is_platform_operator(request.user):
            tenant = Tenant.objects.filter(pk=tenant_uuid, is_active=True).first()
            if tenant is None:
                if Tenant.objects.filter(pk=tenant_uuid).exists():
                    messages.error(request, "This workspace is paused. Restore it from Platform → Workspaces first.")
                else:
                    messages.error(request, "Workspace not found.")
                return redirect("console-index")
        else:
            membership = (
                Membership.objects.filter(user=request.user, tenant_id=tenant_uuid, is_active=True)
                .select_related("tenant")
                .first()
            )
            if membership is None:
                messages.error(request, "You are not a member of that workspace.")
                return redirect("console-index")
            if not membership.tenant.is_active:
                messages.info(request, "This workspace is pending platform approval.")
                return redirect("staff-pending-approval")

        messages.success(request, "Workspace updated.")
        request.session[STAFF_SESSION_TENANT_KEY] = str(tenant_uuid)
        request.session.pop(STAFF_SESSION_OUTLET_KEY, None)
        request.session.pop(STAFF_SESSION_SITE_KEY, None)
        next_url = (request.POST.get("next") or "").strip()
        if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = reverse("console-index")
        return redirect(next_url)
