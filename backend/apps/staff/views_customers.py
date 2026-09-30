import uuid

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView
from rest_framework.exceptions import ValidationError

from apps.accounts.models import MembershipRole
from apps.audit.services import log_audit
from apps.customers.models import Customer
from apps.customers.services import merge_customers
from apps.events.models import EventBooking
from apps.lodging.models import Folio, Reservation
from apps.pos.models import Order

from .forms.customers import StaffCustomerForm
from .mixins import StaffTenantRequiredMixin
from .services.customers import can_manage_customers, visible_customers
from .services.membership import sites_visible_for_membership, staff_accessible_outlets


class CustomerAccessMixin(StaffTenantRequiredMixin):
    staff_nav_capability = ("orders", "lodging", "events")

    def dispatch(self, request, *args, **kwargs):
        if getattr(request, "tenant_membership", None) and not can_manage_customers(request.tenant_membership):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def customers(self):
        return visible_customers(self.request.tenant_membership, self.request.user)

    def customer(self, customer_id):
        return self.customers().filter(pk=customer_id).first()


class StaffCustomerListView(CustomerAccessMixin, TemplateView):
    template_name = "staff/customers/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = self.request.GET.get("q", "").strip()[:100]
        qs = self.customers()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
        ctx.update(customers=qs.order_by("name", "id")[:50], search=q)
        return ctx


class StaffCustomerCreateView(CustomerAccessMixin, TemplateView):
    template_name = "staff/customers/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = kwargs.get("form") or StaffCustomerForm()
        return ctx

    def post(self, request, *args, **kwargs):
        form = StaffCustomerForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form), status=400)
        customer = form.save(commit=False)
        customer.tenant, customer.created_by = request.tenant, request.user
        customer.save()
        log_audit(tenant_id=request.tenant.pk, user_id=request.user.pk, action="customer.created",
            entity_type="customer", entity_id=str(customer.pk), payload={"name": customer.name})
        messages.success(request, "Customer created. Link an existing stay, booking or order only after confirming identity.")
        return redirect("staff-customer-detail", customer_id=customer.pk)


class StaffCustomerDetailView(CustomerAccessMixin, TemplateView):
    template_name = "staff/customers/detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = self.customer(kwargs["customer_id"])
        if customer is None:
            raise Http404
        membership = self.request.tenant_membership
        site_ids = [site.pk for site in sites_visible_for_membership(membership)]
        outlet_ids = [outlet.pk for outlet in staff_accessible_outlets(membership)]
        ctx["customer"] = customer
        ctx["form"] = kwargs.get("form") or StaffCustomerForm(instance=customer)
        ctx["reservations"] = Reservation.objects.filter(tenant=self.request.tenant, customer=customer, site_id__in=site_ids).order_by("-check_in")[:20]
        ctx["folios"] = Folio.objects.filter(tenant=self.request.tenant, customer=customer, site_id__in=site_ids).order_by("-created_at")[:20]
        ctx["bookings"] = EventBooking.objects.filter(tenant=self.request.tenant, customer=customer, space__site_id__in=site_ids).order_by("-start_at")[:20]
        ctx["orders"] = Order.objects.filter(tenant=self.request.tenant, customer=customer, outlet_id__in=outlet_ids).order_by("-created_at")[:20]
        ctx["can_merge"] = membership.role in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}
        if ctx["can_merge"]:
            matches = Q(name__iexact=customer.name)
            if customer.email:
                matches |= Q(email__iexact=customer.email)
            if customer.phone:
                matches |= Q(phone=customer.phone)
            ctx["merge_candidates"] = Customer.objects.filter(tenant=self.request.tenant, merged_into__isnull=True).exclude(pk=customer.pk).filter(matches).order_by("name")[:30]
        return ctx

    def post(self, request, *args, **kwargs):
        customer = self.customer(kwargs["customer_id"])
        if customer is None:
            raise Http404
        if request.POST.get("action") == "merge":
            if request.tenant_membership.role not in {MembershipRole.OWNER, MembershipRole.TENANT_ADMIN}:
                raise Http404
            try:
                target_id = uuid.UUID(request.POST.get("target_id", ""))
            except (ValueError, TypeError):
                messages.error(request, "Select a valid target customer.")
                return redirect("staff-customer-detail", customer_id=customer.pk)
            target = self.customer(target_id)
            if target is None:
                raise Http404
            try:
                merged, _ = merge_customers(source=customer, target=target, tenant_id=request.tenant.pk,
                    user=request.user, reason=request.POST.get("reason", ""))
            except ValidationError as exc:
                messages.error(request, str(exc.detail))
                return redirect("staff-customer-detail", customer_id=customer.pk)
            messages.success(request, "Customer records merged. Historical transaction names were preserved.")
            return redirect("staff-customer-detail", customer_id=merged.pk)
        form = StaffCustomerForm(request.POST, instance=customer)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form, **kwargs), status=400)
        changes = list(form.changed_data)
        form.save()
        if changes:
            log_audit(tenant_id=request.tenant.pk, user_id=request.user.pk, action="customer.updated",
                entity_type="customer", entity_id=str(customer.pk), payload={"fields": changes})
        messages.success(request, "Customer details saved.")
        return redirect("staff-customer-detail", customer_id=customer.pk)
