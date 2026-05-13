import json
import re

from django import forms

from apps.accounts.models import Membership, MembershipRole, User
from apps.integrations.models import IntegrationLink
from apps.tenants.models import Outlet, Site, TenantSettings

from ..services import STAFF_MODULE_CHOICES, STAFF_MODULE_KEYS

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

ROLE_PRESET_CHOICES = [
    ("", "Custom"),
    ("cashier", "Cashier"),
    ("restaurant_server", "Restaurant server"),
    ("bar_staff", "Bar staff"),
    ("front_desk", "Front desk"),
    ("storekeeper", "Storekeeper"),
    ("branch_manager", "Branch manager"),
]

ROLE_PRESET_DEFAULTS: dict[str, dict[str, str]] = {
    "cashier": {"role": MembershipRole.SERVER},
    "restaurant_server": {"role": MembershipRole.SERVER},
    "bar_staff": {"role": MembershipRole.BARTENDER},
    "front_desk": {"role": MembershipRole.FRONT_DESK},
    "storekeeper": {"role": MembershipRole.STOREKEEPER},
    "branch_manager": {"role": MembershipRole.SITE_MANAGER},
}


def apply_role_preset(cleaned_data: dict) -> dict:
    preset = str(cleaned_data.get("role_preset") or "").strip()
    defaults = ROLE_PRESET_DEFAULTS.get(preset)
    if defaults:
        cleaned_data["role"] = defaults["role"]
    return cleaned_data


class StaffTenantModulesForm(forms.Form):
    """Which product areas appear in staff (owner / tenant admin only)."""

    modules = forms.MultipleChoiceField(
        label="Enabled staff areas",
        required=True,
        choices=STAFF_MODULE_CHOICES,
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "staff-checklist"},
        ),
    )

    def clean_modules(self) -> list[str]:
        sel = self.cleaned_data.get("modules") or []
        if not sel:
            raise forms.ValidationError("Select at least one area.")
        bad = set(sel) - STAFF_MODULE_KEYS
        if bad:
            raise forms.ValidationError("Invalid module selection.")
        return list(sel)


class StaffTenantBrandingForm(forms.ModelForm):
    class Meta:
        model = TenantSettings
        fields = [
            "default_currency",
            "default_timezone",
            "receipt_footer",
            "theme_primary",
            "theme_secondary",
            "theme_accent",
            "logo_url",
            "hardware_barcode_scanner_enabled",
            "hardware_cash_drawer_enabled",
            "hardware_receipt_printer_enabled",
            "efris_enabled",
        ]
        widgets = {
            "default_currency": forms.TextInput(attrs={"class": "staff-input", "maxlength": 3}),
            "default_timezone": forms.TextInput(attrs={"class": "staff-input"}),
            "receipt_footer": forms.Textarea(attrs={"class": "staff-input", "rows": 3}),
            "theme_primary": forms.TextInput(attrs={"class": "staff-input", "type": "color"}),
            "theme_secondary": forms.TextInput(attrs={"class": "staff-input", "type": "color"}),
            "theme_accent": forms.TextInput(attrs={"class": "staff-input", "type": "color"}),
            "logo_url": forms.URLInput(attrs={"class": "staff-input"}),
            "hardware_barcode_scanner_enabled": forms.CheckboxInput(),
            "hardware_cash_drawer_enabled": forms.CheckboxInput(),
            "hardware_receipt_printer_enabled": forms.CheckboxInput(),
            "efris_enabled": forms.CheckboxInput(),
        }

    def clean_theme_primary(self):
        return self._hex(self.cleaned_data.get("theme_primary", ""))

    def clean_theme_secondary(self):
        return self._hex(self.cleaned_data.get("theme_secondary", ""))

    def clean_theme_accent(self):
        return self._hex(self.cleaned_data.get("theme_accent", ""))

    def _hex(self, value: str) -> str:
        if value and not _HEX_COLOR.match(value):
            raise forms.ValidationError("Use #RRGGBB hex format.")
        return value


