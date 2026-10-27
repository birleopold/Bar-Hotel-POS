import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import TimeStampedModel


class Supplier(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="suppliers",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    address_line = models.CharField(max_length=512, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tenant", "name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return self.name


class SupplierProductCode(TimeStampedModel):
    """Supplier-specific lookup code for an existing product or purchase package."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="supplier_product_codes",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="product_codes",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="supplier_codes",
    )
    product_package = models.ForeignKey(
        "catalog.ProductPackage",
        on_delete=models.CASCADE,
        related_name="supplier_codes",
        null=True,
        blank=True,
        help_text="Optional package this supplier code identifies.",
    )
    code = models.CharField(max_length=128)
    description = models.CharField(max_length=160, blank=True)
    default_unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Planning cost per base unit for new purchase orders from this supplier.",
    )
    minimum_order_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Optional minimum base-stock quantity when ordering this product from this supplier.",
    )
    expected_lead_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional expected calendar days from order to delivery for this supplier/product relationship.",
    )
    is_preferred = models.BooleanField(
        default=False,
        help_text="Preferred supplier relationship for this product. Only one preferred supplier may exist per product.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["supplier__name", "menu_item__name", "code"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                "supplier",
                name="uniq_supplier_product_code_ci",
            ),
            models.UniqueConstraint(
                fields=["tenant", "menu_item"],
                condition=models.Q(is_preferred=True),
                name="uniq_preferred_supplier_per_product",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.supplier_id and self.tenant_id and self.supplier.tenant_id != self.tenant_id:
            raise ValidationError({"supplier": "Supplier must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product must belong to this business."})
        if self.is_preferred and self.product_package_id:
            raise ValidationError({
                "is_preferred": "Set preferred supplier on the base product relationship, not a package-specific code."
            })
        if self.product_package_id:
            if self.product_package.tenant_id != self.tenant_id:
                raise ValidationError({"product_package": "Package must belong to this business."})
            if self.product_package.menu_item_id != self.menu_item_id:
                raise ValidationError({"product_package": "Package must belong to the selected product."})

    def __str__(self) -> str:
        return f"{self.supplier.name} · {self.code} · {self.menu_item.name}"


class SupplierPriceRecord(TimeStampedModel):
    """Effective-dated supplier purchase price evidence used for PO suggestions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="supplier_price_records",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="price_records",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.CASCADE,
        related_name="supplier_price_records",
    )
    product_package = models.ForeignKey(
        "catalog.ProductPackage",
        on_delete=models.CASCADE,
        related_name="supplier_price_records",
        null=True,
        blank=True,
        help_text="Optional purchasing package this supplier price applies to.",
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    minimum_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.001"),
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Minimum base-stock quantity required for this price.",
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    source_reference = models.CharField(
        max_length=128,
        blank=True,
        help_text="Supplier contract, price-list or quotation reference.",
    )
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = [
            "supplier__name", "menu_item__name",
            "-minimum_quantity", "-valid_from", "-created_at",
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.supplier_id and self.tenant_id and self.supplier.tenant_id != self.tenant_id:
            raise ValidationError({"supplier": "Supplier must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product must belong to this business."})
        if self.product_package_id:
            if self.product_package.tenant_id != self.tenant_id:
                raise ValidationError({"product_package": "Package must belong to this business."})
            if self.product_package.menu_item_id != self.menu_item_id:
                raise ValidationError({"product_package": "Package must belong to the selected product."})
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "End date cannot be earlier than start date."})

    def __str__(self) -> str:
        return (
            f"{self.supplier.name} · {self.menu_item.name} · "
            f"{self.minimum_quantity}+ @ {self.unit_cost}"
        )


class PurchaseRfqStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open for quotations"
    AWARDED = "awarded", "Awarded"
    CANCELLED = "cancelled", "Cancelled"


class SupplierQuoteStatus(models.TextChoices):
    INVITED = "invited", "Invited / awaiting quote"
    SUBMITTED = "submitted", "Quote received"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Not selected"


class PurchaseRfq(TimeStampedModel):
    """Simple competitive sourcing request that converts into the normal PO flow."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="purchase_rfqs",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet", on_delete=models.PROTECT, related_name="purchase_rfqs",
        help_text="Outlet/warehouse that will receive the awarded purchase order.",
    )
    reference = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16, choices=PurchaseRfqStatus.choices,
        default=PurchaseRfqStatus.DRAFT,
    )
    needed_by = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_rfqs_created",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("reference"), "tenant", name="uniq_purchase_rfq_reference_ci",
            ),
        ]

    def __str__(self) -> str:
        return f"RFQ {self.reference} ({self.status})"


class PurchaseRfqLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="purchase_rfq_lines",
    )
    rfq = models.ForeignKey(
        PurchaseRfq, on_delete=models.CASCADE, related_name="lines",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem", on_delete=models.PROTECT, related_name="purchase_rfq_lines",
    )
    quantity_requested = models.DecimalField(
        max_digits=14, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["rfq", "menu_item__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["rfq", "menu_item"], name="uniq_purchase_rfq_item",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.rfq_id and self.tenant_id and self.rfq.tenant_id != self.tenant_id:
            raise ValidationError({"rfq": "RFQ must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product must belong to this business."})


class SupplierQuote(TimeStampedModel):
    """One supplier response/invitation against an RFQ."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_quotes",
    )
    rfq = models.ForeignKey(
        PurchaseRfq, on_delete=models.CASCADE, related_name="quotes",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="quotes",
    )
    status = models.CharField(
        max_length=16, choices=SupplierQuoteStatus.choices,
        default=SupplierQuoteStatus.INVITED,
    )
    reference = models.CharField(
        max_length=128, blank=True,
        help_text="Supplier quotation/reference number.",
    )
    shipping_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    other_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Other quoted charges not included in item unit prices.",
    )
    lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    availability_note = models.CharField(max_length=255, blank=True)
    payment_terms = models.CharField(max_length=255, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    converted_purchase_order = models.OneToOneField(
        "purchasing.PurchaseOrder", on_delete=models.PROTECT,
        null=True, blank=True, related_name="source_supplier_quote",
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="supplier_quotes_recorded",
    )

    class Meta:
        ordering = ["rfq", "supplier__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["rfq", "supplier"], name="uniq_supplier_quote_per_rfq",
            ),
            models.UniqueConstraint(
                fields=["rfq"],
                condition=models.Q(status=SupplierQuoteStatus.ACCEPTED),
                name="uniq_accepted_quote_per_rfq",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.rfq_id and self.tenant_id and self.rfq.tenant_id != self.tenant_id:
            raise ValidationError({"rfq": "RFQ must belong to this business."})
        if self.supplier_id and self.tenant_id and self.supplier.tenant_id != self.tenant_id:
            raise ValidationError({"supplier": "Supplier must belong to this business."})


class SupplierQuoteLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_quote_lines",
    )
    quote = models.ForeignKey(
        SupplierQuote, on_delete=models.CASCADE, related_name="lines",
    )
    rfq_line = models.ForeignKey(
        PurchaseRfqLine, on_delete=models.PROTECT, related_name="quote_lines",
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    quantity_available = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Blank means supplier did not state an availability limit.",
    )
    promised_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["quote", "rfq_line__menu_item__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["quote", "rfq_line"], name="uniq_supplier_quote_rfq_line",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quote_id and self.tenant_id and self.quote.tenant_id != self.tenant_id:
            raise ValidationError({"quote": "Quote must belong to this business."})
        if self.rfq_line_id and self.quote_id and self.rfq_line.rfq_id != self.quote.rfq_id:
            raise ValidationError({"rfq_line": "Quoted product must belong to this RFQ."})


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    PARTIALLY_RECEIVED = "partially_received", "Partially received"
    RECEIVED = "received", "Fully received"
    CANCELLED = "cancelled", "Cancelled"


class PurchaseApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class PurchaseOrder(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="purchase_orders",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        help_text="Receiving outlet / warehouse.",
    )
    status = models.CharField(
        max_length=24,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
    )
    reference = models.CharField(
        max_length=128,
        blank=True,
        help_text="Supplier or internal reference number.",
    )
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_created",
    )
    approval_status = models.CharField(
        max_length=16,
        choices=PurchaseApprovalStatus.choices,
        default=PurchaseApprovalStatus.APPROVED,
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=512, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"PO {self.reference or self.id} ({self.status})"


class PurchaseOrderLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    menu_item = models.ForeignKey(
        "catalog.MenuItem",
        on_delete=models.PROTECT,
        related_name="purchase_order_lines",
    )
    quantity_ordered = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    units_per_carton_snapshot = models.PositiveSmallIntegerField(default=1)
    product_package = models.ForeignKey(
        "catalog.ProductPackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_order_lines",
        help_text="Optional package selected when this PO line was created.",
    )
    package_name_snapshot = models.CharField(max_length=96, blank=True)
    package_units_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Base stock units per selected package at the time the PO was created.",
    )
    package_quantity_ordered = models.PositiveIntegerField(default=0)
    quantity_received = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["purchase_order", "menu_item__name"]
        unique_together = [["purchase_order", "menu_item"]]

    def __str__(self) -> str:
        return f"{self.menu_item.name} x {self.quantity_ordered}"

    @property
    def quantity_remaining(self) -> Decimal:
        return self.quantity_ordered - self.quantity_received


class PurchaseReceipt(TimeStampedModel):
    """One physical delivery received against a purchase order."""

    class LandedCostAllocation(models.TextChoices):
        EXCLUDE = "exclude", "Do not add to inventory cost"
        BY_COST = "by_cost", "Distribute by received supplier cost"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="purchase_receipts")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="receipts")
    delivery_reference = models.CharField(max_length=128, blank=True)
    note = models.CharField(max_length=512, blank=True)
    discrepancy_note = models.CharField(max_length=512, blank=True)
    shipping_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Shipping/freight paid for this physical delivery.",
    )
    duty_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Import duty, clearing or similar landed cost for this delivery.",
    )
    landed_cost_allocation = models.CharField(
        max_length=16,
        choices=LandedCostAllocation.choices,
        default=LandedCostAllocation.EXCLUDE,
    )
    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_receipts_recorded",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.delivery_reference or f"Receipt {self.id}"


class PurchaseReceiptLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    purchase_order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity_received = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    cartons_received = models.PositiveIntegerField(default=0)
    packages_received = models.PositiveIntegerField(default=0)
    unit_cost_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Supplier unit cost captured when this physical receipt was posted.",
    )
    landed_unit_cost_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Supplier cost plus this receipt line's allocated landed costs per base unit.",
    )
    landed_cost_allocated = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Shipping/duty amount allocated to this receipt line.",
    )
    inventory_batch = models.ForeignKey(
        "inventory.InventoryBatch", on_delete=models.PROTECT,
        null=True, blank=True, related_name="purchase_receipt_lines",
    )

    class Meta:
        ordering = ["receipt", "purchase_order_line__menu_item__name"]


class SupplierPaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank transfer"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class SupplierPayment(TimeStampedModel):
    """Actual settlement of received goods; distinct from physical receipt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_payments")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    invoice = models.ForeignKey("purchasing.SupplierInvoice", on_delete=models.PROTECT, null=True, blank=True, related_name="allocated_payments", help_text="Verified invoice; legacy PO payments are unallocated.")
    method = models.CharField(max_length=24, choices=SupplierPaymentMethod.choices)
    reference = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="supplier_payments_recorded"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "idempotency_key"], name="uniq_supplier_payment_key_tenant"),
        ]


class SupplierInvoice(TimeStampedModel):
    """Supplier document against received goods; does NOT post payment or expense."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_invoices",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="invoices",
    )
    reference = models.CharField(max_length=128)
    invoice_date = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    note = models.CharField(max_length=512, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="supplier_invoices_recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "purchase_order", "reference"],
                name="uniq_supplier_invoice_reference_po",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="supplier_invoice_amount_positive",
            ),
        ]


