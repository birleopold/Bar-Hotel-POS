from __future__ import annotations

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.tenants.models import (
    BillingEvent,
    BillingEventType,
    BillingInvoice,
    BillingInvoiceStatus,
    Plan,
    SubscriptionStatus,
    Tenant,
    TenantFeatureEntitlement,
    TenantOutletModulePolicy,
    TenantSetupProgress,
    TenantSettings,
    TenantSubscription,
    Outlet,
    OutletType,
    Site,
    staff_module_choices,
)

from .forms import (
    ConsoleBillingInvoiceForm,
    ConsoleBillingNoteForm,
    ConsoleBillingStatusTransitionForm,
    ConsolePlanForm,
    ConsoleOutletModulePolicyForm,
    ConsoleTenantEntitlementsForm,
    ConsoleTenantForm,
    ConsoleTenantSubscriptionForm,
    suggest_tenant_slug,
)
from .mixins import PlatformOperatorRequiredMixin
from .setup_flow import build_tenant_setup_state, sync_tenant_setup_progress


class PlatformTenantListView(PlatformOperatorRequiredMixin, ListView):
    template_name = "console/platform/tenant_list.html"
    context_object_name = "tenants"
    paginate_by = 30

    def get_queryset(self):
        return (
            Tenant.objects.annotate(
                site_count=Count("sites", distinct=True),
                member_count=Count("memberships", distinct=True),
            )
            .select_related("subscription", "subscription__plan")
            .order_by("name")
        )


class PlatformTenantCreateView(PlatformOperatorRequiredMixin, CreateView):
    model = Tenant
    form_class = ConsoleTenantForm
    template_name = "console/platform/tenant_form.html"
    success_url = reverse_lazy("console-platform-tenants")

    def get_initial(self):
        initial = super().get_initial()
        name = self.request.GET.get("name", "").strip()
        if name:
            initial["name"] = name
            initial["slug"] = suggest_tenant_slug(name)
        return initial

    def form_valid(self, form):
        messages.success(self.request, f"Workspace “{form.instance.name}” created.")
        response = super().form_valid(form)
        TenantSettings.objects.get_or_create(tenant=self.object)
        return response


class PlatformTenantUpdateView(PlatformOperatorRequiredMixin, UpdateView):
    model = Tenant
    form_class = ConsoleTenantForm
    template_name = "console/platform/tenant_form.html"
    success_url = reverse_lazy("console-platform-tenants")
    pk_url_kwarg = "tenant_id"

    def form_valid(self, form):
        messages.success(self.request, f"Workspace “{form.instance.name}” updated.")
        return super().form_valid(form)


class PlatformPlanListView(PlatformOperatorRequiredMixin, ListView):
    template_name = "console/platform/plan_list.html"
    context_object_name = "plans"
    paginate_by = 30

    def get_queryset(self):
        return Plan.objects.annotate(tenant_count=Count("subscriptions", distinct=True)).order_by("name")


class PlatformPlanCreateView(PlatformOperatorRequiredMixin, CreateView):
    model = Plan
    form_class = ConsolePlanForm
    template_name = "console/platform/plan_form.html"
    success_url = reverse_lazy("console-platform-plans")

    def form_valid(self, form):
        messages.success(self.request, f"Plan “{form.instance.name}” created.")
        return super().form_valid(form)


class PlatformPlanUpdateView(PlatformOperatorRequiredMixin, UpdateView):
    model = Plan
    form_class = ConsolePlanForm
    template_name = "console/platform/plan_form.html"
    success_url = reverse_lazy("console-platform-plans")
    pk_url_kwarg = "plan_id"

    def form_valid(self, form):
        messages.success(self.request, f"Plan “{form.instance.name}” updated.")
        return super().form_valid(form)


