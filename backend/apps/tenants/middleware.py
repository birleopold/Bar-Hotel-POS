from __future__ import annotations

import ipaddress
from typing import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.http.request import split_domain_port
from django.utils.cache import patch_vary_headers

from .domains import normalize_hostname, platform_domain_suffix
from .models import TenantDomain


class TenantDomainResolutionMiddleware:
    """Resolve verified active request hosts to branded tenants."""

    CACHE_SECONDS = 60

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.domain_tenant = None
        try:
            raw_host = request.get_host()
            domain, _port = split_domain_port(raw_host)
            if not domain:
                return HttpResponse("Invalid host", status=400, content_type="text/plain")
            bracketless_domain = (
                domain[1:-1]
                if domain.startswith("[") and domain.endswith("]")
                else domain
            )
            try:
                ip = ipaddress.ip_address(bracketless_domain)
            except ValueError:
                host = normalize_hostname(domain)
            else:
                central_host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
                if central_host not in settings.TENANT_CENTRAL_HOSTS:
                    return HttpResponse(
                        "Workspace domain is not configured",
                        status=404,
                        content_type="text/plain",
                    )
                return self.get_response(request)
        except Exception:
            return HttpResponse("Invalid host", status=400, content_type="text/plain")

        key = f"tenant-domain:{host}"
        tenant_id = cache.get(key)
        if tenant_id is None:
            record = TenantDomain.objects.filter(hostname=host).select_related("tenant").first()
            if record and record.status == TenantDomain.Status.ACTIVE and record.tenant.is_active:
                tenant_id = str(record.tenant_id)
            else:
                tenant_id = "~" if record else "!"
            cache.set(key, tenant_id, self.CACHE_SECONDS)
        if tenant_id == "~":
            return HttpResponse("Workspace domain is unavailable", status=404, content_type="text/plain")
        if tenant_id != "!":
            from .models import Tenant

            tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
            if tenant:
                request.domain_tenant = tenant
                request.tenant = tenant

        suffix = platform_domain_suffix()
        if suffix and host.endswith(f".{suffix}") and request.domain_tenant is None:
            return HttpResponse("Workspace domain is unavailable", status=404, content_type="text/plain")
        if request.domain_tenant is None and host not in getattr(settings, "TENANT_CENTRAL_HOSTS", ()):
            return HttpResponse("Workspace domain is not configured", status=404, content_type="text/plain")

        response = self.get_response(request)
        if request.domain_tenant is not None:
            patch_vary_headers(response, ("Host",))
        return response
