from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.audit.models import AuditEvent
from apps.audit.services import log_audit
from apps.catalog.models import Promotion
from apps.catalog.promotion_labels import queue_markdown_labels_for_promotion
from apps.pos.models import Order

from .forms import StaffPromotionForm
from .mixins import StaffTenantRequiredMixin
from .services import membership_can_manage_workspace_settings




REPORT_WINDOWS = {7, 30, 90, 365}


def _report_window_days(request) -> int:
    try:
        value = int((request.GET.get("days") or "30").strip())
    except (TypeError, ValueError):
        value = 30
    return value if value in REPORT_WINDOWS else 30


def _promotion_stats(*, tenant, promotion_ids, days: int):
    since = timezone.now() - timedelta(days=days)
    rows = (
        Order.objects.filter(
            tenant=tenant,
            applied_promotion_id__in=list(promotion_ids),
            is_paid=True,
            created_at__gte=since,
        )
        .values("applied_promotion_id")
        .annotate(
            uses=Count("id"),
            gross_sales=Sum("subtotal"),
            discount_total=Sum("discount_amount"),
            net_sales=Sum("total"),
            customers=Count("customer_id", distinct=True),
        )
    )
    return {row["applied_promotion_id"]: row for row in rows}


def _recent_price_history(*, tenant, days: int, limit: int = 30):
    since = timezone.now() - timedelta(days=days)
    events = list(
        AuditEvent.objects.filter(
            tenant=tenant,
            action__in=[
                "catalog.unit_price_changed",
                "catalog.outlet_price_override_changed",
                "catalog.variant_bulk_updated",
            ],
            created_at__gte=since,
        )
        .select_related("user")
        .order_by("-created_at")[: max(limit * 3, 60)]
    )
    rows = []
    for event in events:
        payload = event.payload or {}
        before = payload.get("before")
        after = payload.get("after")
        if event.action == "catalog.variant_bulk_updated":
            before = (before or {}).get("unit_price") if isinstance(before, dict) else None
            after = (after or {}).get("unit_price") if isinstance(after, dict) else None
            if before == after:
                continue
        if before is None or after is None or str(before) == str(after):
            continue
        rows.append({
            "created_at": event.created_at,
            "item_name": payload.get("item_name") or payload.get("sku") or "Product",
            "outlet_name": payload.get("outlet_name") or "Base / all applicable outlets",
            "before": before,
            "after": after,
            "user": event.user,
        })
        if len(rows) >= limit:
            break
    return rows


class StaffPromotionListView(StaffTenantRequiredMixin, ListView):
    """Promotions schedule; workspace managers may add or edit in staff."""

    staff_nav_capability = "promotions"
    model = Promotion
    template_name = "staff/promotions_list.html"
    context_object_name = "promotions"
    paginate_by = 30

    def get_queryset(self):
        return (
            Promotion.objects.filter(tenant=self.request.tenant)
            .select_related("menu_item", "product_family", "category")
            .prefetch_related("outlets")
            .order_by("-starts_at", "name")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_manage_promotions"] = membership_can_manage_workspace_settings(
            self.request.tenant_membership
        )
        days = _report_window_days(self.request)
        promotions = list(ctx["promotions"])
        stats = _promotion_stats(
            tenant=self.request.tenant,
            promotion_ids=[promotion.pk for promotion in promotions],
            days=days,
        )
        for promotion in promotions:
            row = stats.get(promotion.pk, {})
            promotion.report_uses = row.get("uses", 0)
            promotion.report_gross_sales = row.get("gross_sales") or Decimal("0.00")
            promotion.report_discount_total = row.get("discount_total") or Decimal("0.00")
            promotion.report_net_sales = row.get("net_sales") or Decimal("0.00")
            promotion.report_customers = row.get("customers", 0)
        ctx["promotions"] = promotions
        ctx["promotion_report_days"] = days
        ctx["price_history_rows"] = _recent_price_history(
            tenant=self.request.tenant,
            days=days,
        )
        return ctx


