import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import TimeStampedModel


class Table(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="tables",
    )
    label = models.CharField(max_length=64)
    capacity = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1)])
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["outlet", "sort_order", "label"]
        unique_together = [["outlet", "label"]]

    def __str__(self) -> str:
        return f"{self.outlet}:{self.label}"


class OrderStatus(models.TextChoices):
    OPEN = "open", "Open"
    CANCELLED = "cancelled", "Cancelled"
    CLOSED = "closed", "Closed"


class OrderServiceMode(models.TextChoices):
    DINE_IN = "dine_in", "Dine in"
    TAKEAWAY = "takeaway", "Takeaway"
    COUNTER = "counter", "Counter sale"
    BAR_TAB = "bar_tab", "Bar tab"


class Order(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    table = models.ForeignKey(
        Table,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    status = models.CharField(
        max_length=16,
        choices=OrderStatus.choices,
        default=OrderStatus.OPEN,
    )
    bill_reference = models.CharField(max_length=32, blank=True, default="", db_index=True)
    quick_create_key = models.UUIDField(null=True, blank=True, help_text="Idempotency key for staff quick basket creation.")
    table_label = models.CharField(max_length=64, blank=True)
    service_mode = models.CharField(
        max_length=16,
        choices=OrderServiceMode.choices,
        blank=True,
        default="",
        help_text="Operational hospitality order type; blank preserves legacy/non-hospitality orders.",
    )
    guest_count = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text="Number of covers for hospitality service; null when not recorded or not applicable.",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_created",
    )
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    tax_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Order-level discount subtracted after line subtotals and tax (open orders only).",
    )
    folio = models.ForeignKey(
        "lodging.Folio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    applied_promotion = models.ForeignKey(
        "catalog.Promotion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "quick_create_key"], name="uniq_quick_basket_key_per_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "bill_reference"],
                name="uniq_order_bill_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bill_reference} ({self.status})"

    def save(self, *args, **kwargs) -> None:
        if self._state.adding:
            # New orders must use their own tenant's configured currency.
            # Historical orders are never silently converted when settings change.
            from apps.tenants.models import TenantSettings
            configured = TenantSettings.objects.filter(tenant_id=self.tenant_id).values_list(
                "default_currency", flat=True
            ).first()
            if configured:
                self.currency = configured.strip().upper()
            if not self.bill_reference:
                self.bill_reference = f"B-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class KdsLineStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    IN_PREP = "in_prep", "In prep"
    READY = "ready", "Ready"
    SERVED = "served", "Served"


class OrderLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
    )
    label = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Line subtotal before tax (qty × unit price).",
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    line_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    pricing_source = models.CharField(
        max_length=24,
        default="menu",
        help_text="Price source marker (menu, barcode, plu, weighted, manual).",
    )
    price_book_rule = models.ForeignKey(
        "pos.PriceBookRule",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_lines",
        help_text="Applied customer price-book rule, if any.",
    )
    price_book_base_unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Original unit price before customer price-book override.",
    )
    cost_unit_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Authoritative weighted-average inventory unit cost captured when the sale posts stock.",
    )
    cost_basis_complete_snapshot = models.BooleanField(
        default=False,
        help_text="Whether the captured cost represented the full outlet stock basis at sale time.",
    )
    merchandise_category_snapshot = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Merchandise category name captured when the sale line was created for historical reporting.",
    )
    merchandise_sku_snapshot = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="SKU captured for historical merchandise reporting.",
    )
    inventory_tracked_snapshot = models.BooleanField(
        null=True,
        blank=True,
        help_text="Whether this merchandise line was inventory tracked at sale time; null means legacy/unknown.",
    )
    sales_attributed_membership = models.ForeignKey(
        "accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributed_order_lines",
        help_text="Worker credited with this line when the sale was fully settled.",
    )
    commission_rule_name_snapshot = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Commission rule name captured at final settlement.",
    )
    commission_base_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Net line revenue used to calculate commission at final settlement.",
    )
    commission_rate_percent_snapshot = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Commission percentage captured at final settlement.",
    )
    commission_amount_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Commission earned on this line before later return/refund reversals.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    seat_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(999)],
        help_text="Optional dine-in seat assignment used for restaurant service and later bill splitting.",
    )
    is_voided = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=255, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines_voided",
    )
    kds_station = models.CharField(max_length=32, blank=True)
    kds_status = models.CharField(
        max_length=16,
        choices=KdsLineStatus.choices,
        default=KdsLineStatus.PENDING,
    )
    kds_rush = models.BooleanField(default=False, help_text="Show this prep item first.")
    kds_status_changed_at = models.DateTimeField(null=True, blank=True)
    modifiers_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Chosen modifier options at sale time (name + price_delta per option).",
    )

    class Meta:
        ordering = ["order", "sort_order", "created_at"]

    def __str__(self) -> str:
        return f"{self.label} x {self.quantity}"