class StaffIntegrationLinkForm(forms.ModelForm):
    settings_json = forms.CharField(
        required=False,
        label="Settings (JSON)",
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 6, "spellcheck": "false"}),
    )

    class Meta:
        model = IntegrationLink
        fields = ["provider_key", "label", "is_enabled"]
        widgets = {
            "provider_key": forms.TextInput(attrs={"class": "staff-input", "autocomplete": "off"}),
            "label": forms.TextInput(attrs={"class": "staff-input"}),
            "is_enabled": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant=None, updating: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        self._updating = updating
        if updating:
            self.fields["provider_key"].disabled = True
            self.fields["provider_key"].required = False
        if self.instance.pk:
            self.fields["settings_json"].initial = json.dumps(
                self.instance.settings or {},
                indent=2,
                sort_keys=True,
            )
        elif "settings_json" not in self.initial:
            self.fields["settings_json"].initial = "{}"

    def clean_provider_key(self):
        if self._updating:
            return self.instance.provider_key
        key = (self.cleaned_data.get("provider_key") or "").strip()
        if not key:
            raise forms.ValidationError("Provider key is required.")
        if len(key) > 64:
            raise forms.ValidationError("Max 64 characters.")
        if self._tenant and IntegrationLink.objects.filter(
            tenant=self._tenant,
            provider_key=key,
        ).exists():
            raise forms.ValidationError("This provider key already exists for your workspace.")
        return key

    def clean(self):
        data = super().clean()
        raw = data.get("settings_json")
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            data["parsed_settings"] = {}
            return data
        if not isinstance(raw, str):
            data["parsed_settings"] = raw if isinstance(raw, dict) else {}
            return data
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError({"settings_json": f"Invalid JSON: {e}"}) from e
        if not isinstance(parsed, dict):
            raise forms.ValidationError({"settings_json": "Settings must be a JSON object {}."})
        data["parsed_settings"] = parsed
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.settings = self.cleaned_data.get("parsed_settings") or {}
        if commit:
            obj.save()
        return obj


class StaffEfrisSettingsForm(forms.Form):
    SECRET_MASK_TOKEN = "****"
    SECRET_FIELDS = {
        "access_token",
        "client_secret",
        "api_key",
        "api_secret",
        "signing_key",
        "encryption_key",
    }

    tenant_efris_enabled = forms.BooleanField(required=False, label="Enable EFRIS for this workspace")
    link_is_enabled = forms.BooleanField(required=False, label="Enable URA EFRIS integration link")
    submit_endpoint = forms.URLField(
        required=False,
        label="Submit endpoint",
        widget=forms.URLInput(attrs={"class": "staff-input", "placeholder": "https://..."}),
    )
    auth_endpoint = forms.URLField(
        required=False,
        label="Auth endpoint (optional)",
        widget=forms.URLInput(attrs={"class": "staff-input", "placeholder": "https://..."}),
    )
    tin = forms.CharField(
        required=False,
        max_length=64,
        label="TIN",
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    branch_id = forms.CharField(
        required=False,
        max_length=64,
        label="Branch ID",
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    device_no = forms.CharField(
        required=False,
        max_length=64,
        label="Device number",
        widget=forms.TextInput(attrs={"class": "staff-input"}),
    )
    access_token = forms.CharField(
        required=False,
        max_length=512,
        label="Access token (optional if auth endpoint is used)",
        widget=forms.PasswordInput(render_value=True, attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    client_id = forms.CharField(
        required=False,
        max_length=256,
        label="Client ID",
        widget=forms.TextInput(attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    client_secret = forms.CharField(
        required=False,
        max_length=512,
        label="Client secret",
        widget=forms.PasswordInput(render_value=True, attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    api_key = forms.CharField(
        required=False,
        max_length=256,
        label="API key",
        widget=forms.TextInput(attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    api_secret = forms.CharField(
        required=False,
        max_length=512,
        label="API secret",
        widget=forms.PasswordInput(render_value=True, attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    signing_key = forms.CharField(
        required=False,
        max_length=512,
        label="Signing key (fallback)",
        widget=forms.PasswordInput(render_value=True, attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    encryption_key = forms.CharField(
        required=False,
        max_length=512,
        label="Encryption key (reserved)",
        widget=forms.PasswordInput(render_value=True, attrs={"class": "staff-input", "autocomplete": "off"}),
    )
    signing_mode = forms.ChoiceField(
        required=False,
        initial="hmac_sha256",
        choices=[
            ("hmac_sha256", "HMAC-SHA256"),
            ("sha256", "SHA256"),
            ("none", "None"),
        ],
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    encryption_mode = forms.ChoiceField(
        required=False,
        initial="none",
        choices=[("none", "None"), ("base64", "Base64 hook")],
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    request_timeout_seconds = forms.IntegerField(
        required=False,
        initial=30,
        min_value=1,
        max_value=120,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": 1, "max": 120}),
    )
    extra_headers_json = forms.CharField(
        required=False,
        label="Extra headers (JSON object)",
        widget=forms.Textarea(attrs={"class": "staff-input", "rows": 4, "spellcheck": "false"}),
        initial="{}",
    )

    def clean_extra_headers_json(self):
        raw = self.cleaned_data.get("extra_headers_json")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return {}
        if not isinstance(raw, str):
            return raw if isinstance(raw, dict) else {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise forms.ValidationError("Extra headers must be a JSON object.")
        return {str(k): str(v) for k, v in parsed.items()}

    def clean(self):
        data = super().clean()
        for key in self.SECRET_FIELDS:
            if data.get(key) == self.SECRET_MASK_TOKEN:
                data[key] = str(self._existing_settings.get(key) or "")
        if not data.get("link_is_enabled"):
            return data
        if not data.get("submit_endpoint"):
            self.add_error("submit_endpoint", "Submit endpoint is required when link is enabled.")
        if not data.get("tin"):
            self.add_error("tin", "TIN is required when link is enabled.")
        if data.get("auth_endpoint") and not data.get("access_token"):
            if not data.get("client_id") or not data.get("client_secret"):
                self.add_error(
                    "client_id",
                    "Provide access token or client credentials when auth endpoint is set.",
                )
        return data

    @classmethod
    def build_initial(cls, *, tenant_settings: TenantSettings, link: IntegrationLink | None) -> dict:
        settings = (link.settings or {}) if link else {}
        return {
            "tenant_efris_enabled": bool(tenant_settings.efris_enabled),
            "link_is_enabled": bool(link.is_enabled) if link else False,
            "submit_endpoint": settings.get("submit_endpoint", ""),
            "auth_endpoint": settings.get("auth_endpoint", ""),
            "tin": settings.get("tin", ""),
            "branch_id": settings.get("branch_id", ""),
            "device_no": settings.get("device_no", ""),
            "access_token": cls.SECRET_MASK_TOKEN if settings.get("access_token") else "",
            "client_id": settings.get("client_id", ""),
            "client_secret": cls.SECRET_MASK_TOKEN if settings.get("client_secret") else "",
            "api_key": cls.SECRET_MASK_TOKEN if settings.get("api_key") else "",
            "api_secret": cls.SECRET_MASK_TOKEN if settings.get("api_secret") else "",
            "signing_key": cls.SECRET_MASK_TOKEN if settings.get("signing_key") else "",
            "encryption_key": cls.SECRET_MASK_TOKEN if settings.get("encryption_key") else "",
            "signing_mode": settings.get("signing_mode", "hmac_sha256"),
            "encryption_mode": settings.get("encryption_mode", "none"),
            "request_timeout_seconds": settings.get("request_timeout_seconds", 30),
            "extra_headers_json": json.dumps(settings.get("extra_headers") or {}, indent=2, sort_keys=True),
        }

    def __init__(self, *args, existing_settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._existing_settings = dict(existing_settings or {})
        keep_msg = f'Use "{self.SECRET_MASK_TOKEN}" to keep the existing secret.'
        for key in self.SECRET_FIELDS:
            self.fields[key].help_text = keep_msg

    def to_integration_settings(self) -> dict:
        keys = [
            "submit_endpoint",
            "auth_endpoint",
            "tin",
            "branch_id",
            "device_no",
            "access_token",
            "client_id",
            "client_secret",
            "api_key",
            "api_secret",
            "signing_key",
            "encryption_key",
            "signing_mode",
            "encryption_mode",
            "request_timeout_seconds",
        ]
        payload = {}
        for key in keys:
            value = self.cleaned_data.get(key)
            if value in ("", None):
                continue
            payload[key] = value
        extra_headers = self.cleaned_data.get("extra_headers_json") or {}
        if extra_headers:
            payload["extra_headers"] = extra_headers
        return payload


class StaffTeamInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "staff-input", "autocomplete": "email"}),
    )
    role_preset = forms.ChoiceField(
        required=False,
        choices=ROLE_PRESET_CHOICES,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    role = forms.ChoiceField(
        choices=[(c.value, c.label) for c in MembershipRole],
        initial=MembershipRole.SERVER,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    expires_days = forms.IntegerField(
        min_value=1,
        max_value=30,
        initial=7,
        widget=forms.NumberInput(attrs={"class": "staff-input", "min": 1, "max": 30}),
    )

    def clean(self):
        return apply_role_preset(super().clean())


class StaffWorkerCreateForm(forms.Form):
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "staff-input"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "staff-input", "autocomplete": "email"}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "staff-input", "autocomplete": "tel"}))
    role_preset = forms.ChoiceField(
        required=False,
        choices=ROLE_PRESET_CHOICES,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    role = forms.ChoiceField(
        choices=[(c.value, c.label) for c in MembershipRole],
        initial=MembershipRole.SERVER,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    sites = forms.ModelMultipleChoiceField(
        queryset=Site.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    outlets = forms.ModelMultipleChoiceField(
        queryset=Outlet.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    send_reset_link = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        if tenant is not None:
            self.fields["sites"].queryset = Site.objects.filter(tenant=tenant).order_by("name")
            self.fields["outlets"].queryset = Outlet.objects.filter(site__tenant=tenant).select_related("site").order_by(
                "site__name", "name"
            )
        self.fields["sites"].help_text = "Leave empty for all branches."
        self.fields["outlets"].help_text = "Leave empty for all outlets allowed by the selected branches."

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        return email

    def clean(self):
        data = apply_role_preset(super().clean())
        email = data.get("email")
        if self._tenant is not None and email and Membership.objects.filter(tenant=self._tenant, user__email__iexact=email).exists():
            raise forms.ValidationError({"email": "This user already belongs to the workspace."})
        selected_sites = data.get("sites")
        selected_outlets = data.get("outlets")
        if selected_sites and selected_outlets:
            site_ids = set(selected_sites.values_list("id", flat=True))
            if any(o.site_id not in site_ids for o in selected_outlets):
                raise forms.ValidationError({"outlets": "Selected outlets must belong to the selected sites."})
        return data


class StaffMembershipBulkActionForm(forms.Form):
    member_ids = forms.ModelMultipleChoiceField(queryset=Membership.objects.none(), required=True)
    action = forms.ChoiceField(
        choices=[
            ("activate", "Activate selected"),
            ("deactivate", "Deactivate selected"),
            ("apply_preset", "Apply role preset"),
        ],
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    role_preset = forms.ChoiceField(
        required=False,
        choices=ROLE_PRESET_CHOICES,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["member_ids"].queryset = Membership.objects.filter(tenant=tenant)

    def clean(self):
        data = super().clean()
        if data.get("action") == "apply_preset" and not data.get("role_preset"):
            raise forms.ValidationError({"role_preset": "Choose a role preset for this bulk action."})
        return data


class StaffMembershipManageForm(forms.ModelForm):
    role_preset = forms.ChoiceField(
        required=False,
        choices=ROLE_PRESET_CHOICES,
        widget=forms.Select(attrs={"class": "staff-input"}),
    )
    sites = forms.ModelMultipleChoiceField(
        queryset=Site.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    outlets = forms.ModelMultipleChoiceField(
        queryset=Outlet.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = Membership
        fields = ["role_preset", "role", "is_active", "sites", "outlets"]
        widgets = {
            "role": forms.Select(attrs={"class": "staff-input"}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant = tenant
        site_qs = Site.objects.none()
        outlet_qs = Outlet.objects.none()
        if tenant is not None:
            site_qs = Site.objects.filter(tenant=tenant).order_by("name")
            outlet_qs = Outlet.objects.filter(site__tenant=tenant).select_related("site").order_by("site__name", "name")
        self.fields["sites"].queryset = site_qs
        self.fields["outlets"].queryset = outlet_qs
        self.fields["sites"].help_text = "Leave empty for access to all sites in this workspace."
        self.fields["outlets"].help_text = "Leave empty for access to all outlets allowed by the selected sites."

    def clean_sites(self):
        sites = self.cleaned_data.get("sites")
        if self._tenant is None:
            return sites
        return sites.filter(tenant=self._tenant)

    def clean_outlets(self):
        outlets = self.cleaned_data.get("outlets")
        if self._tenant is None:
            return outlets
        return outlets.filter(site__tenant=self._tenant)

    def clean(self):
        data = apply_role_preset(super().clean())
        selected_sites = data.get("sites")
        selected_outlets = data.get("outlets")
        if selected_sites and selected_outlets:
            site_ids = set(selected_sites.values_list("id", flat=True))
            bad_outlets = [o.name for o in selected_outlets if o.site_id not in site_ids]
            if bad_outlets:
                raise forms.ValidationError(
                    {"outlets": "Selected outlets must belong to the selected sites."},
                )
        return data

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            instance.sites.set(self.cleaned_data.get("sites") or [])
            instance.outlets.set(self.cleaned_data.get("outlets") or [])
        else:
            self._pending_sites = list(self.cleaned_data.get("sites") or [])
            self._pending_outlets = list(self.cleaned_data.get("outlets") or [])
        return instance