class StaffPromotionDetailView(StaffTenantRequiredMixin, DetailView):
    staff_nav_capability = "promotions"
    model = Promotion
    template_name = "staff/promotion_detail.html"
    context_object_name = "promotion"
    pk_url_kwarg = "promotion_id"

    def get_queryset(self):
        return (
            Promotion.objects.filter(tenant=self.request.tenant)
            .select_related("menu_item", "product_family", "category")
            .prefetch_related("outlets")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_manage_promotions"] = membership_can_manage_workspace_settings(
            self.request.tenant_membership
        )
        paid_redemptions = Order.objects.filter(
            tenant=self.request.tenant,
            applied_promotion=self.object,
            is_paid=True,
        )
        ctx["paid_redemption_count"] = paid_redemptions.count()
        ctx["identified_customer_redemption_count"] = paid_redemptions.exclude(
            customer_id__isnull=True
        ).count()
        days = _report_window_days(self.request)
        row = _promotion_stats(
            tenant=self.request.tenant,
            promotion_ids=[self.object.pk],
            days=days,
        ).get(self.object.pk, {})
        ctx["promotion_report_days"] = days
        ctx["promotion_report"] = {
            "uses": row.get("uses", 0),
            "gross_sales": row.get("gross_sales") or Decimal("0.00"),
            "discount_total": row.get("discount_total") or Decimal("0.00"),
            "net_sales": row.get("net_sales") or Decimal("0.00"),
            "customers": row.get("customers", 0),
        }
        return ctx


class StaffPromotionCreateView(StaffTenantRequiredMixin, CreateView):
    staff_nav_capability = "promotions"
    model = Promotion
    form_class = StaffPromotionForm
    template_name = "staff/promotion_form.html"
    success_url = reverse_lazy("staff-promotions")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(
                request,
                "Only an owner or tenant admin can create offers.",
            )
            return redirect("staff-promotions")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.tenant = self.request.tenant
        self.object.save()
        form.save_m2m()
        markdown_labels = queue_markdown_labels_for_promotion(
            promotion=self.object,
            user=self.request.user,
        )
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="promotion.created",
            entity_type="promotion",
            entity_id=str(self.object.pk),
            payload={
                "name": self.object.name,
                "target": self.object.target_label,
                "discount_percent": str(self.object.discount_percent) if self.object.discount_percent is not None else None,
                "discount_amount": str(self.object.discount_amount) if self.object.discount_amount is not None else None,
                "starts_at": str(self.object.starts_at),
                "ends_at": str(self.object.ends_at) if self.object.ends_at else None,
                "markdown_labels_queued": markdown_labels,
            },
        )
        messages.success(
            self.request,
            "Offer created." + (
                f" {markdown_labels} markdown label task{'s' if markdown_labels != 1 else ''} queued."
                if markdown_labels else ""
            ),
        )
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "New offer"
        return ctx


class StaffPromotionUpdateView(StaffTenantRequiredMixin, UpdateView):
    staff_nav_capability = "promotions"
    model = Promotion
    form_class = StaffPromotionForm
    template_name = "staff/promotion_form.html"
    pk_url_kwarg = "promotion_id"
    success_url = reverse_lazy("staff-promotions")

    def dispatch(self, request, *args, **kwargs):
        if not membership_can_manage_workspace_settings(request.tenant_membership):
            messages.error(
                request,
                "Only an owner or tenant admin can edit promotions.",
            )
            return redirect("staff-promotions")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Promotion.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        before = {
            "name": self.object.name,
            "target": self.object.target_label,
            "discount_percent": str(self.object.discount_percent) if self.object.discount_percent is not None else None,
            "discount_amount": str(self.object.discount_amount) if self.object.discount_amount is not None else None,
            "starts_at": str(self.object.starts_at),
            "ends_at": str(self.object.ends_at) if self.object.ends_at else None,
            "is_active": self.object.is_active,
        }
        self.object = form.save(commit=False)
        self.object.save()
        form.save_m2m()
        markdown_labels = queue_markdown_labels_for_promotion(
            promotion=self.object,
            user=self.request.user,
        )
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="promotion.updated",
            entity_type="promotion",
            entity_id=str(self.object.pk),
            payload={
                "before": before,
                "after": {
                    "name": self.object.name,
                    "target": self.object.target_label,
                    "discount_percent": str(self.object.discount_percent) if self.object.discount_percent is not None else None,
                    "discount_amount": str(self.object.discount_amount) if self.object.discount_amount is not None else None,
                    "starts_at": str(self.object.starts_at),
                    "ends_at": str(self.object.ends_at) if self.object.ends_at else None,
                    "is_active": self.object.is_active,
                },
                "markdown_labels_queued": markdown_labels,
            },
        )
        messages.success(
            self.request,
            "Offer updated." + (
                f" {markdown_labels} markdown label task{'s' if markdown_labels != 1 else ''} queued."
                if markdown_labels else ""
            ),
        )
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit offer"
        return ctx