class PriceBook(TimeStampedModel):
    """Tenant-defined retail customer price level; base menu price remains the fallback."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="price_books",
    )
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=48)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        blank=True,
        related_name="price_books",
        help_text="Empty means every retail outlet in this business.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uniq_price_book_code_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant", "name"],
                name="uniq_price_book_name_tenant",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PriceBookRule(TimeStampedModel):
    """Quantity tier targeting one SKU, family, brand, or category."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="price_book_rules",
    )
    price_book = models.ForeignKey(
        PriceBook,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.PROTECT,
        related_name="price_book_rules",
        null=True,
        blank=True,
    )
    product_family = models.ForeignKey(
        "catalog.ProductFamily",
        on_delete=models.PROTECT,
        related_name="price_book_rules",
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        "catalog.MenuCategory",
        on_delete=models.PROTECT,
        related_name="price_book_rules",
        null=True,
        blank=True,
    )
    brand = models.CharField(
        max_length=128,
        blank=True,
        help_text="Case-insensitive brand target. Leave blank unless this is a brand-wide rule.",
    )
    minimum_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_book", "-minimum_quantity", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["price_book", "menu_item", "minimum_quantity"],
                condition=models.Q(menu_item__isnull=False),
                name="uniq_price_book_item_tier",
            ),
            models.UniqueConstraint(
                fields=["price_book", "product_family", "minimum_quantity"],
                condition=models.Q(product_family__isnull=False),
                name="uniq_price_book_family_tier",
            ),
            models.UniqueConstraint(
                fields=["price_book", "category", "minimum_quantity"],
                condition=models.Q(category__isnull=False),
                name="uniq_price_book_category_tier",
            ),
            models.UniqueConstraint(
                Lower("brand"),
                "price_book",
                "minimum_quantity",
                condition=~models.Q(brand=""),
                name="uniq_price_book_brand_tier",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(menu_item__isnull=False, product_family__isnull=True, category__isnull=True, brand="")
                    | models.Q(menu_item__isnull=True, product_family__isnull=False, category__isnull=True, brand="")
                    | models.Q(menu_item__isnull=True, product_family__isnull=True, category__isnull=False, brand="")
                    | (models.Q(menu_item__isnull=True, product_family__isnull=True, category__isnull=True) & ~models.Q(brand=""))
                ),
                name="price_book_rule_exactly_one_target",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.price_book_id and self.tenant_id and self.price_book.tenant_id != self.tenant_id:
            raise ValidationError({"price_book": "Price book must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product must belong to this business."})
        if self.product_family_id and self.tenant_id and self.product_family.tenant_id != self.tenant_id:
            raise ValidationError({"product_family": "Product family must belong to this business."})
        if self.category_id and self.tenant_id and self.category.tenant_id != self.tenant_id:
            raise ValidationError({"category": "Category must belong to this business."})
        targets = int(bool(self.menu_item_id)) + int(bool(self.product_family_id)) + int(bool(self.category_id)) + int(bool((self.brand or "").strip()))
        if targets != 1:
            raise ValidationError("Choose exactly one price-rule target: product, family, brand, or category.")
        self.brand = (self.brand or "").strip()

    @property
    def target_label(self):
        if self.menu_item_id:
            return self.menu_item.name
        if self.product_family_id:
            return f"Family · {self.product_family.name}"
        if self.category_id:
            return f"Category · {self.category.name}"
        return f"Brand · {self.brand}"


class CustomerPriceBookAssignment(TimeStampedModel):
    """One active customer price level; changing it never rewrites paid history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="customer_price_book_assignments",
    )
    customer = models.OneToOneField(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="price_book_assignment",
    )
    price_book = models.ForeignKey(
        PriceBook,
        on_delete=models.PROTECT,
        related_name="customer_assignments",
    )
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_book_assignments_made",
    )

    class Meta:
        ordering = ["customer__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer"],
                name="uniq_customer_price_book_tenant",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.customer_id and self.tenant_id and self.customer.tenant_id != self.tenant_id:
            raise ValidationError({"customer": "Customer must belong to this business."})
        if self.price_book_id and self.tenant_id and self.price_book.tenant_id != self.tenant_id:
            raise ValidationError({"price_book": "Price book must belong to this business."})


class WholesalePriceRule(TimeStampedModel):
    """Manager-controlled B2B quantity-price tier, never implicit for walk-in sales."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="wholesale_price_rules")
    outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="wholesale_price_rules")
    menu_item = models.ForeignKey("catalog.MenuItem", on_delete=models.PROTECT, related_name="wholesale_price_rules")
    minimum_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["outlet", "menu_item", "-minimum_quantity"]
        constraints = [
            models.UniqueConstraint(fields=["outlet", "menu_item", "minimum_quantity"], name="uniq_wholesale_tier_per_outlet"),
            models.CheckConstraint(condition=models.Q(minimum_quantity__gt=0), name="wholesale_tier_qty_positive"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="wholesale_tier_price_nonnegative"),
        ]


