"""Business-date configuration; safe read-only preview and scoped settings."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden, Http404
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.tenants.business_date import business_date_for, effective_business_clock
from apps.tenants.models import Site, TenantSettings
from .mixins import StaffTenantRequiredMixin
from .services import staff_accessible_outlets


class StaffBusinessDateView(StaffTenantRequiredMixin, TemplateView):
    template_name = "staff/business_date.html"
    staff_nav_capability = "workspace"

    def _allowed_roles(self):
        return {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.SITE_MANAGER}

    def _can_edit_global(self):
        return self.request.tenant_membership.role in {
            MembershipRole.OWNER, MembershipRole.TENANT_ADMIN,
        }

    def _visible_sites(self):
        qs = Site.objects.filter(tenant=self.request.tenant).order_by("name")
        if self._can_edit_global():
            return qs
        permitted = {o.site_id for o in staff_accessible_outlets(self.request.tenant_membership)}
        return qs.filter(pk__in=permitted)

    def dispatch(self, request, *args, **kwargs):
        if request.tenant_membership.role not in self._allowed_roles():
            return HttpResponseForbidden("Business date settings are available to property managers.")
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _valid_timezone(value):
        if not value or len(value) > 64:
            raise ValueError("Enter a time zone such as Africa/Kampala.")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("Use a valid time zone, such as Africa/Kampala.") from exc
        return value

    @staticmethod
    def _hour(value, *, optional=False):
        if optional and value == "":
            return None
        try:
            hour = int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Choose a closing hour between 0 and 23.") from exc
        if str(hour) != str(value).strip() or not 0 <= hour <= 23:
            raise ValueError("Choose a closing hour between 0 and 23.")
        return hour

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        settings, _ = TenantSettings.objects.get_or_create(tenant=self.request.tenant)
        ctx["business_settings"] = settings
        ctx["can_edit_global"] = self._can_edit_global()
        rows = []
        for site in self._visible_sites():
            try:
                _zone, hour, name = effective_business_clock(
                    tenant=self.request.tenant, site=site,
                )
                current_date = business_date_for(tenant=self.request.tenant, site=site)
            except ValueError:
                hour, name, current_date = None, "Check time zone", None
            rows.append({
                "site": site, "timezone": name,
                "cutover_hour": hour, "business_date": current_date,
            })
        ctx["property_dates"] = rows
        return ctx

    def post(self, request, *args, **kwargs):
        scope = request.POST.get("scope", "")
        try:
            with transaction.atomic():
                if scope == "tenant":
                    if not self._can_edit_global():
                        return HttpResponseForbidden("Only the business owner can change the default.")
                    name = self._valid_timezone((request.POST.get("timezone") or "").strip())
                    hour = self._hour(request.POST.get("cutover_hour"))
                    settings, _ = TenantSettings.objects.select_for_update().get_or_create(
                        tenant=request.tenant,
                    )
                    settings.default_timezone = name
                    settings.business_day_cutover_hour = hour
                    settings.save(update_fields=[
                        "default_timezone", "business_day_cutover_hour", "updated_at",
                    ])
                    audit_id = str(request.tenant.pk)
                    audit_action = "operations.business_date_default_changed"
                    payload = {"timezone": name, "cutover_hour": hour}
                elif scope == "site":
                    site = self._visible_sites().select_for_update().filter(
                        pk=request.POST.get("site_id"),
                    ).first()
                    if site is None:
                        raise Http404("Property not available")
                    name = (request.POST.get("timezone") or "").strip()
                    if name:
                        self._valid_timezone(name)
                    hour = self._hour(request.POST.get("cutover_hour", ""), optional=True)
                    site.business_timezone = name
                    site.business_day_cutover_hour = hour
                    site.save(update_fields=[
                        "business_timezone", "business_day_cutover_hour", "updated_at",
                    ])
                    audit_id = str(site.pk)
                    audit_action = "operations.business_date_property_changed"
                    payload = {"timezone_override": name, "cutover_hour_override": hour}
                else:
                    raise ValueError("Choose an operating-day settings form.")
                log_audit(
                    tenant_id=request.tenant.pk, user_id=request.user.pk,
                    action=audit_action, entity_type="business_date_setting",
                    entity_id=audit_id, payload=payload,
                )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Operating day settings saved.")
        return redirect("staff-business-date")
