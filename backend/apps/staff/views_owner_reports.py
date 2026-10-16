"""Owner report schedule settings and delivery history, exposed through staff UI."""
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.models import Membership, MembershipRole
from apps.api.owner_reports import build_pdf_summary, _summary_for_schedule
from apps.staff.report_csv import format_sales_summary_csv_from_summary
from apps.tenants.models import (
    OwnerReportSchedule, OwnerReportDelivery,
    OwnerReportFrequency, Site, TenantSettings,
)

from .mixins import StaffTenantRequiredMixin


class OwnerReportScheduleForm(forms.ModelForm):
    recipients = forms.ModelMultipleChoiceField(
        label="People who will receive these reports",
        queryset=Membership.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = OwnerReportSchedule
        fields = (
            "is_enabled", "site", "frequency", "local_send_hour",
            "send_weekday", "send_monthday", "recipients",
        )
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "site": forms.Select(attrs={"class": "staff-input"}),
            "frequency": forms.Select(attrs={"class": "staff-input"}),
            "local_send_hour": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0", "max": "23",
            }),
            "send_weekday": forms.NumberInput(attrs={
                "class": "staff-input", "min": "0", "max": "6",
            }),
            "send_monthday": forms.NumberInput(attrs={
                "class": "staff-input", "min": "1", "max": "28",
            }),
        }

    def __init__(self, *args, tenant, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = Site.objects.filter(
            tenant=tenant, is_active=True,
        ).order_by("name")
        self.fields["site"].empty_label = "All business sections (UTC calendar)"
        allowed = Membership.objects.filter(
            tenant=tenant, is_active=True, user__is_active=True,
            role__in=[MembershipRole.OWNER, MembershipRole.TENANT_ADMIN],
        ).select_related("user").order_by("user__email")
        self.fields["recipients"].queryset = allowed
        self.fields["recipients"].label_from_instance = lambda obj: obj.user.email

    def clean(self):
        data = super().clean()
        if data.get("is_enabled") and not data.get("recipients"):
            self.add_error("recipients", "Select at least one active owner or administrator.")
        return data


class StaffOwnerReportSettingsView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "workspace"
    http_method_names = ["get", "post", "head", "options"]

    def dispatch(self, request, *args, **kwargs):
        m = getattr(request, "tenant_membership", None)
        if m and (
            not m.is_active or
            m.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN)
        ):
            return HttpResponseForbidden("Only a workspace owner or administrator may manage scheduled reports.")
        if request.session.get("staff_pin_authenticated"):
            return HttpResponseForbidden(
                "Sign in with your account password to configure report emails."
            )
        return super().dispatch(request, *args, **kwargs)

    def _schedule(self, request):
        schedule, _ = OwnerReportSchedule.objects.get_or_create(
            tenant=request.tenant,
            defaults={"is_enabled": False},
        )
        return schedule

    def _render(self, request, *, form=None):
        schedule = self._schedule(request)
        if form is None:
            form = OwnerReportScheduleForm(instance=schedule, tenant=request.tenant)
        return render(request, "staff/settings/owner_reports.html", {
            "form": form, "schedule": schedule,
            "history": OwnerReportDelivery.objects.filter(
                tenant=request.tenant, schedule=schedule,
            ).order_by("-created_at")[:25],
        })

    def _download_sample(self, request, format):
        schedule = self._schedule(request)
        site = schedule.site
        if site and site.tenant_id != request.tenant.pk:
            return HttpResponseForbidden("Property is outside your business.")
        # A preview is always the last completed day in the configured
        # clock. No email or financial operation is performed.
        zone_name = (site.business_timezone if site else None) or (
            request.tenant.settings.default_timezone
        )
        try:
            local_today = timezone.now().astimezone(
                ZoneInfo(zone_name or "UTC"),
            ).date()
        except ZoneInfoNotFoundError:
            messages.error(request, "Correct the business timezone before previewing.")
            return redirect("staff-owner-report-settings")
        d = local_today - timedelta(days=1)
        period = (d, d)
        summary = _summary_for_schedule(schedule, period)
        if format == "csv":
            resp = HttpResponse(
                format_sales_summary_csv_from_summary(summary),
                content_type="text/csv; charset=utf-8",
            )
            resp["Content-Disposition"] = 'attachment; filename="owner-report-preview.csv"'
        else:
            pdf = build_pdf_summary(schedule=schedule, period=period, summary=summary)
            resp = HttpResponse(pdf, content_type="application/pdf")
            resp["Content-Disposition"] = 'attachment; filename="owner-report-preview.pdf"'
        resp["Cache-Control"] = "private, no-store"
        return resp

    def get(self, request):
        sample = request.GET.get("preview")
        if sample in ("pdf", "csv"):
            return self._download_sample(request, sample)
        return self._render(request)

    def post(self, request):
        schedule = self._schedule(request)
        form = OwnerReportScheduleForm(
            request.POST, instance=schedule, tenant=request.tenant,
        )
        if not form.is_valid():
            return self._render(request, form=form)
        config = form.save(commit=False)
        config.tenant = request.tenant
        config.full_clean(exclude=["recipients"])
        config.save()
        form.save_m2m()
        messages.success(
            request,
            "Report preferences saved. Automatic emails run only while enabled, "
            "with configured email delivery and scheduled workers.",
        )
        return redirect("staff-owner-report-settings")
