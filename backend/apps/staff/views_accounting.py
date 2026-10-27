from __future__ import annotations

import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.finance.accounting_bridge import (
    build_accounting_preview,
    create_accounting_export,
)
from apps.finance.models import AccountingExportBatch, AccountingMapping
from .forms import StaffAccountingMappingForm
from .mixins import StaffTenantRequiredMixin
from .services.membership import staff_accessible_outlets
from .services.permissions import membership_can_manage_workspace_settings


ACCOUNTING_EXPORT_ROLES = {
    MembershipRole.OWNER,
    MembershipRole.TENANT_ADMIN,
    MembershipRole.ACCOUNTANT,
}


def _accounting_period(request):
    today = timezone.localdate()
    raw_from = (request.GET.get("date_from") or request.POST.get("date_from") or "").strip()
    raw_to = (request.GET.get("date_to") or request.POST.get("date_to") or "").strip()
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
        or (date_to - date_from).days > 366
        or date_to > today
    ):
        raise ValueError("Choose valid past dates, up to 367 days per accounting export.")
    return date_from, date_to


def _safe_csv(value):
    token = str(value or "")
    return "'" + token if token.startswith(("=", "+", "-", "@", "\t", "\r")) else token


def _batch_csv(batch: AccountingExportBatch) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "date_from",
        "date_to",
        "currency",
        "account_code",
        "account_name",
        "debit",
        "credit",
        "memo",
        "site",
        "site_id",
        "outlet",
        "outlet_id",
        "register",
        "cashier",
        "tender",
        "category",
        "folio",
        "supplier",
        "source_references",
    ])
    for line in batch.journal_lines:
        dims = line.get("dimensions") or {}
        writer.writerow([
            batch.date_from,
            batch.date_to,
            _safe_csv(batch.currency),
            _safe_csv(line.get("account_code")),
            _safe_csv(line.get("account_name")),
            line.get("debit", "0.00"),
            line.get("credit", "0.00"),
            _safe_csv(line.get("memo")),
            _safe_csv(dims.get("site")),
            _safe_csv(dims.get("site_id")),
            _safe_csv(dims.get("outlet")),
            _safe_csv(dims.get("outlet_id")),
            _safe_csv(dims.get("register")),
            _safe_csv(dims.get("cashier")),
            _safe_csv(dims.get("tender")),
            _safe_csv(dims.get("category")),
            _safe_csv(dims.get("folio")),
            _safe_csv(dims.get("supplier")),
            _safe_csv(";".join(line.get("source_refs") or [])),
        ])
    return out.getvalue()


class StaffAccountingMappingListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "workspace"
    template_name = "staff/settings/accounting_mappings.html"
    context_object_name = "accounting_mappings"

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden(
                "Only an owner or tenant admin can manage accounting mappings."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return AccountingMapping.objects.filter(
            tenant=self.request.tenant
        ).order_by("kind", "source_label", "account_code")


class _AccountingMappingEditorMixin:
    staff_nav_capability = "workspace"
    model = AccountingMapping
    form_class = StaffAccountingMappingForm
    template_name = "staff/settings/accounting_mapping_form.html"
    success_url = reverse_lazy("staff-workspace-accounting-mappings")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden(
                "Only an owner or tenant admin can manage accounting mappings."
            )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return AccountingMapping.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw


class StaffAccountingMappingCreateView(_AccountingMappingEditorMixin, CreateView):
    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="accounting.mapping_created",
            entity_type="accounting_mapping",
            entity_id=str(self.object.pk),
            payload={
                "kind": self.object.kind,
                "source_key": self.object.source_key,
                "source_label": self.object.source_label,
                "account_code": self.object.account_code,
                "account_name": self.object.account_name,
            },
            source="staff",
        )
        messages.success(self.request, "Accounting mapping created.")
        return response


class StaffAccountingMappingUpdateView(_AccountingMappingEditorMixin, UpdateView):
    pk_url_kwarg = "mapping_id"

    def form_valid(self, form):
        before = {
            "kind": self.object.kind,
            "source_key": self.object.source_key,
            "source_label": self.object.source_label,
            "account_code": self.object.account_code,
            "account_name": self.object.account_name,
            "is_active": self.object.is_active,
        }
        response = super().form_valid(form)
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="accounting.mapping_updated",
            entity_type="accounting_mapping",
            entity_id=str(self.object.pk),
            payload={
                "before": before,
                "after": {
                    "kind": self.object.kind,
                    "source_key": self.object.source_key,
                    "source_label": self.object.source_label,
                    "account_code": self.object.account_code,
                    "account_name": self.object.account_name,
                    "is_active": self.object.is_active,
                },
                "historical_exports_changed": False,
            },
            source="staff",
        )
        messages.success(
            self.request,
            "Accounting mapping updated. Existing export batches remain unchanged.",
        )
        return response


