from __future__ import annotations

import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.models import CommissionRule, MembershipRole, SalesTarget
from apps.audit.services import log_audit

from .forms import StaffCommissionRuleForm, StaffSalesTargetForm
from .mixins import StaffTenantRequiredMixin
from .services.commissions import build_commission_report
from .services.management import (
    MANAGER_ROLES,
    management_scope,
    management_team,
)
from .services.permissions import membership_can_manage_workspace_settings


class StaffCommissionRuleListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "workspace"
    template_name = "staff/settings/commission_rules.html"
    context_object_name = "commission_rules"

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden(
                "Only an owner or tenant admin can manage commission rules."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            CommissionRule.objects.filter(tenant=self.request.tenant)
            .select_related(
                "membership__user",
                "menu_item",
                "category",
                "created_by",
            )
            .order_by("-is_active", "name")
        )


class _CommissionRuleEditorMixin:
    staff_nav_capability = "workspace"
    model = CommissionRule
    form_class = StaffCommissionRuleForm
    template_name = "staff/settings/commission_rule_form.html"
    success_url = reverse_lazy("staff-workspace-commission-rules")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden(
                "Only an owner or tenant admin can manage commission rules."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return CommissionRule.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw


class StaffCommissionRuleCreateView(_CommissionRuleEditorMixin, CreateView):
    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="commission.rule_created",
            entity_type="commission_rule",
            entity_id=str(self.object.pk),
            payload={
                "name": self.object.name,
                "rate_percent": str(self.object.rate_percent),
                "membership_id": str(self.object.membership_id or ""),
                "menu_item_id": str(self.object.menu_item_id or ""),
                "category_id": str(self.object.category_id or ""),
                "effective_from": str(self.object.effective_from or ""),
                "effective_to": str(self.object.effective_to or ""),
            },
            source="staff",
        )
        messages.success(self.request, "Commission rule created.")
        return response


class StaffCommissionRuleUpdateView(_CommissionRuleEditorMixin, UpdateView):
    pk_url_kwarg = "rule_id"

    def form_valid(self, form):
        before = {
            "name": self.object.name,
            "rate_percent": str(self.object.rate_percent),
            "membership_id": str(self.object.membership_id or ""),
            "menu_item_id": str(self.object.menu_item_id or ""),
            "category_id": str(self.object.category_id or ""),
            "effective_from": str(self.object.effective_from or ""),
            "effective_to": str(self.object.effective_to or ""),
            "is_active": self.object.is_active,
        }
        response = super().form_valid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="commission.rule_updated",
            entity_type="commission_rule",
            entity_id=str(self.object.pk),
            payload={
                "before": before,
                "after": {
                    "name": self.object.name,
                    "rate_percent": str(self.object.rate_percent),
                    "membership_id": str(self.object.membership_id or ""),
                    "menu_item_id": str(self.object.menu_item_id or ""),
                    "category_id": str(self.object.category_id or ""),
                    "effective_from": str(self.object.effective_from or ""),
                    "effective_to": str(self.object.effective_to or ""),
                    "is_active": self.object.is_active,
                },
                "retroactive": False,
            },
            source="staff",
        )
        messages.success(
            self.request,
            "Commission rule updated. Settled sales keep their original commission snapshots.",
        )
        return response


