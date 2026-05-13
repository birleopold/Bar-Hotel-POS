import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


def default_enabled_staff_modules():
    """All staff product areas enabled until a tenant narrows their plan."""
    return [
        "pos",
        "kitchen",
        "promotions",
        "inventory",
        "purchasing",
        "lodging",
        "events",
        "finance",
        "workspace",
    ]


def default_plan_included_modules():
    return default_enabled_staff_modules()


def staff_module_choices() -> list[tuple[str, str]]:
    return [
        ("pos", "Point of sale"),
        ("kitchen", "Prep queue (KDS)"),
        ("promotions", "Offers"),
        ("inventory", "Stock"),
        ("purchasing", "Purchasing"),
        ("lodging", "Lodging & rooms"),
        ("events", "Events & spaces"),
        ("finance", "Finance (income & expenses)"),
        ("workspace", "Workspace & team"),
    ]


STAFF_MODULE_KEYS = {
    "pos",
    "kitchen",
    "promotions",
    "inventory",
    "purchasing",
    "lodging",
    "events",
    "finance",
    "workspace",
}


class Tenant(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TenantSettings(TimeStampedModel):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    business_lines = models.JSONField(
        default=list,
        help_text=(
            "Business lines enabled for this workspace. "
            "Keys: bar, lounge, restaurant, cafeteria, lodging, retail, supermarket, events."
        ),
    )
    default_currency = models.CharField(max_length=3, default="USD")
    default_timezone = models.CharField(max_length=64, default="UTC")
    receipt_footer = models.TextField(blank=True)
    theme_primary = models.CharField(max_length=7, default="#E85D4C", help_text="Hex color")
    theme_secondary = models.CharField(max_length=7, default="#2DD4BF", help_text="Hex color")
    theme_accent = models.CharField(max_length=7, default="#FBBF24", help_text="Hex color")
    logo_url = models.URLField(blank=True)
    enabled_staff_modules = models.JSONField(
        default=default_enabled_staff_modules,
        help_text=(
            "Staff UI modules this tenant subscribes to. "
            "Keys: pos, kitchen, promotions, inventory, purchasing, lodging, events, workspace."
        ),
    )
    hardware_barcode_scanner_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, scanner-first barcode/PLU controls appear in POS.",
    )
    hardware_cash_drawer_enabled = models.BooleanField(
        default=False,
        help_text="If enabled, cash-drawer specific hints/actions can be shown in POS.",
    )
    hardware_receipt_printer_enabled = models.BooleanField(
        default=True,
        help_text="If enabled, receipt/bill print shortcuts appear in POS.",
    )
    efris_enabled = models.BooleanField(
        default=False,
        help_text=(
            "If enabled, finance postings are queued for Uganda EFRIS submission. "
            "Keep off for properties that do not use EFRIS."
        ),
    )

    def __str__(self) -> str:
        return f"Settings for {self.tenant.name}"


class Site(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=255)
    address_line = models.CharField(max_length=512, blank=True)
    city = models.CharField(max_length=128, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tenant", "name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.name}"


class OutletType(models.TextChoices):
    RESTAURANT = "restaurant", "Restaurant"
    BAR = "bar", "Bar"
    LOUNGE = "lounge", "Lounge"
    CAFETERIA = "cafeteria", "Cafeteria"
    LODGING_FRONT_DESK = "lodging_front_desk", "Lodging / front desk"
    RETAIL = "retail", "Retail / shop"
    SUPERMARKET = "supermarket", "Supermarket / grocery"
    EVENT_SPACE = "event_space", "Event space"


class Outlet(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="outlets")
    name = models.CharField(max_length=255)
    outlet_type = models.CharField(
        max_length=32,
        choices=OutletType.choices,
        default=OutletType.RESTAURANT,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site", "name"]
        unique_together = [["site", "name"]]

    def __str__(self) -> str:
        return f"{self.site}:{self.name}"

    @property
    def tenant(self) -> Tenant:
        return self.site.tenant


class TenantSetupProgress(TimeStampedModel):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="setup_progress",
    )
    suppress_dashboard_prompt = models.BooleanField(default=False)
    last_completion_percent = models.PositiveSmallIntegerField(default=0)
    last_next_step_key = models.CharField(max_length=64, blank=True)
    step_state_overrides = models.JSONField(
        default=dict,
        help_text="Optional per-step manual states (e.g. skipped, blocked).",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tenant__name"]

    def __str__(self) -> str:
        return f"Setup progress for {self.tenant.name}"


class SubscriptionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    SUSPENDED = "suspended", "Suspended"
    CANCELLED = "cancelled", "Cancelled"


class Plan(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    included_modules = models.JSONField(
        default=default_plan_included_modules,
        help_text="Staff module keys enabled by default on this plan.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TenantSubscription(TimeStampedModel):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=16,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tenant__name"]

    def __str__(self) -> str:
        return f"{self.tenant.name}: {self.plan.name} ({self.status})"


class TenantFeatureEntitlement(TimeStampedModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="feature_entitlements",
    )
    module_key = models.CharField(max_length=32)
    is_enabled = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["tenant__name", "module_key"]
        unique_together = [["tenant", "module_key"]]

    def __str__(self) -> str:
        state = "on" if self.is_enabled else "off"
        return f"{self.tenant.name}: {self.module_key}={state}"


class TenantOutletModulePolicy(TimeStampedModel):
    """Optional per-outlet-type module policy layered on top of tenant-level entitlements."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="outlet_module_policies",
    )
    outlet_type = models.CharField(max_length=32, choices=OutletType.choices)
    enabled_modules = models.JSONField(
        default=default_enabled_staff_modules,
        help_text="Module keys enabled for this outlet type in this tenant.",
    )
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["tenant__name", "outlet_type"]
        unique_together = [["tenant", "outlet_type"]]

    def __str__(self) -> str:
        return f"{self.tenant.name}: {self.outlet_type}"


class BillingInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAST_DUE = "past_due", "Past due"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


class BillingInvoice(TimeStampedModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="billing_invoices",
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    invoice_number = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=16,
        choices=BillingInvoiceStatus.choices,
        default=BillingInvoiceStatus.DRAFT,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    external_ref = models.CharField(max_length=128, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [["tenant", "invoice_number"]]

    def __str__(self) -> str:
        return f"{self.tenant.name} {self.invoice_number}"


class BillingEventType(models.TextChoices):
    NOTE = "note", "Note"
    INVOICE_CREATED = "invoice_created", "Invoice created"
    INVOICE_STATUS_CHANGED = "invoice_status_changed", "Invoice status changed"
    SUBSCRIPTION_STATUS_CHANGED = "subscription_status_changed", "Subscription status changed"


class BillingEvent(TimeStampedModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="billing_events",
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_events",
    )
    invoice = models.ForeignKey(
        BillingInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_events",
    )
    event_type = models.CharField(
        max_length=40,
        choices=BillingEventType.choices,
        default=BillingEventType.NOTE,
    )
    message = models.TextField(blank=True)
    previous_subscription_status = models.CharField(max_length=16, blank=True)
    new_subscription_status = models.CharField(max_length=16, blank=True)
    previous_invoice_status = models.CharField(max_length=16, blank=True)
    new_invoice_status = models.CharField(max_length=16, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]

    def __str__(self) -> str:
        return f"{self.tenant.name}: {self.event_type}"