class StaffAccountingExportView(StaffTenantRequiredMixin, View):
    template_name = "staff/accounting_export.html"

    def dispatch(self, request, *args, **kwargs):
        if request.tenant_membership.role not in ACCOUNTING_EXPORT_ROLES:
            return HttpResponseForbidden(
                "Accounting exports are available to owners, tenant admins and accountants."
            )
        return super().dispatch(request, *args, **kwargs)

    def _outlets(self, request):
        return list(staff_accessible_outlets(request.tenant_membership))

    def _preview(self, request):
        date_from, date_to = _accounting_period(request)
        outlets = self._outlets(request)
        preview = build_accounting_preview(
            tenant_id=request.tenant.pk,
            date_from=date_from,
            date_to=date_to,
            allowed_outlet_ids=[outlet.pk for outlet in outlets],
            currency=request.tenant.settings.default_currency,
        )
        return preview, outlets

    def _history(self, request, outlets):
        allowed = {str(outlet.pk) for outlet in outlets}
        rows = []
        for batch in (
            AccountingExportBatch.objects.filter(tenant=request.tenant)
            .select_related("generated_by")
            .order_by("-created_at")[:100]
        ):
            scope = set(batch.scope_outlet_ids or [])
            if scope.issubset(allowed):
                rows.append(batch)
            if len(rows) >= 30:
                break
        return rows

    def get(self, request):
        try:
            preview, outlets = self._preview(request)
            error = ""
        except ValueError as exc:
            preview, outlets, error = None, self._outlets(request), str(exc)
        return render(
            request,
            self.template_name,
            {
                "accounting_preview": preview,
                "accounting_error": error,
                "accounting_outlets": outlets,
                "accounting_exports": self._history(request, outlets),
            },
            status=400 if error else 200,
        )

    def post(self, request):
        try:
            preview, outlets = self._preview(request)
        except ValueError as exc:
            return render(
                request,
                self.template_name,
                {
                    "accounting_preview": None,
                    "accounting_error": str(exc),
                    "accounting_outlets": self._outlets(request),
                    "accounting_exports": [],
                },
                status=400,
            )
        if not preview["ready"]:
            messages.error(
                request,
                "Complete the missing mappings and resolve any journal imbalance before generating an export.",
            )
            return render(
                request,
                self.template_name,
                {
                    "accounting_preview": preview,
                    "accounting_error": "",
                    "accounting_outlets": outlets,
                    "accounting_exports": self._history(request, outlets),
                },
                status=409,
            )
        batch, replay = create_accounting_export(
            tenant_id=request.tenant.pk,
            preview=preview,
            allowed_outlet_ids=[outlet.pk for outlet in outlets],
            user=request.user,
        )
        if not replay:
            log_audit(
                tenant_id=request.tenant.pk,
                user_id=request.user.pk,
                action="accounting.export_generated",
                entity_type="accounting_export",
                entity_id=str(batch.pk),
                payload={
                    "date_from": str(batch.date_from),
                    "date_to": str(batch.date_to),
                    "currency": batch.currency,
                    "line_count": batch.line_count,
                    "total_debit": str(batch.total_debit),
                    "total_credit": str(batch.total_credit),
                    "fingerprint": batch.fingerprint,
                    "outlet_ids": batch.scope_outlet_ids,
                },
                source="staff",
            )
        messages.success(
            request,
            "Existing identical export reused."
            if replay
            else "Accounting export generated and frozen.",
        )
        return redirect("staff-accounting-export-download", batch_id=batch.pk)


class StaffAccountingExportDownloadView(StaffAccountingExportView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, batch_id):
        batch = AccountingExportBatch.objects.filter(
            tenant=request.tenant,
            pk=batch_id,
        ).first()
        if batch is None:
            raise Http404
        allowed = {str(outlet.pk) for outlet in self._outlets(request)}
        if not set(batch.scope_outlet_ids or []).issubset(allowed):
            raise Http404
        body = _batch_csv(batch)
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="accounting-journal-{batch.date_from}-{batch.date_to}-{str(batch.pk)[:8]}.csv"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
