from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.audit.services import log_audit
from apps.catalog.models import Promotion
from apps.pos.models import Order

from .forms import StaffPromotionForm
from .mixins import StaffTenantRequiredMixin
from .services import membership_can_manage_workspace_settings


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
            },
        )
        messages.success(self.request, "Offer created.")
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
            },
        )
        messages.success(self.request, "Offer updated.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Edit offer"
        return ctx
