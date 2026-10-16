"""Shared search endpoint for full-page search and fast command palette."""
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from .mixins import StaffTenantRequiredMixin
from .services.search import staff_global_search
from .services.membership import staff_accessible_outlets
from .services.workspace import resolve_staff_outlet


class StaffGlobalSearchView(StaffTenantRequiredMixin, View):
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        query = (request.GET.get("q") or "").strip()[:80]
        wants_json = request.GET.get("format") == "json"
        try:
            page_number = max(1, min(int(request.GET.get("page", "1")), 100))
        except (TypeError, ValueError):
            page_number = 1
        # Lightweight per-user rate limit protects searchable personal records.
        # A distributed cache is needed to enforce a fleet-wide limit.
        cache_key = f"staff-search:{request.tenant.pk}:{request.user.pk}"
        if wants_json:
            if cache.add(cache_key, 1, timeout=3):
                count = 1
            else:
                try:
                    count = cache.incr(cache_key)
                except (ValueError, NotImplementedError):
                    cache.set(cache_key, 1, timeout=3)
                    count = 1
            if count > 12:
                response = JsonResponse(
                    {"groups": [], "error": "Too many searches. Try again shortly."},
                    status=429,
                )
                response["Retry-After"] = "3"
                response["Cache-Control"] = "private, no-store"
                return response
        groups = staff_global_search(
            tenant=request.tenant, membership=request.tenant_membership,
            user=request.user, query=query,
            per_group=5 if wants_json else 8,
            page=1 if wants_json else page_number,
            current_outlet=resolve_staff_outlet(
                request, staff_accessible_outlets(request.tenant_membership),
            ),
        )
        if wants_json:
            response = JsonResponse({"groups": groups, "query": query})
        else:
            response = render(request, "staff/search/index.html", {
                "query": query, "search_groups": groups,
                "search_page": page_number,
                "previous_page": page_number - 1 if page_number > 1 else None,
                "next_page": page_number + 1 if any(
                    group.get("has_more") for group in groups
                ) and page_number < 100 else None,
            })
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie"
        return response