class RetailPickup(TimeStampedModel):
    """Pickup handoff for an already fully paid sale; no second inventory posting."""
    class Status(models.TextChoices):
        AWAITING = "awaiting", "Awaiting customer"
        COLLECTED = "collected", "Collected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="retail_pickups")
    order = models.OneToOneField("pos.Order", on_delete=models.PROTECT, related_name="retail_pickup")
    expected_on = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AWAITING)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="retail_pickups_created")
    collected_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="retail_pickups_collected")
    collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["expected_on", "created_at"]



class OutletDeliverySettings(TimeStampedModel):
    """Explicit opt-in. A tenant's other outlets never inherit delivery."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="delivery_settings",
    )
    outlet = models.OneToOneField(
        "tenants.Outlet", on_delete=models.CASCADE, related_name="delivery_settings",
    )
    is_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["outlet"]


class OrderDelivery(TimeStampedModel):
    """Fulfillment lifecycle for one existing order, not another sale/payment."""
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ACCEPTED = "accepted", "Accepted"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready to dispatch"
        DISPATCHED = "dispatched", "Dispatched"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed attempt"
        RETURNED = "returned", "Returned"
        CANCELLED = "cancelled", "Cancelled"

    class DestinationType(models.TextChoices):
        ADDRESS = "address", "External address"
        ROOM = "room", "Hotel guest room"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="order_deliveries",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet", on_delete=models.PROTECT, related_name="order_deliveries",
    )
    order = models.OneToOneField(
        "pos.Order", on_delete=models.PROTECT, related_name="delivery",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.REQUESTED,
    )
    destination_type = models.CharField(max_length=16, choices=DestinationType.choices)
    recipient_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=500, blank=True)
    room_reference = models.CharField(max_length=64, blank=True)
    instructions = models.CharField(max_length=500, blank=True)
    promised_at = models.DateTimeField(null=True, blank=True)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3)
    assigned_driver = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_deliveries",
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL,
        related_name="created_deliveries",
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "outlet", "status"], name="pos_delivery_queue_idx")]


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK = "bank", "Bank transfer"
    OTHER = "other", "Other"


class Payment(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    shift = models.ForeignKey(
        "pos.PosShift", on_delete=models.PROTECT, null=True, blank=True,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_payment_idempotency_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.method} ({self.order.bill_reference})"


class Refund(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    shift = models.ForeignKey(
        "pos.PosShift", on_delete=models.PROTECT, null=True, blank=True,
        related_name="refunds",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_recorded",
    )
    restocked = models.BooleanField(
        default=False,
        help_text="If true, tracked inventory was increased for this refund.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_refund_idempotency_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"Refund {self.amount} ({self.order.bill_reference})"


class Workstation(TimeStampedModel):
    """Named physical device; selection alone never grants worker access."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="workstations")
    outlet = models.ForeignKey("tenants.Outlet", on_delete=models.PROTECT, related_name="workstations")
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40)
    is_active = models.BooleanField(default=True)
    requires_pairing = models.BooleanField(default=False, help_text="Require administrator-approved browser pairing for staff register operations.")
    receipt_printer = models.CharField(max_length=120, blank=True)
    kitchen_printer = models.CharField(max_length=120, blank=True)
    cash_drawer = models.CharField(max_length=80, blank=True)
    kds_station = models.CharField(max_length=64, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["outlet__name", "name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "code"], name="uniq_workstation_code_per_tenant")]

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.outlet_id and self.tenant_id and self.outlet.site.tenant_id != self.tenant_id:
            raise ValidationError({"outlet": "Choose a section in this workspace."})

    def __str__(self):
        return f"{self.name} ({self.code})"


class WorkstationPairing(TimeStampedModel):
    """Revocable browser credential. Never stores the raw 256-bit secret."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="workstation_pairings")
    workstation = models.ForeignKey(Workstation, on_delete=models.PROTECT, related_name="pairings")
    label = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=64, editable=False)
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="workstation_pairings_approved")
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="workstation_pairings_revoked")
    revocation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PosShiftStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class PosShift(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pos_shifts",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="pos_shifts",
    )
    workstation = models.ForeignKey(
        Workstation, on_delete=models.PROTECT, null=True, blank=True, related_name="shifts",
    )
    status = models.CharField(max_length=16, choices=PosShiftStatus.choices, default=PosShiftStatus.OPEN)
    opened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_shifts_opened",
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_shifts_closed",
    )
    cash_attribution = models.BooleanField(
        default=True, help_text="Use explicit payment/refund links; older shifts retain time-window accounting.",
    )
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["workstation"], condition=models.Q(status="open", workstation__isnull=False), name="uniq_open_shift_workstation"),
            models.UniqueConstraint(fields=["outlet"], condition=models.Q(status="open", workstation__isnull=True), name="uniq_open_section_shift"),
        ]

    def __str__(self) -> str:
        return f"{self.outlet.name} shift {self.status}"


class SupermarketLineReturn(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund = models.OneToOneField(
        Refund, on_delete=models.PROTECT, null=True, blank=True,
        related_name="line_return",
        help_text="Customer refund recorded with this physical return, if any.",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    order_line = models.ForeignKey(
        OrderLine,
        on_delete=models.CASCADE,
        related_name="supermarket_returns",
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    reason = models.CharField(max_length=255, blank=True)
    restocked = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supermarket_returns_created",
    )
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Optional tenant-scoped retry identity for a physical return.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_supermarket_return_retry_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order.bill_reference} return {self.quantity}"


class WorkstationHardwareCheck(models.Model):
    """Append-only, operator-observed hardware test result (not telemetry)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE,
        related_name="hardware_checks",
    )
    workstation = models.ForeignKey(
        Workstation, on_delete=models.PROTECT,
        related_name="hardware_checks",
    )
    checked_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="hardware_checks",
    )
    test_type = models.CharField(
        max_length=20, choices=[
            ("receipt_printer", "Receipt printer"),
            ("barcode_scanner", "Barcode scanner"),
            ("kitchen_display", "Kitchen printer or display"),
            ("cash_drawer", "Cash drawer"),
            ("weighing_scale", "Weighing scale"),
        ],
    )
    result = models.CharField(
        max_length=12, choices=[
            ("pass", "Observed working"), ("fail", "Observed failure"),
            ("not_tested", "Not tested"),
        ],
    )
    note = models.CharField(max_length=500, blank=True)
    configured_device = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

class OfflineQueueStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class OfflineQueuedOperation(TimeStampedModel):
    """Client-side POS queue: idempotent replay when connectivity returns."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="offline_queue",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="offline_queue",
    )
    client_mutation_id = models.CharField(
        max_length=128,
        help_text="Unique per device/session; prevents duplicate apply.",
    )
    operation_type = models.CharField(
        max_length=32,
        help_text="e.g. order_payment, order_create",
    )
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16,
        choices=OfflineQueueStatus.choices,
        default=OfflineQueueStatus.PENDING,
    )
    error_message = models.TextField(blank=True)
    applied_payment_id = models.UUIDField(null=True, blank=True)
    applied_order_id = models.UUIDField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="offline_reviews",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_mutation_id"],
                name="uniq_offline_queue_client_mutation_per_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operation_type} ({self.status})"


class CashDrawerMovement(TimeStampedModel):
    """Immutable physical drawer movement tied to one register shift."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="cash_drawer_movements")
    shift = models.ForeignKey(PosShift, on_delete=models.PROTECT, related_name="cash_movements")
    direction = models.CharField(max_length=16, choices=[("float_add", "Float added"), ("drop", "Cash drop"), ("payout", "Cash payout")])
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="cash_drawer_movements")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["shift", "idempotency_key"], name="unique_drawer_movement_key_per_shift")]


class ShiftHandover(TimeStampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Awaiting independent count"
        VERIFIED = "verified", "Awaiting manager approval"
        APPROVED = "approved", "Awaiting next cashier"
        ACCEPTED = "accepted", "Accepted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="shift_handovers")
    shift = models.OneToOneField(PosShift, on_delete=models.PROTECT, related_name="handover")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED)
    variance_explanation = models.CharField(max_length=512, blank=True)
    verified_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    verification_note = models.CharField(max_length=512, blank=True)
    verified_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_shift_handovers")
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_shift_handovers")
    approval_note = models.CharField(max_length=512, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_shift_handovers")
    accepted_at = models.DateTimeField(null=True, blank=True)
    next_shift = models.OneToOneField(PosShift, on_delete=models.PROTECT, null=True, blank=True, related_name="prior_handover")

    class Meta:
        ordering = ["-created_at"]
