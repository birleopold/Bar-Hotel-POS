from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.audit.services import log_audit
from apps.pos.models import PosShiftStatus, Workstation
from apps.tenants.models import Outlet

from .mixins import StaffTenantRequiredMixin
from .services import membership_can_manage_workspace_settings, staff_accessible_outlets
from .workstations import forget_workstation, select_workstation, selected_workstation


class WorkstationForm(forms.ModelForm):
    class Meta:
        model = Workstation
        fields = ["name", "code", "outlet", "is_active", "receipt_printer", "kitchen_printer", "cash_drawer", "kds_station"]

    def __init__(self, *args, tenant, outlets, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tenant = tenant
        self.fields["outlet"].queryset = Outlet.objects.filter(pk__in=[o.pk for o in outlets], site__tenant=tenant)
        self.fields["code"].help_text = "Unique device code, for example bar-till-01."
        for name, field in self.fields.items():
            if name != "is_active":
                field.widget.attrs["class"] = "staff-input"
        for name in ("receipt_printer", "kitchen_printer", "cash_drawer", "kds_station"):
            self.fields[name].help_text = "Configuration label for this device."

    def clean_code(self):
        code = self.cleaned_data["code"].lower()
        if Workstation.objects.filter(tenant=self.instance.tenant, code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This device code is already used in your workspace.")
        return code

    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.shifts.filter(status=PosShiftStatus.OPEN).exists():
            if data.get("outlet") != self.instance.outlet or not data.get("is_active"):
                raise forms.ValidationError("Close the open shift before moving or disabling this workstation.")
        return data


class StaffWorkstationListView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"

    def get(self, request):
        outlets = staff_accessible_outlets(request.tenant_membership)
        stations = Workstation.objects.filter(tenant=request.tenant, outlet__in=outlets).select_related("outlet")
        return render(request, "staff/workstations.html", {
            "workstations": stations,
            "selected_station": selected_workstation(request, outlets=outlets),
            "can_manage": membership_can_manage_workspace_settings(request.tenant_membership),
        })

    def post(self, request):
        if request.POST.get("action") == "forget":
            messages.success(request, "Workstation selection cleared for this browser.")
            return forget_workstation(redirect("staff-workstations"))
        outlets = staff_accessible_outlets(request.tenant_membership)
        try:
            identifier = forms.UUIDField().clean(request.POST.get("workstation_id"))
        except forms.ValidationError:
            return HttpResponseBadRequest("Choose a valid workstation.")
        station = get_object_or_404(Workstation, pk=identifier, tenant=request.tenant, outlet__in=outlets, is_active=True)
        log_audit(tenant_id=request.tenant.id, user_id=request.user.id, action="workstation.selected",
                  entity_type="workstation", entity_id=str(station.pk), payload={})
        messages.success(request, f"This browser now uses {station.name}.")
        return select_workstation(redirect("staff-workstations"), station)


class StaffWorkstationEditView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"

    def dispatch(self, request, *args, **kwargs):
        if getattr(request, "tenant_membership", None) and not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden("Only workspace owners and administrators can configure devices.")
        return super().dispatch(request, *args, **kwargs)

    def _instance(self, request, workstation_id=None, lock=False):
        qs = Workstation.objects.filter(tenant=request.tenant, outlet__in=staff_accessible_outlets(request.tenant_membership))
        if lock:
            qs = qs.select_for_update()
        return get_object_or_404(qs, pk=workstation_id) if workstation_id else Workstation(tenant=request.tenant)

    def get(self, request, workstation_id=None):
        form = WorkstationForm(instance=self._instance(request, workstation_id), tenant=request.tenant, outlets=staff_accessible_outlets(request.tenant_membership))
        return render(request, "staff/workstation_form.html", {"form": form})

    @transaction.atomic
    def post(self, request, workstation_id=None):
        # Same outlet → workstation lock order as shift opening.
        outlets = staff_accessible_outlets(request.tenant_membership)
        list(Outlet.objects.select_for_update().filter(pk__in=[o.pk for o in outlets]).order_by("pk"))
        form = WorkstationForm(request.POST, instance=self._instance(request, workstation_id, lock=True), tenant=request.tenant, outlets=outlets)
        if form.is_valid():
            try:
                with transaction.atomic():
                    station = form.save()
            except IntegrityError:
                form.add_error("code", "This device code is already used in your workspace.")
                return render(request, "staff/workstation_form.html", {"form": form}, status=400)
            log_audit(tenant_id=request.tenant.id, user_id=request.user.id, action="workstation.updated" if workstation_id else "workstation.created",
                      entity_type="workstation", entity_id=str(station.pk), payload={"outlet_id": str(station.outlet_id), "active": station.is_active})
            messages.success(request, "Workstation saved.")
            return redirect("staff-workstations")
        return render(request, "staff/workstation_form.html", {"form": form}, status=400)
