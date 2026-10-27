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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["supplier__name", "menu_item__name", "code"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                "supplier",
                name="uniq_supplier_product_code_ci",
            ),
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

    def __str__(self) -> str:
        return f"{self.supplier.name} · {self.code} · {self.menu_item.name}"


class PurchaseOrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    PARTIALLY_RECEIVED = "partially_received", "Partially received"
    RECEIVED = "received", "Fully received"
    CANCELLED = "cancelled", "Cancelled"


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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="purchase_receipts")
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="receipts")
    delivery_reference = models.CharField(max_length=128, blank=True)
    note = models.CharField(max_length=512, blank=True)
    discrepancy_note = models.CharField(max_length=512, blank=True)
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