class StaffCommissionReportView(StaffTenantRequiredMixin, View):
    template_name = "staff/management_commissions.html"

    def dispatch(self, request, *args, **kwargs):
        if request.tenant_membership.role not in MANAGER_ROLES:
            return HttpResponseForbidden(
                "Commission reporting is available to managers only."
            )
        return super().dispatch(request, *args, **kwargs)

    def _period(self, request):
        today = timezone.localdate()
        raw_from = (request.GET.get("date_from") or "").strip()
        raw_to = (request.GET.get("date_to") or "").strip()
        date_to = parse_date(raw_to) if raw_to else today
        date_from = (
            parse_date(raw_from)
            if raw_from
            else (date_to - timedelta(days=6) if date_to else None)
        )
        if (
            date_from is None
            or date_to is None
            or date_from > date_to
            or (date_to - date_from).days > 31
            or date_to > today
        ):
            raise ValueError("Choose valid past dates, up to 32 days per report.")
        return date_from, date_to

    def _team(self, request):
        return management_team(request)

    def _context(self, request, *, target_form=None, error=""):
        outlets, _, _ = management_scope(request)
        try:
            date_from, date_to = self._period(request)
        except ValueError as exc:
            return {
                "commission_error": str(exc),
                "commission_report": None,
                "date_from": "",
                "date_to": "",
                "target_form": target_form,
                "sales_targets": [],
            }
        outlet_ids = [outlet.pk for outlet in outlets]
        report = build_commission_report(
            tenant_id=request.tenant.pk,
            date_from=date_from,
            date_to=date_to,
            allowed_outlet_ids=outlet_ids,
            currency=request.tenant.settings.default_currency,
        )
        team = self._team(request)
        targets = list(
            SalesTarget.objects.filter(
                tenant=request.tenant,
                membership__in=team,
                period_start__lte=date_to,
                period_end__gte=date_from,
            )
            .select_related("membership__user", "created_by")
            .order_by("membership__user__email", "period_start")
        )
        return {
            "commission_error": error,
            "commission_report": report,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "target_form": target_form
            or StaffSalesTargetForm(tenant=request.tenant, memberships=team),
            "sales_targets": targets,
        }

    def get(self, request):
        ctx = self._context(request)
        if request.GET.get("export") == "csv" and ctx["commission_report"]:
            report = ctx["commission_report"]
            out = io.StringIO()
            writer = csv.writer(out)

            def safe(value):
                token = str(value or "")
                return "'" + token if token.startswith(
                    ("=", "+", "-", "@", "\t", "\r")
                ) else token

            writer.writerow([
                "worker",
                "gross_sales",
                "sales_reversal",
                "net_sales",
                "gross_commission",
                "mapped_return_reversal",
                "allocated_refund_reversal",
                "net_commission",
                "target_amount",
                "target_progress_percent",
                "currency",
            ])
            for row in report["workers"]:
                writer.writerow([
                    safe(row["worker"]),
                    row["gross_sales"],
                    row["sales_reversal"],
                    row["net_sales"],
                    row["gross_commission"],
                    row["mapped_return_reversal"],
                    row["allocated_refund_reversal"],
                    row["net_commission"],
                    row["target_amount"] if row["target_amount"] is not None else "",
                    row["target_progress_percent"] if row["target_progress_percent"] is not None else "",
                    report["currency"],
                ])
            response = HttpResponse(
                out.getvalue(), content_type="text/csv; charset=utf-8"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="commissions-{ctx["date_from"]}-{ctx["date_to"]}.csv"'
            )
            response["Cache-Control"] = "private, no-store"
            return response
        return render(request, self.template_name, ctx)

    @transaction.atomic
    def post(self, request):
        team = self._team(request)
        form = StaffSalesTargetForm(
            request.POST,
            tenant=request.tenant,
            memberships=team,
        )
        if not form.is_valid():
            ctx = self._context(
                request,
                target_form=form,
                error="Check the target details.",
            )
            return render(request, self.template_name, ctx, status=400)
        target = form.save(commit=False)
        target.tenant = request.tenant
        target.created_by = request.user
        target.save()
        log_audit(
            tenant_id=request.tenant.pk,
            user_id=request.user.pk,
            action="commission.target_created",
            entity_type="sales_target",
            entity_id=str(target.pk),
            payload={
                "membership_id": str(target.membership_id),
                "period_start": str(target.period_start),
                "period_end": str(target.period_end),
                "target_amount": str(target.target_amount),
            },
            source="staff",
        )
        messages.success(request, "Sales target saved.")
        return redirect(
            reverse("staff-management-commissions")
            + f"?date_from={target.period_start}&date_to={target.period_end}"
        )


class StaffSalesTargetUpdateView(StaffTenantRequiredMixin, UpdateView):
    model = SalesTarget
    form_class = StaffSalesTargetForm
    template_name = "staff/sales_target_form.html"
    pk_url_kwarg = "target_id"

    def dispatch(self, request, *args, **kwargs):
        if request.tenant_membership.role not in MANAGER_ROLES:
            return HttpResponseForbidden("Sales target editing is manager-only.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        team = management_team(self.request)
        return SalesTarget.objects.filter(
            tenant=self.request.tenant,
            membership__in=team,
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["memberships"] = management_team(self.request)
        return kw

    def form_valid(self, form):
        before = {
            "membership_id": str(self.object.membership_id),
            "period_start": str(self.object.period_start),
            "period_end": str(self.object.period_end),
            "target_amount": str(self.object.target_amount),
            "note": self.object.note,
        }
        response = super().form_valid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="commission.target_updated",
            entity_type="sales_target",
            entity_id=str(self.object.pk),
            payload={
                "before": before,
                "after": {
                    "membership_id": str(self.object.membership_id),
                    "period_start": str(self.object.period_start),
                    "period_end": str(self.object.period_end),
                    "target_amount": str(self.object.target_amount),
                    "note": self.object.note,
                },
            },
            source="staff",
        )
        messages.success(self.request, "Sales target updated.")
        return response

    def get_success_url(self):
        return (
            reverse("staff-management-commissions")
            + f"?date_from={self.object.period_start}&date_to={self.object.period_end}"
        )
