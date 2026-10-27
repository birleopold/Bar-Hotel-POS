from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.audit.services import log_audit
from apps.pos.models import CustomerPriceBookAssignment, PriceBook, PriceBookRule
from apps.tenants.business_lines import normalize_business_lines

from .forms import (
    ConsoleCustomerPriceBookAssignmentForm,
    ConsolePriceBookForm,
    ConsolePriceBookRuleForm,
)
from .mixins import ConsoleOrgAdminRequiredMixin


class RetailPricingRequiredMixin(ConsoleOrgAdminRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        try:
            lines = set(normalize_business_lines(request.tenant.settings.business_lines))
        except Exception:
            lines = set()
        if lines and not lines.intersection({"retail", "supermarket"}):
            raise Http404("Retail pricing is available only for Retail or Supermarket workspaces.")
        return super().dispatch(request, *args, **kwargs)


class OrgPriceBookListView(RetailPricingRequiredMixin, ListView):
    template_name = "console/org/price_book_list.html"
    context_object_name = "price_books"

    def get_queryset(self):
        return (
            PriceBook.objects.filter(tenant=self.request.tenant)
            .prefetch_related("outlets")
            .order_by("name")
        )


class OrgPriceBookCreateView(RetailPricingRequiredMixin, CreateView):
    model = PriceBook
    form_class = ConsolePriceBookForm
    template_name = "console/org/price_book_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.tenant = self.request.tenant
            self.object.save()
            form.save_m2m()
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="pricing.price_book_created",
                entity_type="price_book",
                entity_id=str(self.object.pk),
                payload={"name": self.object.name, "code": self.object.code},
            )
        messages.success(self.request, f"Price book “{self.object.name}” created.")
        return redirect("console-org-price-book-detail", price_book_id=self.object.pk)


class OrgPriceBookUpdateView(RetailPricingRequiredMixin, UpdateView):
    model = PriceBook
    form_class = ConsolePriceBookForm
    template_name = "console/org/price_book_form.html"
    pk_url_kwarg = "price_book_id"

    def get_queryset(self):
        return PriceBook.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        return kw

    def form_valid(self, form):
        before = {
            "name": self.object.name,
            "code": self.object.code,
            "starts_at": str(self.object.starts_at) if self.object.starts_at else None,
            "ends_at": str(self.object.ends_at) if self.object.ends_at else None,
            "is_active": self.object.is_active,
        }
        with transaction.atomic():
            self.object = form.save()
            form.save_m2m()
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="pricing.price_book_updated",
                entity_type="price_book",
                entity_id=str(self.object.pk),
                payload={
                    "before": before,
                    "after": {
                        "name": self.object.name,
                        "code": self.object.code,
                        "starts_at": str(self.object.starts_at) if self.object.starts_at else None,
                        "ends_at": str(self.object.ends_at) if self.object.ends_at else None,
                        "is_active": self.object.is_active,
                    },
                },
            )
        messages.success(self.request, f"Price book “{self.object.name}” saved.")
        return redirect("console-org-price-book-detail", price_book_id=self.object.pk)


class OrgPriceBookDetailView(RetailPricingRequiredMixin, DetailView):
    model = PriceBook
    template_name = "console/org/price_book_detail.html"
    context_object_name = "price_book"
    pk_url_kwarg = "price_book_id"

    def get_queryset(self):
        return PriceBook.objects.filter(tenant=self.request.tenant).prefetch_related("outlets")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rules"] = (
            self.object.rules.filter(tenant=self.request.tenant)
            .select_related("menu_item", "product_family", "category")
            .order_by("-minimum_quantity", "pk")
        )
        ctx["assignments"] = (
            self.object.customer_assignments.filter(tenant=self.request.tenant)
            .select_related("customer")
            .order_by("customer__name")
        )
        ctx["assignment_form"] = ConsoleCustomerPriceBookAssignmentForm(
            tenant=self.request.tenant,
            price_book=self.object,
        )
        return ctx


class PriceBookScopedMixin(RetailPricingRequiredMixin):
    price_book: PriceBook

    def dispatch(self, request, *args, **kwargs):
        self.price_book = get_object_or_404(
            PriceBook,
            pk=kwargs["price_book_id"],
            tenant=request.tenant,
        )
        return super().dispatch(request, *args, **kwargs)


