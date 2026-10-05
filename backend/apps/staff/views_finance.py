from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, ListView

from apps.finance.models import CashbookEntry, FinanceCategory, FinanceCategoryKind
from apps.accounts.models import MembershipRole
from apps.tenants.models import Site

from .forms import StaffCashbookEntryForm, StaffFinanceCategoryForm
from .mixins import StaffTenantRequiredMixin
from .report_csv import format_cashbook_csv
from .services import sites_visible_for_membership


def _parse_range(request: HttpRequest) -> tuple[date, date, list[str]]:
    today = timezone.localdate()
    d0 = today - timedelta(days=30)
    d1 = today
    errs: list[str] = []
    raw_from = request.GET.get("date_from")
    raw_to = request.GET.get("date_to")
    if raw_from:
        try:
            d0 = date.fromisoformat(raw_from)
        except ValueError:
            errs.append("Invalid start date.")
    if raw_to:
        try:
            d1 = date.fromisoformat(raw_to)
        except ValueError:
            errs.append("Invalid end date.")
    if not errs and d0 > d1:
        errs.append("Start date must be on or before end date.")
    return d0, d1, errs


class StaffFinanceEntryListView(StaffTenantRequiredMixin, ListView):
    staff_nav_capability = "finance"
    template_name = "staff/finance/entries_list.html"
    context_object_name = "entries"
    paginate_by = 40

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if (request.GET.get("format") or "").strip().lower() == "csv":
            self.object_list = self.get_queryset()
            if getattr(self, "_date_errors", []):
                return HttpResponse(
                    "\n".join(self._date_errors),
                    status=400,
                    content_type="text/plain; charset=utf-8",
                )
            return self._csv_response()
        return super().get(request, *args, **kwargs)

    def _csv_response(self) -> HttpResponse:
        body = format_cashbook_csv(self.object_list)
        d0, d1 = self._d0, self._d1
        resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="cashbook-entries-{d0.isoformat()}_{d1.isoformat()}.csv"'
        )
        return resp

    def get_queryset(self):
        d0, d1, self._date_errors = _parse_range(self.request)
        self._d0, self._d1 = d0, d1
        if self._date_errors:
            return CashbookEntry.objects.none()
        qs = (
            CashbookEntry.objects.filter(tenant=self.request.tenant, transaction_date__gte=d0, transaction_date__lte=d1)
            .select_related("category", "site", "created_by")
            .order_by("-transaction_date", "-created_at")
        )
        membership = self.request.tenant_membership
        if membership.role not in (MembershipRole.OWNER, MembershipRole.TENANT_ADMIN, MembershipRole.ACCOUNTANT):
            qs = qs.filter(site_id__in=[site.id for site in self._membership_sites()])
        kind = (self.request.GET.get("kind") or "").strip().lower()
        if kind == "income":
            qs = qs.filter(category__kind=FinanceCategoryKind.INCOME)
        elif kind == "expense":
            qs = qs.filter(category__kind=FinanceCategoryKind.EXPENSE)
        return qs

    def _membership_sites(self):
        return sites_visible_for_membership(self.request.tenant_membership)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["date_from"] = self._d0
        ctx["date_to"] = self._d1
        ctx["date_errors"] = getattr(self, "_date_errors", [])
        ctx["kind_filter"] = (self.request.GET.get("kind") or "").strip().lower()

        if ctx["date_errors"]:
            ctx["total_income"] = Decimal("0")
            ctx["total_expense"] = Decimal("0")
            ctx["net_cash"] = Decimal("0")
            ctx["has_categories"] = FinanceCategory.objects.filter(tenant=self.request.tenant, is_active=True).exists()
            return ctx

        entries = CashbookEntry.objects.filter(
            tenant=self.request.tenant,
            transaction_date__gte=self._d0,
            transaction_date__lte=self._d1,
        )
        if self.request.tenant_membership.role not in (
            MembershipRole.OWNER,
            MembershipRole.TENANT_ADMIN,
        ):
            entries = entries.filter(site_id__in=[site.id for site in sites_visible_for_membership(self.request.tenant_membership)])
        income = entries.filter(category__kind=FinanceCategoryKind.INCOME).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        expense = entries.filter(category__kind=FinanceCategoryKind.EXPENSE).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        ctx["total_income"] = income.quantize(Decimal("0.01"))
        ctx["total_expense"] = expense.quantize(Decimal("0.01"))
        ctx["net_cash"] = (income - expense).quantize(Decimal("0.01"))
        ctx["has_categories"] = FinanceCategory.objects.filter(tenant=self.request.tenant, is_active=True).exists()
        return ctx


class StaffFinanceEntryCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "finance"
    template_name = "staff/finance/entry_form.html"
    form_class = StaffCashbookEntryForm

    def get_initial(self):
        return {"transaction_date": timezone.localdate()}

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self._sites = list(sites_visible_for_membership(request.tenant_membership))
        self._categories = FinanceCategory.objects.filter(tenant=request.tenant, is_active=True).order_by(
            "kind", "name"
        )
        if not self._categories.exists():
            messages.info(request, "Add at least one income or expense category first.")
            return redirect("staff-finance-categories-new")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant_id"] = self.request.tenant.id
        kw["sites"] = Site.objects.filter(id__in=[s.id for s in self._sites])
        kw["categories"] = self._categories
        return kw

    def form_valid(self, form):
        entry = form.save(commit=False)
        site = entry.site
        if site and site not in self._sites:
            form.add_error("site", "Choose a branch assigned to your role.")
            return self.form_invalid(form)
        entry.created_by = self.request.user
        entry.save()
        messages.success(self.request, "Income or expense recorded.")
        return redirect("staff-finance-entries")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sites"] = self._sites
        return ctx


class StaffFinanceCategoryCreateView(StaffTenantRequiredMixin, FormView):
    staff_nav_capability = "finance"
    template_name = "staff/finance/category_form.html"
    form_class = StaffFinanceCategoryForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant_id"] = self.request.tenant.id
        return kw

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Category saved.")
        return redirect("staff-finance-entries")