class PlatformTenantControlPlaneView(PlatformOperatorRequiredMixin, TemplateView):
    template_name = "console/platform/tenant_control_plane.html"

    def dispatch(self, request, *args, **kwargs):
        self.tenant_obj = get_object_or_404(Tenant, pk=kwargs["tenant_id"])
        return super().dispatch(request, *args, **kwargs)

    def _subscription_form(self, data=None):
        sub = getattr(self.tenant_obj, "subscription", None)
        return ConsoleTenantSubscriptionForm(
            data=data,
            instance=sub,
            prefix="sub",
        )

    def _entitlements_form(self, data=None):
        return ConsoleTenantEntitlementsForm(
            data=data,
            tenant=self.tenant_obj,
            prefix="ent",
        )

    def _invoice_form(self, data=None):
        return ConsoleBillingInvoiceForm(
            data=data,
            prefix="inv",
        )

    def _outlet_policy_form(self, data=None):
        form = ConsoleOutletModulePolicyForm(
            data=data,
            tenant=self.tenant_obj,
            prefix="op",
        )
        if data is None:
            selected_type = (self.request.GET.get("outlet_type") or "").strip()
            if selected_type:
                form.fields["outlet_type"].initial = selected_type
            outlet_type_value = (
                selected_type
                or str(form.fields["outlet_type"].initial or "")
                or str(form.fields["outlet_type"].choices[0][0])
            )
            policy = TenantOutletModulePolicy.objects.filter(
                tenant=self.tenant_obj,
                outlet_type=outlet_type_value,
            ).first()
            form.apply_initial_from_policy(policy)
        return form

    def _transition_form(self, data=None):
        sub = getattr(self.tenant_obj, "subscription", None)
        initial = {"target_status": sub.status} if sub else None
        return ConsoleBillingStatusTransitionForm(
            data=data,
            initial=initial,
            prefix="trn",
        )

    def _note_form(self, data=None):
        return ConsoleBillingNoteForm(
            data=data,
            prefix="note",
        )

    def _event(
        self,
        *,
        event_type: str,
        message: str = "",
        subscription: TenantSubscription | None = None,
        invoice: BillingInvoice | None = None,
        prev_sub_status: str = "",
        new_sub_status: str = "",
        prev_invoice_status: str = "",
        new_invoice_status: str = "",
        metadata: dict | None = None,
    ) -> None:
        BillingEvent.objects.create(
            tenant=self.tenant_obj,
            subscription=subscription,
            invoice=invoice,
            actor=self.request.user,
            event_type=event_type,
            message=message,
            previous_subscription_status=prev_sub_status,
            new_subscription_status=new_sub_status,
            previous_invoice_status=prev_invoice_status,
            new_invoice_status=new_invoice_status,
            metadata=metadata or {},
            occurred_at=timezone.now(),
        )

    def _provision_supermarket_tenant(self) -> None:
        allowed_modules = ["pos", "inventory", "purchasing", "promotions", "workspace"]
        # 1) Supermarket baseline plan.
        plan, _ = Plan.objects.get_or_create(
            code="supermarket-core",
            defaults={
                "name": "Supermarket Core",
                "is_active": True,
                "monthly_price": 0,
                "included_modules": allowed_modules,
                "notes": "Baseline supermarket-only workspace plan.",
            },
        )
        if plan.included_modules != allowed_modules:
            plan.included_modules = allowed_modules
            if not plan.is_active:
                plan.is_active = True
            if not plan.notes:
                plan.notes = "Baseline supermarket-only workspace plan."
            plan.save(update_fields=["included_modules", "is_active", "notes", "updated_at"])

        # 2) Subscription assignment.
        sub, _ = TenantSubscription.objects.get_or_create(
            tenant=self.tenant_obj,
            defaults={
                "plan": plan,
                "status": SubscriptionStatus.ACTIVE,
                "started_at": timezone.now(),
            },
        )
        if sub.plan_id != plan.id or sub.status != SubscriptionStatus.ACTIVE:
            sub.plan = plan
            sub.status = SubscriptionStatus.ACTIVE
            if sub.started_at is None:
                sub.started_at = timezone.now()
            sub.save(update_fields=["plan", "status", "started_at", "updated_at"])

        # 3) Module policy and entitlement overrides.
        settings_obj, _ = TenantSettings.objects.get_or_create(tenant=self.tenant_obj)
        if settings_obj.enabled_staff_modules != allowed_modules:
            settings_obj.enabled_staff_modules = allowed_modules
            settings_obj.save(update_fields=["enabled_staff_modules", "updated_at"])
        allowed_set = set(allowed_modules)
        entitlement_map = {
            e.module_key: e
            for e in TenantFeatureEntitlement.objects.filter(tenant=self.tenant_obj)
        }
        for module_key, _ in staff_module_choices():
            desired = module_key in allowed_set
            existing = entitlement_map.get(module_key)
            if existing is None:
                TenantFeatureEntitlement.objects.create(
                    tenant=self.tenant_obj,
                    module_key=module_key,
                    is_enabled=desired,
                )
            elif existing.is_enabled != desired:
                existing.is_enabled = desired
                existing.save(update_fields=["is_enabled", "updated_at"])

        # 4) Default outlet topology (site + supermarket outlet).
        site = Site.objects.filter(tenant=self.tenant_obj, is_active=True).order_by("created_at").first()
        if site is None:
            site = Site.objects.create(tenant=self.tenant_obj, name="Main site", is_active=True)
        has_supermarket_outlet = Outlet.objects.filter(
            site__tenant=self.tenant_obj,
            is_active=True,
            outlet_type__in=[OutletType.SUPERMARKET, OutletType.RETAIL],
        ).exists()
        if not has_supermarket_outlet:
            Outlet.objects.create(
                site=site,
                name="Main supermarket",
                outlet_type=OutletType.SUPERMARKET,
                is_active=True,
            )

        # 4b) Outlet-type policy templates (supports mixed-line tenants).
        policy_templates: dict[str, list[str]] = {
            OutletType.SUPERMARKET: ["pos", "inventory", "purchasing", "promotions", "workspace"],
            OutletType.RETAIL: ["pos", "inventory", "purchasing", "promotions", "workspace"],
            OutletType.RESTAURANT: ["pos", "kitchen", "inventory", "purchasing", "promotions", "workspace"],
            OutletType.BAR: ["pos", "kitchen", "inventory", "purchasing", "promotions", "workspace"],
            OutletType.LODGING_FRONT_DESK: ["lodging", "workspace", "pos"],
            OutletType.EVENT_SPACE: ["events", "workspace", "pos"],
        }
        for policy_outlet_type, modules in policy_templates.items():
            policy, _ = TenantOutletModulePolicy.objects.get_or_create(
                tenant=self.tenant_obj,
                outlet_type=policy_outlet_type,
                defaults={"enabled_modules": modules, "is_active": True},
            )
            if policy.enabled_modules != modules or not policy.is_active:
                policy.enabled_modules = modules
                policy.is_active = True
                policy.save(update_fields=["enabled_modules", "is_active", "updated_at"])

        # 5) Starter checklist seed (hide irrelevant lodging optional step).
        progress, _ = TenantSetupProgress.objects.get_or_create(tenant=self.tenant_obj)
        overrides = dict(progress.step_state_overrides or {})
        overrides["lodging_basics"] = "skipped"
        progress.step_state_overrides = overrides
        progress.suppress_dashboard_prompt = False
        progress.save(update_fields=["step_state_overrides", "suppress_dashboard_prompt", "updated_at"])
        state = build_tenant_setup_state(self.tenant_obj, progress=progress)
        sync_tenant_setup_progress(self.tenant_obj, state)

        self._event(
            event_type=BillingEventType.NOTE,
            message="One-click supermarket provisioning applied (plan, modules, outlet baseline, setup seed).",
            subscription=sub,
            metadata={"provisioning_profile": "supermarket-core"},
        )

    def post(self, request, *args, **kwargs):
        if "provision_supermarket" in request.POST:
            self._provision_supermarket_tenant()
            messages.success(request, "Supermarket workspace baseline provisioned.")
            return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
        if "save_subscription" in request.POST:
            sub_form = self._subscription_form(data=request.POST)
            ent_form = self._entitlements_form()
            inv_form = self._invoice_form()
            outlet_policy_form = self._outlet_policy_form()
            trn_form = self._transition_form()
            note_form = self._note_form()
            prev_status = ""
            existing_sub = getattr(self.tenant_obj, "subscription", None)
            if existing_sub:
                prev_status = existing_sub.status
            if sub_form.is_valid():
                sub = sub_form.save(commit=False)
                sub.tenant = self.tenant_obj
                sub.save()
                if prev_status != sub.status:
                    self._event(
                        event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
                        message="Subscription status updated from control plane.",
                        subscription=sub,
                        prev_sub_status=prev_status,
                        new_sub_status=sub.status,
                    )
                messages.success(request, "Subscription saved.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "save_entitlements" in request.POST:
            sub_form = self._subscription_form()
            ent_form = self._entitlements_form(data=request.POST)
            inv_form = self._invoice_form()
            outlet_policy_form = self._outlet_policy_form()
            trn_form = self._transition_form()
            note_form = self._note_form()
            if ent_form.is_valid():
                existing = {
                    e.module_key: e
                    for e in TenantFeatureEntitlement.objects.filter(tenant=self.tenant_obj)
                }

                for key, _ in staff_module_choices():
                    desired = bool(ent_form.cleaned_data.get(f"module_{key}"))
                    obj = existing.get(key)
                    if obj is None:
                        TenantFeatureEntitlement.objects.create(
                            tenant=self.tenant_obj,
                            module_key=key,
                            is_enabled=desired,
                        )
                    elif obj.is_enabled != desired:
                        obj.is_enabled = desired
                        obj.save(update_fields=["is_enabled", "updated_at"])
                messages.success(request, "Entitlements saved.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "prefill_outlet_policy" in request.POST:
            sub_form = self._subscription_form()
            ent_form = self._entitlements_form()
            inv_form = self._invoice_form()
            trn_form = self._transition_form()
            note_form = self._note_form()
            outlet_policy_form = self._outlet_policy_form()
            preset_key = (request.POST.get("op-policy_preset") or "").strip()
            if not outlet_policy_form.apply_preset(preset_key):
                messages.error(request, "Select a preset to prefill.")
            else:
                messages.success(request, "Preset applied. Review and save outlet policy.")
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "save_outlet_policy" in request.POST:
            sub_form = self._subscription_form()
            ent_form = self._entitlements_form()
            inv_form = self._invoice_form()
            outlet_policy_form = self._outlet_policy_form(data=request.POST)
            trn_form = self._transition_form()
            note_form = self._note_form()
            if outlet_policy_form.is_valid():
                outlet_type = outlet_policy_form.cleaned_data["outlet_type"]
                enabled_modules: list[str] = []
                for key, _ in staff_module_choices():
                    if outlet_policy_form.cleaned_data.get(f"module_{key}"):
                        enabled_modules.append(key)
                policy, _ = TenantOutletModulePolicy.objects.get_or_create(
                    tenant=self.tenant_obj,
                    outlet_type=outlet_type,
                    defaults={
                        "enabled_modules": enabled_modules,
                        "is_active": bool(outlet_policy_form.cleaned_data.get("is_active")),
                    },
                )
                changed = False
                if policy.enabled_modules != enabled_modules:
                    policy.enabled_modules = enabled_modules
                    changed = True
                desired_active = bool(outlet_policy_form.cleaned_data.get("is_active"))
                if policy.is_active != desired_active:
                    policy.is_active = desired_active
                    changed = True
                if changed:
                    policy.save(update_fields=["enabled_modules", "is_active", "updated_at"])
                messages.success(request, "Outlet module policy saved.")
                return redirect(
                    f"{reverse_lazy('console-platform-tenant-control-plane', kwargs={'tenant_id': self.tenant_obj.id})}?outlet_type={outlet_type}"
                )
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "create_invoice" in request.POST:
            sub_form = self._subscription_form()
            ent_form = self._entitlements_form()
            inv_form = self._invoice_form(data=request.POST)
            outlet_policy_form = self._outlet_policy_form()
            trn_form = self._transition_form()
            note_form = self._note_form()
            if inv_form.is_valid():
                subscription = getattr(self.tenant_obj, "subscription", None)
                invoice = inv_form.save(commit=False)
                invoice.tenant = self.tenant_obj
                invoice.subscription = subscription
                invoice.save()
                self._event(
                    event_type=BillingEventType.INVOICE_CREATED,
                    message=f"Invoice {invoice.invoice_number} created.",
                    subscription=subscription,
                    invoice=invoice,
                    new_invoice_status=invoice.status,
                )
                messages.success(request, "Invoice saved.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "invoice_set_status" in request.POST:
            invoice_id = (request.POST.get("invoice_id") or "").strip()
            new_status = (request.POST.get("status") or "").strip()
            invoice = BillingInvoice.objects.filter(id=invoice_id, tenant=self.tenant_obj).first()
            if invoice is None:
                messages.error(request, "Invoice not found.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            if new_status not in {c[0] for c in BillingInvoiceStatus.choices}:
                messages.error(request, "Invalid invoice status.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            prev_status = invoice.status
            invoice.status = new_status
            if new_status == BillingInvoiceStatus.PAID and invoice.paid_at is None:
                invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at", "updated_at"])
            self._event(
                event_type=BillingEventType.INVOICE_STATUS_CHANGED,
                message=f"Invoice {invoice.invoice_number} set to {new_status}.",
                subscription=invoice.subscription,
                invoice=invoice,
                prev_invoice_status=prev_status,
                new_invoice_status=new_status,
            )
            # Concrete ops workflow: moving an invoice to past_due advances subscription to past_due.
            if new_status == BillingInvoiceStatus.PAST_DUE and invoice.subscription is not None:
                sub = invoice.subscription
                if sub.status not in {SubscriptionStatus.PAST_DUE, SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED}:
                    before = sub.status
                    sub.status = SubscriptionStatus.PAST_DUE
                    sub.save(update_fields=["status", "updated_at"])
                    self._event(
                        event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
                        message=f"Subscription moved to past_due from invoice {invoice.invoice_number}.",
                        subscription=sub,
                        invoice=invoice,
                        prev_sub_status=before,
                        new_sub_status=sub.status,
                    )
            messages.success(request, "Invoice status updated.")
            return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
        if "transition_subscription" in request.POST:
            trn_form = self._transition_form(data=request.POST)
            sub_form = self._subscription_form()
            ent_form = self._entitlements_form()
            inv_form = self._invoice_form()
            outlet_policy_form = self._outlet_policy_form()
            note_form = self._note_form()
            subscription = getattr(self.tenant_obj, "subscription", None)
            if subscription is None:
                messages.error(request, "Create a subscription first.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            if trn_form.is_valid():
                target = trn_form.cleaned_data["target_status"]
                reason = (trn_form.cleaned_data.get("reason") or "").strip()
                previous = subscription.status
                subscription.status = target
                if target == SubscriptionStatus.CANCELLED and subscription.cancelled_at is None:
                    subscription.cancelled_at = timezone.now()
                subscription.save(update_fields=["status", "cancelled_at", "updated_at"])
                self._event(
                    event_type=BillingEventType.SUBSCRIPTION_STATUS_CHANGED,
                    message=reason or f"Subscription moved from {previous} to {target}.",
                    subscription=subscription,
                    prev_sub_status=previous,
                    new_sub_status=target,
                )
                messages.success(request, "Subscription transition recorded.")
                return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
            return self.render_to_response(
                self.get_context_data(
                    subscription_form=sub_form,
                    entitlements_form=ent_form,
                    invoice_form=inv_form,
                    outlet_policy_form=outlet_policy_form,
                    transition_form=trn_form,
                    note_form=note_form,
                ),
            )
        if "add_billing_note" in request.POST:
            note_form = self._note_form(data=request.POST)
            if note_form.is_valid():
                self._event(
                    event_type=BillingEventType.NOTE,
                    message=note_form.cleaned_data["message"],
                    subscription=getattr(self.tenant_obj, "subscription", None),
                )
                messages.success(request, "Billing note added.")
            else:
                messages.error(request, "Billing note is required.")
            return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)
        messages.error(request, "Unknown action.")
        return redirect("console-platform-tenant-control-plane", tenant_id=self.tenant_obj.id)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = getattr(self.tenant_obj, "subscription", None)
        ctx["tenant_obj"] = self.tenant_obj
        ctx["subscription"] = sub
        ctx["subscription_form"] = kwargs.get("subscription_form") or self._subscription_form()
        ctx["entitlements_form"] = kwargs.get("entitlements_form") or self._entitlements_form()
        ctx["invoice_form"] = kwargs.get("invoice_form") or self._invoice_form()
        ctx["outlet_policy_form"] = kwargs.get("outlet_policy_form") or self._outlet_policy_form()
        ctx["transition_form"] = kwargs.get("transition_form") or self._transition_form()
        ctx["note_form"] = kwargs.get("note_form") or self._note_form()
        ctx["outlet_policies"] = list(
            TenantOutletModulePolicy.objects.filter(tenant=self.tenant_obj).order_by("outlet_type")
        )
        ctx["invoices"] = list(
            BillingInvoice.objects.filter(tenant=self.tenant_obj)
            .select_related("subscription")
            .order_by("-created_at")[:30]
        )
        ctx["billing_events"] = list(
            BillingEvent.objects.filter(tenant=self.tenant_obj)
            .select_related("actor", "subscription", "invoice")
            .order_by("-occurred_at", "-created_at")[:40]
        )
        ctx["has_past_due_invoice"] = BillingInvoice.objects.filter(
            tenant=self.tenant_obj,
            status=BillingInvoiceStatus.PAST_DUE,
        ).exists()
        return ctx
