from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.audit.services import log_audit
from apps.pos.models import (
    PosShiftStatus,
    Workstation,
    WorkstationDevice,
    WorkstationDeviceAdapter,
    WorkstationDeviceType,
)
from apps.pos.services.device_adapters import (
    ALLOWED_ADAPTERS,
    device_status_summary,
    validate_device_adapter,
)
from apps.tenants.models import Outlet

from .mixins import StaffTenantRequiredMixin
from .services import membership_can_manage_workspace_settings, staff_accessible_outlets
from .workstations import (forget_workstation, select_workstation, selected_workstation, active_pairing, approve_browser, revoke_pairing, set_pairing_cookie)


class WorkstationForm(forms.ModelForm):
    class Meta:
        model = Workstation
        fields = ["name", "code", "outlet", "is_active", "requires_pairing", "receipt_printer", "kitchen_printer", "cash_drawer", "kds_station"]

    def __init__(self, *args, tenant, outlets, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.tenant = tenant
        self._original_outlet_id = self.instance.outlet_id
        self._original_pairing_required = self.instance.requires_pairing
        if self.instance._state.adding:
            self.initial.setdefault("requires_pairing", True)
        self.fields["outlet"].queryset = Outlet.objects.filter(pk__in=[o.pk for o in outlets], site__tenant=tenant)
        self.fields["code"].help_text = "Unique device code, for example bar-till-01."
        from .services.modules import get_tenant_staff_modules
        if "kitchen" not in get_tenant_staff_modules(tenant):
            # A retail-only customer should never see irrelevant kitchen setup.
            self.fields.pop("kitchen_printer", None)
            self.fields.pop("kds_station", None)
        for name, field in self.fields.items():
            if name not in {"is_active", "requires_pairing"}:
                field.widget.attrs["class"] = "staff-input"
        for name in ("receipt_printer", "kitchen_printer", "cash_drawer", "kds_station"):
            if name in self.fields:
                self.fields[name].help_text = "Configuration label for this device."

    def clean_code(self):
        code = self.cleaned_data["code"].lower()
        if Workstation.objects.filter(tenant=self.instance.tenant, code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This device code is already used in your workspace.")
        return code

    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.shifts.filter(status=PosShiftStatus.OPEN).exists():
            if (data.get("outlet") != self.instance.outlet or not data.get("is_active")
                    or data.get("requires_pairing") != self._original_pairing_required):
                raise forms.ValidationError("Close the open shift before moving, disabling or changing browser approval policy.")
        return data


class WorkstationDeviceForm(forms.ModelForm):
    class Meta:
        model = WorkstationDevice
        fields = ["device_type", "adapter", "label", "is_active"]
        widgets = {
            "device_type": forms.Select(attrs={"class": "staff-input"}),
            "adapter": forms.Select(attrs={"class": "staff-input"}),
            "label": forms.TextInput(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant, workstation, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self._workstation = workstation
        self.instance.tenant = tenant
        self.instance.workstation = workstation
        self.fields["label"].help_text = (
            "Human-readable physical label, for example Front Epson TM-T20."
        )
        self.fields["adapter"].help_text = (
            "Browser adapters are supervised fallbacks. Local bridge is reserved "
            "for an installed authenticated device bridge."
        )
        from .services.modules import get_tenant_staff_modules
        if "kitchen" not in get_tenant_staff_modules(
            tenant, outlet=workstation.outlet
        ):
            allowed_types = [
                choice for choice in WorkstationDeviceType.choices
                if choice[0] != WorkstationDeviceType.KITCHEN_PRINTER
            ]
            self.fields["device_type"].choices = allowed_types

    def clean(self):
        data = super().clean()
        device_type = data.get("device_type")
        adapter = data.get("adapter")
        if device_type and adapter:
            try:
                validate_device_adapter(
                    device_type=device_type,
                    adapter=adapter,
                )
            except Exception as exc:
                detail = getattr(exc, "detail", None)
                if isinstance(detail, dict) and "adapter" in detail:
                    raise forms.ValidationError(
                        {"adapter": str(detail["adapter"])}
                    )
                raise
        if (
            device_type == WorkstationDeviceType.KITCHEN_PRINTER
            and "kitchen" not in __import__(
                "apps.staff.services.modules",
                fromlist=["get_tenant_staff_modules"],
            ).get_tenant_staff_modules(
                self._tenant,
                outlet=self._workstation.outlet,
            )
        ):
            raise forms.ValidationError(
                {"device_type": "Kitchen hardware is not enabled for this section."}
            )
        label = " ".join((data.get("label") or "").split())
        if not label:
            raise forms.ValidationError({"label": "Enter a physical device label."})
        data["label"] = label
        duplicate = WorkstationDevice.objects.filter(
            tenant=self._tenant,
            workstation=self._workstation,
            device_type=device_type,
            label__iexact=label,
        )
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError(
                {"label": "This workstation already has that device label."}
            )
        return data


class StaffWorkstationDeviceEditView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"
    template_name = "staff/workstation_device_form.html"

    def dispatch(self, request, *args, **kwargs):
        if (
            getattr(request, "tenant_membership", None)
            and not membership_can_manage_workspace_settings(
                request.tenant_membership
            )
        ):
            return HttpResponseForbidden(
                "Only workspace owners and administrators can configure devices."
            )
        if request.session.get("staff_pin_authenticated"):
            return HttpResponseForbidden(
                "Sign in with your account password to administer workstation devices."
            )
        return super().dispatch(request, *args, **kwargs)

    def _station(self, request, workstation_id):
        outlets = staff_accessible_outlets(request.tenant_membership)
        return get_object_or_404(
            Workstation.objects.select_related("outlet"),
            pk=workstation_id,
            tenant=request.tenant,
            outlet__in=outlets,
        )

    def _device(self, request, station, device_id=None):
        if device_id is None:
            return WorkstationDevice(
                tenant=request.tenant,
                workstation=station,
            )
        return get_object_or_404(
            WorkstationDevice,
            pk=device_id,
            tenant=request.tenant,
            workstation=station,
        )

    def get(self, request, workstation_id, device_id=None):
        station = self._station(request, workstation_id)
        device = self._device(request, station, device_id)
        form = WorkstationDeviceForm(
            instance=device,
            tenant=request.tenant,
            workstation=station,
        )
        return render(
            request,
            self.template_name,
            {
                "station": station,
                "device": device if device.pk else None,
                "form": form,
                "adapter_matrix": {
                    key: sorted(values)
                    for key, values in ALLOWED_ADAPTERS.items()
                },
            },
        )

    @transaction.atomic
    def post(self, request, workstation_id, device_id=None):
        station = self._station(request, workstation_id)
        device = self._device(request, station, device_id)
        form = WorkstationDeviceForm(
            request.POST,
            instance=device,
            tenant=request.tenant,
            workstation=station,
        )
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "station": station,
                    "device": device if device.pk else None,
                    "form": form,
                },
                status=400,
            )
        obj = form.save(commit=False)
        obj.tenant = request.tenant
        obj.workstation = station
        if not obj.pk:
            obj.created_by = request.user
        obj.save()
        log_audit(
            tenant_id=request.tenant.pk,
            user_id=request.user.pk,
            action=(
                "workstation.device_updated"
                if device_id
                else "workstation.device_created"
            ),
            entity_type="workstation_device",
            entity_id=str(obj.pk),
            payload={
                "workstation_id": str(station.pk),
                "device_type": obj.device_type,
                "adapter": obj.adapter,
                "label": obj.label,
                "active": obj.is_active,
            },
            source="staff",
        )
        messages.success(request, "Workstation device saved.")
        return redirect("staff-workstation-test", workstation_id=station.pk)


class StaffWorkstationListView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"

    def get(self, request):
        outlets = staff_accessible_outlets(request.tenant_membership)
        stations = list(
            Workstation.objects.filter(
                tenant=request.tenant,
                outlet__in=outlets,
            )
            .select_related("outlet")
            .prefetch_related("devices")
        )
        for station in stations:
            station.device_statuses = [
                device_status_summary(device)
                for device in station.devices.all()
                if device.is_active
            ]
        return render(request, "staff/workstations.html", {
            "workstations": stations,
            "selected_station": selected_workstation(request, outlets=outlets),
            "can_manage": membership_can_manage_workspace_settings(request.tenant_membership),
            "browser_pairing": active_pairing(request, tenant_id=request.tenant.pk),
        })

    def post(self, request):
        if request.POST.get("action") == "forget":
            pair = active_pairing(request, tenant_id=request.tenant.pk)
            if pair:
                revoke_pairing(pairing=pair, user=request.user, reason="Browser detached by signed-in worker")
            messages.success(request, "This browser has been detached from the workstation.")
            return forget_workstation(redirect("staff-workstations"))
        outlets = staff_accessible_outlets(request.tenant_membership)
        try:
            identifier = forms.UUIDField().clean(request.POST.get("workstation_id"))
        except forms.ValidationError:
            return HttpResponseBadRequest("Choose a valid workstation.")
        station = get_object_or_404(Workstation, pk=identifier, tenant=request.tenant, outlet__in=outlets, is_active=True)
        pair = active_pairing(request, tenant_id=request.tenant.pk)
        if station.requires_pairing and (pair is None or pair.workstation_id != station.pk):
            messages.error(request, "Ask an administrator to approve this browser for the workstation.")
            return redirect("staff-workstations")
        log_audit(tenant_id=request.tenant.id, user_id=request.user.id, action="workstation.selected",
                  entity_type="workstation", entity_id=str(station.pk), payload={})
        messages.success(request, f"This browser now uses {station.name}.")
        return select_workstation(redirect("staff-workstations"), station)


class StaffWorkstationEditView(StaffTenantRequiredMixin, View):
    staff_nav_capability = "orders"
    template_name = "staff/workstation_form.html"
    success_url_name = "staff-workstations"

    def dispatch(self, request, *args, **kwargs):
        if getattr(request, "tenant_membership", None) and not membership_can_manage_workspace_settings(request.tenant_membership):
            return HttpResponseForbidden("Only workspace owners and administrators can configure devices.")
        if request.session.get("staff_pin_authenticated"):
            return HttpResponseForbidden("Sign in with your account password to administer workstation devices.")
        return super().dispatch(request, *args, **kwargs)

    def workstation_outlets(self, request):
        return staff_accessible_outlets(request.tenant_membership)

    def _instance(self, request, workstation_id=None, lock=False):
        qs = Workstation.objects.filter(tenant=request.tenant, outlet__in=self.workstation_outlets(request))
        if lock:
            qs = qs.select_for_update()
        return get_object_or_404(qs, pk=workstation_id) if workstation_id else Workstation(tenant=request.tenant)

    def get(self, request, workstation_id=None):
        form = WorkstationForm(instance=self._instance(request, workstation_id), tenant=request.tenant, outlets=self.workstation_outlets(request))
        return render(request, self.template_name, {"form": form})

    @transaction.atomic
    def post(self, request, workstation_id=None):
        # Same outlet → workstation lock order as shift opening.
        outlets = self.workstation_outlets(request)
        list(Outlet.objects.select_for_update().filter(pk__in=[o.pk for o in outlets]).order_by("pk"))
        form = WorkstationForm(request.POST, instance=self._instance(request, workstation_id, lock=True), tenant=request.tenant, outlets=outlets)
        if form.is_valid():
            try:
                with transaction.atomic():
                    station = form.save()
            except IntegrityError:
                form.add_error("code", "This device code is already used in your workspace.")
                return render(request, self.template_name, {"form": form}, status=400)
            if (not station.is_active or station.outlet_id != form._original_outlet_id):
                for pair in station.pairings.filter(revoked_at__isnull=True):
                    revoke_pairing(pairing=pair, user=request.user, reason="Workstation disabled or moved")
            log_audit(tenant_id=request.tenant.id, user_id=request.user.id, action="workstation.updated" if workstation_id else "workstation.created",
                      entity_type="workstation", entity_id=str(station.pk), payload={"outlet_id": str(station.outlet_id), "active": station.is_active})
            messages.success(request, "Workstation saved.")
            return redirect(self.success_url_name)
        return render(request, self.template_name, {"form": form}, status=400)


class BrowserApprovalForm(forms.Form):
    label = forms.CharField(max_length=80, label="Browser name", widget=forms.TextInput(attrs={"class": "staff-input", "placeholder": "Front counter tablet"}))
    password = forms.CharField(label="Your account password", widget=forms.PasswordInput(attrs={"class": "staff-input", "autocomplete": "current-password"}))


class BrowserRevocationForm(forms.Form):
    pairing_id = forms.UUIDField(widget=forms.HiddenInput())
    reason = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": "staff-input"}))
    password = forms.CharField(label="Your account password", widget=forms.PasswordInput(attrs={"class": "staff-input", "autocomplete": "current-password"}))


class StaffWorkstationPairView(StaffWorkstationEditView):
    pair_template_name = "staff/workstation_pair.html"
    shell_template_name = "staff/base.html"
    pair_success_url_name = "staff-workstations"
    pair_self_url_name = "staff-workstation-pair"
    edit_url_name = "staff-workstation-edit"

    def _render(self, request, station, form=None, revoke_form=None, status=200):
        return render(request, self.pair_template_name, {
            "station": station, "form": form or BrowserApprovalForm(),
            "revoke_form": revoke_form or BrowserRevocationForm(),
            "pairings": station.pairings.select_related("approved_by", "revoked_by"),
            "workstation_shell_template": self.shell_template_name,
            "workstation_list_url_name": self.pair_success_url_name,
            "workstation_edit_url_name": self.edit_url_name,
        }, status=status)

    def get(self, request, workstation_id):
        return self._render(request, self._instance(request, workstation_id))

    def post(self, request, workstation_id):
        station = self._instance(request, workstation_id)
        revoking = request.POST.get("action") == "revoke"
        form = BrowserRevocationForm(request.POST) if revoking else BrowserApprovalForm(request.POST)
        if form.is_valid() and not request.user.check_password(form.cleaned_data["password"]):
            form.add_error("password", "Confirm your account password to approve this action.")
        if not form.is_valid():
            return self._render(request, station, revoke_form=form if revoking else None, form=None if revoking else form, status=400)
        if revoking:
            pair = get_object_or_404(station.pairings, pk=form.cleaned_data["pairing_id"], tenant=request.tenant)
            revoke_pairing(pairing=pair, user=request.user, reason=form.cleaned_data["reason"])
            messages.success(request, "Browser approval revoked. Its PIN session locks on the next request.")
            return redirect(self.pair_self_url_name, workstation_id=station.pk)
        from rest_framework.exceptions import ValidationError
        try:
            old_pair = active_pairing(request, tenant_id=request.tenant.pk)
            pair, secret = approve_browser(station=station, user=request.user, label=form.cleaned_data["label"])
            if old_pair:
                revoke_pairing(pairing=old_pair, user=request.user, reason="This browser was paired again")
        except ValidationError as exc:
            form.add_error(None, str(exc.detail))
            return self._render(request, station, form=form, status=400)
        messages.success(request, "This browser is approved. Workers can now sign in individually and use this register.")
        return set_pairing_cookie(redirect(self.pair_success_url_name), pair, secret)


class StaffWorkstationDeviceTestView(StaffTenantRequiredMixin, View):
    """Browser-assisted device check with manually recorded observations only."""

    staff_nav_capability = "orders"
    http_method_names = ["get", "post", "head", "options"]
    template_name = "staff/workstation_test.html"
    shell_template_name = "staff/base.html"
    list_url_name = "staff-workstations"
    edit_url_name = "staff-workstation-edit"
    success_url_name = "staff-workstation-test"

    def workstation_outlets(self, request):
        return staff_accessible_outlets(request.tenant_membership)

    def can_manage_device_config(self, request):
        membership = getattr(request, "tenant_membership", None)
        return bool(
            membership
            and membership_can_manage_workspace_settings(membership)
        )

    def can_record_hardware_check(self, request):
        return bool(
            getattr(request, "tenant_membership", None)
            and self.can_manage_device_config(request)
            and not request.session.get("staff_pin_authenticated")
        )

    def _station(self, request, workstation_id):
        outlets = self.workstation_outlets(request)
        station = get_object_or_404(
            Workstation.objects.select_related("outlet"),
            tenant=request.tenant, outlet__in=outlets, pk=workstation_id,
        )
        return station, outlets

    def get(self, request, workstation_id):
        from apps.pos.models import WorkstationHardwareCheck
        from apps.pos.services.hardware import browser_device_capabilities
        from .services.modules import get_tenant_staff_modules

        station, outlets = self._station(request, workstation_id)
        selected = selected_workstation(request, outlets=outlets)
        allowed_manager = self.can_manage_device_config(request)
        can_record = self.can_record_hardware_check(request)
        history = WorkstationHardwareCheck.objects.filter(
            tenant=request.tenant, workstation=station,
        ).select_related("checked_by").order_by("-created_at")[:15]
        response = render(request, self.template_name, {
            "station": station,
            "selected_station": selected,
            "is_current_station": bool(selected and selected.pk == station.pk),
            "can_manage": allowed_manager,
            "can_record_check": can_record,
            "hardware_check_membership_required": bool(
                allowed_manager and getattr(request, "tenant_membership", None) is None
            ),
            "has_kitchen": "kitchen" in get_tenant_staff_modules(
                request.tenant, outlet=station.outlet,
            ),
            "device_capabilities": browser_device_capabilities(station),
            "registered_devices": [
                device_status_summary(device)
                for device in station.devices.all().order_by(
                    "device_type", "label"
                )
            ],
            "check_history": history,
            "workstation_shell_template": self.shell_template_name,
            "workstation_list_url_name": self.list_url_name,
            "workstation_edit_url_name": self.edit_url_name,
        })
        response["Cache-Control"] = "private, no-store"
        return response

    def post(self, request, workstation_id):
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from apps.pos.services.hardware import record_hardware_check
        station, _outlets = self._station(request, workstation_id)
        if not self.can_record_hardware_check(request):
            return HttpResponseForbidden(
                "Sign in as a workspace administrator with your account password to record checks."
            )
        if request.POST.get("action") != "record_hardware_check":
            return HttpResponseBadRequest("Choose a device check action.")
        try:
            record_hardware_check(
                tenant=request.tenant, workstation_id=station.pk,
                membership=request.tenant_membership, user=request.user,
                test_type=(request.POST.get("test_type") or "").strip(),
                result=(request.POST.get("result") or "").strip(),
                note=request.POST.get("note", ""),
            )
        except DRFValidationError as exc:
            messages.error(request, str(exc.detail))
        else:
            messages.success(
                request,
                "Your observed check was recorded. Physical certification is still separate.",
            )
        return redirect(self.success_url_name, workstation_id=station.pk)