class SupplierInvoiceLine(TimeStampedModel):
    """Immutable PO/GRN quantity and quoted-cost evidence for invoice matching."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey("purchasing.SupplierInvoice", on_delete=models.PROTECT, related_name="matched_lines")
    purchase_order_line = models.ForeignKey("purchasing.PurchaseOrderLine", on_delete=models.PROTECT, related_name="invoice_matches")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["invoice", "purchase_order_line"], name="uniq_supplier_invoice_line_po_line"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="supplier_invoice_line_qty_positive"),
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="supplier_invoice_line_cost_nonnegative"),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="supplier_invoice_line_amount_nonnegative"),
        ]


class SupplierReturn(TimeStampedModel):
    """Confirmed outward stock movement to vendor; credit/refund is independent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_returns")
    purchase_order = models.ForeignKey("purchasing.PurchaseOrder", on_delete=models.PROTECT, related_name="returns_to_supplier")
    receipt_line = models.ForeignKey("purchasing.PurchaseReceiptLine", on_delete=models.PROTECT, related_name="supplier_returns")
    movement = models.OneToOneField("inventory.StockMovement", on_delete=models.PROTECT, related_name="supplier_return")
    reference = models.CharField(max_length=128)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    note = models.CharField(max_length=512)
    returned_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="supplier_returns_processed")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["purchase_order", "reference"], name="uniq_supplier_return_reference_po"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="supplier_return_quantity_positive"),
        ]


class SupplierCreditNote(TimeStampedModel):
    """A verified vendor-issued credit against a recorded invoice, not a refund.

    No stock or cashbook movement is posted by recording this document.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="supplier_credit_notes",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="credits",
    )
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.PROTECT, related_name="credits",
    )
    reference = models.CharField(max_length=128)
    credit_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=512)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="supplier_credit_notes_recorded",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "purchase_order", "reference"],
                name="uniq_supplier_credit_reference_po",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="supplier_credit_amount_positive",
            ),
        ]