class OrgPriceBookRuleCreateView(PriceBookScopedMixin, CreateView):
    model = PriceBookRule
    form_class = ConsolePriceBookRuleForm
    template_name = "console/org/price_book_rule_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["price_book"] = self.price_book
        return kw

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.tenant = self.request.tenant
            self.object.price_book = self.price_book
            self.object.save()
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="pricing.price_book_rule_saved",
                entity_type="price_book_rule",
                entity_id=str(self.object.pk),
                payload={
                    "price_book_id": str(self.price_book.pk),
                    "menu_item_id": str(self.object.menu_item_id) if self.object.menu_item_id else None,
                    "product_family_id": str(self.object.product_family_id) if self.object.product_family_id else None,
                    "category_id": str(self.object.category_id) if self.object.category_id else None,
                    "brand": self.object.brand or "",
                    "target": self.object.target_label,
                    "minimum_quantity": str(self.object.minimum_quantity),
                    "unit_price": str(self.object.unit_price),
                    "is_active": self.object.is_active,
                },
            )
        messages.success(self.request, "Price tier added.")
        return redirect("console-org-price-book-detail", price_book_id=self.price_book.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["price_book"] = self.price_book
        ctx["form_title"] = "Add price tier"
        return ctx


class OrgPriceBookRuleUpdateView(PriceBookScopedMixin, UpdateView):
    model = PriceBookRule
    form_class = ConsolePriceBookRuleForm
    template_name = "console/org/price_book_rule_form.html"
    pk_url_kwarg = "rule_id"

    def get_queryset(self):
        return PriceBookRule.objects.filter(
            tenant=self.request.tenant,
            price_book=self.price_book,
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["tenant"] = self.request.tenant
        kw["price_book"] = self.price_book
        return kw

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.tenant = self.request.tenant
        self.object.price_book = self.price_book
        self.object.save()
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="pricing.price_book_rule_saved",
            entity_type="price_book_rule",
            entity_id=str(self.object.pk),
            payload={
                "price_book_id": str(self.price_book.pk),
                "menu_item_id": str(self.object.menu_item_id) if self.object.menu_item_id else None,
                "product_family_id": str(self.object.product_family_id) if self.object.product_family_id else None,
                "category_id": str(self.object.category_id) if self.object.category_id else None,
                "brand": self.object.brand or "",
                "target": self.object.target_label,
                "minimum_quantity": str(self.object.minimum_quantity),
                "unit_price": str(self.object.unit_price),
                "is_active": self.object.is_active,
            },
        )
        messages.success(self.request, "Price tier saved.")
        return redirect("console-org-price-book-detail", price_book_id=self.price_book.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["price_book"] = self.price_book
        ctx["form_title"] = "Edit price tier"
        return ctx


class OrgPriceBookRuleDeleteView(PriceBookScopedMixin, DeleteView):
    model = PriceBookRule
    template_name = "console/org/price_book_rule_confirm_delete.html"
    pk_url_kwarg = "rule_id"

    def get_queryset(self):
        return PriceBookRule.objects.filter(
            tenant=self.request.tenant,
            price_book=self.price_book,
        )

    def get_success_url(self):
        return reverse("console-org-price-book-detail", kwargs={"price_book_id": self.price_book.pk})

    def form_valid(self, form):
        rule = self.object
        payload = {
            "price_book_id": str(self.price_book.pk),
            "menu_item_id": str(rule.menu_item_id) if rule.menu_item_id else None,
            "product_family_id": str(rule.product_family_id) if rule.product_family_id else None,
            "category_id": str(rule.category_id) if rule.category_id else None,
            "brand": rule.brand or "",
            "target": rule.target_label,
            "minimum_quantity": str(rule.minimum_quantity),
            "unit_price": str(rule.unit_price),
        }
        if rule.order_lines.exists():
            rule.is_active = False
            rule.save(update_fields=["is_active", "updated_at"])
            log_audit(
                tenant_id=self.request.tenant.pk,
                user_id=self.request.user.pk,
                action="pricing.price_book_rule_deactivated",
                entity_type="price_book_rule",
                entity_id=str(rule.pk),
                payload={**payload, "reason": "historical_sale_reference"},
            )
            messages.success(
                self.request,
                "This tier has historical sales, so it was deactivated instead of deleted.",
            )
            return redirect(self.get_success_url())
        log_audit(
            tenant_id=self.request.tenant.pk,
            user_id=self.request.user.pk,
            action="pricing.price_book_rule_deleted",
            entity_type="price_book_rule",
            entity_id=str(rule.pk),
            payload=payload,
        )
        messages.success(self.request, "Price tier removed.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["price_book"] = self.price_book
        return ctx


class OrgPriceBookAssignmentView(PriceBookScopedMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "assign").strip()
        if action == "remove":
            assignment_id = request.POST.get("assignment_id")
            assignment = get_object_or_404(
                CustomerPriceBookAssignment,
                pk=assignment_id,
                tenant=request.tenant,
                price_book=self.price_book,
            )
            customer_name = assignment.customer.name
            assignment_id_value = assignment.pk
            assignment.delete()
            log_audit(
                tenant_id=request.tenant.pk,
                user_id=request.user.pk,
                action="pricing.customer_price_book_removed",
                entity_type="customer_price_book_assignment",
                entity_id=str(assignment_id_value),
                payload={"customer_name": customer_name, "price_book_id": str(self.price_book.pk)},
            )
            messages.success(request, f"Removed {customer_name} from this price book.")
            return redirect("console-org-price-book-detail", price_book_id=self.price_book.pk)

        form = ConsoleCustomerPriceBookAssignmentForm(
            request.POST,
            tenant=request.tenant,
            price_book=self.price_book,
        )
        if not form.is_valid():
            messages.error(request, "Choose a valid customer.")
            return redirect("console-org-price-book-detail", price_book_id=self.price_book.pk)

        customer = form.cleaned_data["customer"]
        previous = CustomerPriceBookAssignment.objects.filter(
            tenant=request.tenant,
            customer=customer,
        ).select_related("price_book").first()
        previous_book = previous.price_book.name if previous else None
        with transaction.atomic():
            assignment, _created = CustomerPriceBookAssignment.objects.update_or_create(
                tenant=request.tenant,
                customer=customer,
                defaults={
                    "price_book": self.price_book,
                    "assigned_by": request.user,
                },
            )
            log_audit(
                tenant_id=request.tenant.pk,
                user_id=request.user.pk,
                action="pricing.customer_price_book_assigned",
                entity_type="customer_price_book_assignment",
                entity_id=str(assignment.pk),
                payload={
                    "customer_id": str(customer.pk),
                    "previous_price_book": previous_book,
                    "price_book_id": str(self.price_book.pk),
                    "price_book": self.price_book.name,
                },
            )
        if previous_book and previous_book != self.price_book.name:
            messages.success(
                request,
                f"{customer.name} moved from {previous_book} to {self.price_book.name}.",
            )
        else:
            messages.success(request, f"{customer.name} assigned to {self.price_book.name}.")
        return redirect("console-org-price-book-detail", price_book_id=self.price_book.pk)
