import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

from apps.common.models import TimeStampedModel


class MenuCategory(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="menu_categories",
    )
    name = models.CharField(max_length=128)
    offer_type = models.CharField(
        max_length=24,
        choices=OfferType.choices,
        default=OfferType.STANDARD,
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return f"{self.tenant.slug}:{self.name}"


class UnitOfMeasure(models.TextChoices):
    EACH = "each", "Each (SKU / piece)"
    KG = "kg", "Kilogram"
    LB = "lb", "Pound"
    LITER = "liter", "Liter"


class SerialIdentifierType(models.TextChoices):
    SERIAL = "serial", "Serial number"
    IMEI = "imei", "IMEI"
    CUSTOM = "custom", "Custom identifier"


class ProductFamily(TimeStampedModel):
    """Optional parent merchandise record for related sellable variants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_families",
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.PROTECT,
        related_name="product_families",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    variant_schema = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered variant dimensions and allowed values for matrix-generated sellable SKUs.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category__sort_order", "category__name", "name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return self.name


class MenuItem(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="menu_items",
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.PROTECT,
        related_name="items",
    )
    product_family = models.ForeignKey(
        ProductFamily,
        on_delete=models.SET_NULL,
        related_name="variants",
        null=True,
        blank=True,
        help_text="Optional parent product used to group concrete size/colour/style variants.",
    )
    variant_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="Canonical key for a matrix-generated variant; blank for ordinary/manual products.",
    )
    variant_values = models.JSONField(
        default=dict,
        blank=True,
        help_text="Variant dimension snapshot such as Colour=Black and Size=M.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    brand = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional brand or manufacturer name.",
    )
    model_number = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional model, style, or manufacturer model number.",
    )
    reference_code = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional internal or manufacturer reference code.",
    )
    msrp = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Optional manufacturer suggested retail price; does not override the selling price.",
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Include this item in rotating Service TV menu highlights.",
    )
    product_image = models.ImageField(
        upload_to="products/%Y/%m/",
        blank=True,
        help_text="Upload a JPEG, PNG, or WebP product photo (maximum 5 MB).",
    )
    @property
    def product_image_src(self):
        if self.product_image:
            return self.product_image.url
        return self.display_image_url

    @property
    def product_image_render_src(self):
        """Cache-safe, app-served URL for displaying an uploaded product photo.

        Do not depend on a reverse proxy's /media/ alias for uploaded product
        images. The dedicated Django route reads the same canonical MEDIA_ROOT
        and therefore survives stale or mismatched nginx/Caddy media aliases.
        """
        if not self.product_image:
            return self.display_image_url
        name = (self.product_image.name or "").lstrip("/")
        prefix = "products/"
        if not name.startswith(prefix):
            return self.product_image.url
        path = name[len(prefix):]
        src = reverse("public-product-media-direct", kwargs={"path": path})
        version = int(self.updated_at.timestamp()) if self.updated_at else 0
        separator = "&" if "?" in src else "?"
        return f"{src}{separator}v={version}"

    display_image_url = models.URLField(
        blank=True,
        help_text="Optional public image URL used on guest-facing and Service TV displays.",
    )
    availability_note = models.CharField(
        max_length=160,
        blank=True,
        help_text="Optional short guest-facing availability note, such as 'Available until 4 PM'.",
    )
    sku = models.CharField(max_length=64, blank=True)
    barcode = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Scannable barcode / PLU for retail and supermarket POS.",
    )
    unit_of_measure = models.CharField(
        max_length=16,
        choices=UnitOfMeasure.choices,
        default=UnitOfMeasure.EACH,
    )
    units_per_carton = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
        help_text="Pieces in one supplier carton; 1 means cartons are not configured.",
    )
    track_inventory = models.BooleanField(
        default=False,
        help_text="When true, outlet stock is reduced when the order is paid.",
    )
    serial_tracking = models.BooleanField(
        default=False,
        help_text="Track every physical unit by serial number or IMEI. Requires piece-based inventory tracking.",
    )
    serial_identifier_type = models.CharField(
        max_length=16,
        choices=SerialIdentifierType.choices,
        default=SerialIdentifierType.SERIAL,
    )
    warranty_months = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(240)],
        help_text="Optional default warranty term for serialized units, in months.",
    )
    reorder_level = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Optional low-stock hint for dashboards (same UoM as quantity).",
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="If set, tax is computed on the line subtotal (exclusive).",
    )
    is_active = models.BooleanField(default=True)
    kds_station = models.CharField(
        max_length=32,
        blank=True,
        help_text="Default kitchen display station tag (e.g. kitchen, bar).",
    )
    consume_recipe_on_sale = models.BooleanField(
        default=False,
        help_text="When true and the order is fully paid, deduct recipe ingredient stock.",
    )
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        through="MenuItemOutlet",
        related_name="menu_items",
        blank=True,
        help_text="If empty, item is offered at every outlet of the tenant.",
    )

    class Meta:
        ordering = ["category__sort_order", "category__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_family", "variant_key"],
                condition=~models.Q(variant_key=""),
                name="uniq_product_family_variant_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(serial_tracking=False)
                    | (
                        models.Q(track_inventory=True)
                        & models.Q(unit_of_measure=UnitOfMeasure.EACH)
                    )
                ),
                name="serialized_item_requires_piece_stock",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def unit_price_for_outlet(self, outlet_id: uuid.UUID) -> Decimal:
        link = self.outlet_links.filter(outlet_id=outlet_id).first()
        if link and link.price_override is not None:
            return link.price_override
        return self.unit_price


class ProductCustomFieldDefinition(TimeStampedModel):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Yes / no"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_custom_field_definitions",
    )
    name = models.CharField(max_length=96)
    key = models.SlugField(max_length=96)
    field_type = models.CharField(max_length=16, choices=FieldType.choices, default=FieldType.TEXT)
    help_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="uniq_product_custom_field_key_tenant"),
            models.UniqueConstraint(
                Lower("key"),
                "tenant",
                name="uniq_product_custom_field_key_ci_tenant",
            ),
            models.UniqueConstraint(Lower("name"), "tenant", name="uniq_product_custom_field_name_ci_tenant"),
        ]

    def __str__(self) -> str:
        return self.name


class ProductCustomFieldValue(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_custom_field_values",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="custom_field_values",
    )
    definition = models.ForeignKey(
        ProductCustomFieldDefinition,
        on_delete=models.CASCADE,
        related_name="values",
    )
    value_text = models.TextField(blank=True)

    class Meta:
        ordering = ["definition__sort_order", "definition__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "definition"],
                name="uniq_product_custom_value_item_definition",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product and custom value must belong to the same business."})
        if self.definition_id and self.tenant_id and self.definition.tenant_id != self.tenant_id:
            raise ValidationError({"definition": "Custom field and value must belong to the same business."})

    def typed_value(self):
        if self.definition.field_type == ProductCustomFieldDefinition.FieldType.BOOLEAN:
            return self.value_text.strip().lower() in {"1", "true", "yes", "on"}
        if self.definition.field_type == ProductCustomFieldDefinition.FieldType.NUMBER:
            try:
                return Decimal(self.value_text)
            except Exception:
                return None
        return self.value_text


class ProductAlternateCode(TimeStampedModel):
    class CodeType(models.TextChoices):
        INTERNAL = "internal", "Internal"
        SUPPLIER = "supplier", "Supplier"
        MANUFACTURER = "manufacturer", "Manufacturer"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_alternate_codes",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="alternate_codes",
    )
    code = models.CharField(max_length=128, db_index=True)
    code_type = models.CharField(max_length=16, choices=CodeType.choices, default=CodeType.INTERNAL)
    label = models.CharField(max_length=96, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["menu_item__name", "code_type", "code"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                "tenant",
                name="uniq_product_alternate_code_ci_tenant",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Product and alternate code must belong to the same business."})

    def __str__(self) -> str:
        return f"{self.menu_item.name} · {self.code}"


class ProductLabelQueueEntry(TimeStampedModel):
    class Reason(models.TextChoices):
        NEW_PRODUCT = "new_product", "New product"
        PRICE_CHANGE = "price_change", "Price change"
        RECEIVING = "receiving", "Goods received"
        MANUAL = "manual", "Manual request"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PRINTED = "printed", "Printed"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_label_queue_entries",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="product_label_queue_entries",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="label_queue_entries",
    )
    reason = models.CharField(max_length=24, choices=Reason.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    price_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    note = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_label_requests",
    )
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_label_completions",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["outlet", "menu_item", "reason"],
                condition=models.Q(status="pending"),
                name="uniq_pending_label_reason_item_outlet",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.outlet_id and self.tenant_id and self.outlet.site.tenant_id != self.tenant_id:
            raise ValidationError({"outlet": "Label outlet must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Label product must belong to this business."})


class ProductPackage(TimeStampedModel):
    """Alternative scannable sell/purchase pack that converts into base stock units."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="product_packages",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="packages",
    )
    name = models.CharField(max_length=96, help_text="For example 6-pack, case of 24, or carton.")
    units_per_package = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Number of base stock units represented by one package.",
    )
    barcode = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Optional barcode that identifies this package size.",
    )
    sku_alias = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional supplier/internal code for this package.",
    )
    sell_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Optional package selling price. Blank means base unit price × package quantity.",
    )
    is_sellable = models.BooleanField(default=True)
    is_purchasable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["menu_item__name", "units_per_package", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_tenant_product_package_barcode",
            ),
            models.UniqueConstraint(
                fields=["tenant", "sku_alias"],
                condition=~models.Q(sku_alias=""),
                name="uniq_tenant_product_package_sku_alias",
            ),
            models.UniqueConstraint(
                fields=["menu_item", "name"],
                name="uniq_product_package_name_per_item",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Package and product must belong to the same business."})
        if self.units_per_package and self.units_per_package <= 0:
            raise ValidationError({"units_per_package": "Package quantity must be greater than zero."})

    def __str__(self) -> str:
        return f"{self.menu_item.name} · {self.name}"


class MenuItemOutlet(models.Model):
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="outlet_links",
    )
    outlet = models.ForeignKey(
        "tenants.Outlet",
        on_delete=models.CASCADE,
        related_name="menu_item_links",
    )
    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        unique_together = [["menu_item", "outlet"]]


class BarcodeMode(models.TextChoices):
    SCAN = "scan", "Scanned barcode"
    PLU = "plu", "PLU code"


class WeightedPricingMode(models.TextChoices):
    UNIT = "unit", "Unit priced"
    WEIGHTED = "weighted", "Weighted at checkout"


class SupermarketSkuProfile(TimeStampedModel):
    """Retail metadata for supermarket/grocery checkout flows."""

    menu_item = models.OneToOneField(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="supermarket_profile",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="supermarket_skus",
    )
    department = models.CharField(max_length=64, blank=True)
    barcode_mode = models.CharField(
        max_length=16,
        choices=BarcodeMode.choices,
        default=BarcodeMode.SCAN,
    )
    plu_code = models.CharField(max_length=16, blank=True)
    scale_prefix = models.CharField(max_length=2, blank=True, help_text="Configured local variable-weight EAN-13 prefix 20–29.")
    scale_item_code = models.CharField(max_length=5, blank=True, help_text="Five digits identifying this weighed product within the local label format.")
    weighted_pricing_mode = models.CharField(
        max_length=16,
        choices=WeightedPricingMode.choices,
        default=WeightedPricingMode.UNIT,
    )
    allow_fractional_quantity = models.BooleanField(default=False)
    sell_by_unit = models.BooleanField(
        default=True,
        help_text="When false and weighted mode is active, checkout expects measured quantity.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tenant__name", "menu_item__name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "plu_code"], condition=~models.Q(plu_code=""), name="uniq_nonblank_supermarket_plu"),
            models.UniqueConstraint(fields=["tenant", "scale_prefix", "scale_item_code"], condition=~models.Q(scale_prefix=""), name="uniq_tenant_scale_weight_code"),
        ]

    def __str__(self) -> str:
        return f"{self.menu_item.name} supermarket profile"


class MenuItemRecipeLine(TimeStampedModel):
    """BOM: ingredient quantities per one sellable unit of the parent menu item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="recipe_lines",
    )
    ingredient_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="used_in_recipes",
    )
    quantity_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Ingredient quantity consumed per 1 unit of parent sold.",
    )

    class Meta:
        ordering = ["parent_item", "ingredient_item__name"]
        unique_together = [["parent_item", "ingredient_item"]]

    def __str__(self) -> str:
        return f"{self.parent_item.name}: {self.ingredient_item.name} x {self.quantity_per_unit}"


class RetailAssemblyComponent(TimeStampedModel):
    """Retail build/unbuild BOM component for a tracked finished product."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="retail_assembly_components",
    )
    parent_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="assembly_components",
    )
    component_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name="used_in_retail_assemblies",
    )
    quantity_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Base stock units of this component required to build one finished unit.",
    )

    class Meta:
        ordering = ["parent_item", "component_item__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent_item", "component_item"],
                name="uniq_retail_assembly_component",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.parent_item_id == self.component_item_id:
            raise ValidationError({"component_item": "A product cannot be a component of itself."})
        if self.parent_item_id and self.tenant_id and self.parent_item.tenant_id != self.tenant_id:
            raise ValidationError({"parent_item": "Finished product must belong to this business."})
        if self.component_item_id and self.tenant_id and self.component_item.tenant_id != self.tenant_id:
            raise ValidationError({"component_item": "Component must belong to this business."})

    def __str__(self) -> str:
        return f"{self.parent_item.name}: {self.component_item.name} x {self.quantity_per_unit}"


class RetailProductGroup(TimeStampedModel):
    """Non-stock quick-sale group that expands into ordinary component SKUs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="retail_product_groups",
    )
    name = models.CharField(max_length=128)
    code = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional cashier lookup code for this group. It does not replace component barcodes.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_retail_group_name_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "code"],
                condition=~models.Q(code=""),
                name="uniq_retail_group_code_tenant",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "tenant",
                name="uniq_retail_group_name_tenant_ci",
            ),
            models.UniqueConstraint(
                Lower("code"),
                "tenant",
                condition=~models.Q(code=""),
                name="uniq_retail_group_code_tenant_ci",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class RetailProductGroupLine(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="retail_product_group_lines",
    )
    group = models.ForeignKey(
        RetailProductGroup,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name="retail_group_lines",
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "menu_item__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "menu_item"],
                name="uniq_retail_group_component",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.group_id and self.tenant_id and self.group.tenant_id != self.tenant_id:
            raise ValidationError({"group": "Group must belong to this business."})
        if self.menu_item_id and self.tenant_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Group components must belong to the same business."})
        if self.group_id and self.menu_item_id and self.group.tenant_id != self.menu_item.tenant_id:
            raise ValidationError({"menu_item": "Group components must belong to the same business."})


class ServiceOffering(TimeStampedModel):
    """Tenant-defined non-menu services sellable on orders (spa, rides, activities, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="service_offerings",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="If set, tax is computed on service subtotal (exclusive).",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional expected duration for scheduling visibility.",
    )
    kds_station = models.CharField(
        max_length=32,
        blank=True,
        default="service",
        help_text="Prep/ops station tag (e.g. service, sauna, spa, bar).",
    )
    is_active = models.BooleanField(default=True)
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        related_name="service_offerings",
        blank=True,
        help_text="If empty, service is available at every outlet of the tenant.",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return self.name

    def available_at_outlet(self, outlet_id: uuid.UUID) -> bool:
        if not self.outlets.exists():
            return True
        return self.outlets.filter(id=outlet_id).exists()


class ServiceOfferingOption(TimeStampedModel):
    """Service tier/package row for a base offering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_offering = models.ForeignKey(
        ServiceOffering,
        on_delete=models.CASCADE,
        related_name="options",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional duration override for this service package.",
    )
    kds_station = models.CharField(
        max_length=32,
        blank=True,
        help_text="Optional station override; blank uses parent service station.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        unique_together = [["service_offering", "name"]]

    def __str__(self) -> str:
        return f"{self.service_offering.name} · {self.name}"

    def effective_station(self) -> str:
        return (self.kds_station or self.service_offering.kds_station or "service")[:32]


class Promotion(TimeStampedModel):
    class OfferType(models.TextChoices):
        STANDARD = "standard", "Amount / percent off"
        BUY_X_GET_Y = "buy_x_get_y", "Buy X get Y free"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="promotions",
    )
    name = models.CharField(max_length=128)
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name="promotions",
        null=True,
        blank=True,
    )
    product_family = models.ForeignKey(
        ProductFamily,
        on_delete=models.PROTECT,
        related_name="promotions",
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.PROTECT,
        related_name="promotions",
        null=True,
        blank=True,
    )
    brand = models.CharField(
        max_length=128,
        blank=True,
        help_text="Optional case-insensitive brand target. Leave all targets blank for a whole-basket promotion.",
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    min_order_subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    min_target_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Optional minimum qualifying quantity for the targeted product/family/category/brand, or total basket quantity for whole-basket offers.",
    )
    coupon_code = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional coupon code. Coded offers are entered explicitly at checkout and are hidden from the normal offer list.",
    )
    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Optional total number of fully paid orders that may use this offer.",
    )
    max_redemptions_per_customer = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Optional paid-order limit per identified customer. Anonymous sales are not counted against this customer-specific limit.",
    )
    buy_quantity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="For Buy X Get Y, number of qualifying units the customer buys.",
    )
    get_quantity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="For Buy X Get Y, number of additional qualifying units discounted to free.",
    )
    max_uses_per_order = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Optional maximum number of Buy X Get Y sets discounted on one order.",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    outlets = models.ManyToManyField(
        "tenants.Outlet",
        blank=True,
        related_name="promotions",
        help_text="Empty = valid at all outlets.",
    )

    class Meta:
        ordering = ["-starts_at", "name"]
        constraints = [
            models.UniqueConstraint(
                Lower("coupon_code"),
                "tenant",
                condition=~models.Q(coupon_code=""),
                name="uniq_promotion_coupon_code_ci_tenant",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            offer_type="standard",
                            discount_percent__isnull=False,
                            discount_amount__isnull=True,
                            buy_quantity__isnull=True,
                            get_quantity__isnull=True,
                            max_uses_per_order__isnull=True,
                        )
                        | models.Q(
                            offer_type="standard",
                            discount_percent__isnull=True,
                            discount_amount__isnull=False,
                            buy_quantity__isnull=True,
                            get_quantity__isnull=True,
                            max_uses_per_order__isnull=True,
                        )
                        | models.Q(
                            offer_type="buy_x_get_y",
                            discount_percent__isnull=True,
                            discount_amount__isnull=True,
                            buy_quantity__isnull=False,
                            get_quantity__isnull=False,
                        )
                    )
                ),
                name="promotion_offer_type_fields_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(offer_type="standard")
                    | models.Q(menu_item__isnull=False)
                    | models.Q(product_family__isnull=False)
                    | models.Q(category__isnull=False)
                    | ~models.Q(brand="")
                ),
                name="promotion_bogo_requires_target",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(max_redemptions__isnull=True)
                    | models.Q(max_redemptions_per_customer__isnull=True)
                    | models.Q(max_redemptions_per_customer__lte=models.F("max_redemptions"))
                ),
                name="promotion_customer_limit_within_total",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(menu_item__isnull=True, product_family__isnull=True, category__isnull=True)
                    | models.Q(menu_item__isnull=False, product_family__isnull=True, category__isnull=True, brand="")
                    | models.Q(menu_item__isnull=True, product_family__isnull=False, category__isnull=True, brand="")
                    | models.Q(menu_item__isnull=True, product_family__isnull=True, category__isnull=False, brand="")
                ),
                name="promotion_at_most_one_structured_target",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.menu_item_id and self.menu_item.tenant_id != self.tenant_id:
            raise ValidationError({"menu_item": "Promotion product must belong to this business."})
        if self.product_family_id and self.product_family.tenant_id != self.tenant_id:
            raise ValidationError({"product_family": "Promotion family must belong to this business."})
        if self.category_id and self.category.tenant_id != self.tenant_id:
            raise ValidationError({"category": "Promotion category must belong to this business."})
        targets = (
            int(bool(self.menu_item_id))
            + int(bool(self.product_family_id))
            + int(bool(self.category_id))
            + int(bool((self.brand or "").strip()))
        )
        if targets > 1:
            raise ValidationError("Choose only one promotion target: product, family, brand, or category.")
        self.brand = (self.brand or "").strip()
        self.coupon_code = (self.coupon_code or "").strip()
        if self.offer_type == self.OfferType.BUY_X_GET_Y:
            if targets == 0:
                raise ValidationError("Buy X Get Y requires one product, family, category, or brand target.")
            if self.discount_percent is not None or self.discount_amount is not None:
                raise ValidationError("Buy X Get Y uses buy/get quantities instead of amount or percent discount.")
            if not self.buy_quantity or not self.get_quantity:
                raise ValidationError("Buy X Get Y requires both buy quantity and get quantity.")
        else:
            if (self.discount_percent is None) == (self.discount_amount is None):
                raise ValidationError("Standard offers require exactly one amount or percent discount.")
            if (
                self.buy_quantity is not None
                or self.get_quantity is not None
                or self.max_uses_per_order is not None
            ):
                raise ValidationError("Buy/get quantities and uses-per-order are only valid for Buy X Get Y offers.")
        if (
            self.max_redemptions is not None
            and self.max_redemptions_per_customer is not None
            and self.max_redemptions_per_customer > self.max_redemptions
        ):
            raise ValidationError({
                "max_redemptions_per_customer": "Per-customer limit cannot exceed the total redemption limit."
            })

    @property
    def target_label(self):
        if self.menu_item_id:
            return self.menu_item.name
        if self.product_family_id:
            return f"Family · {self.product_family.name}"
        if self.category_id:
            return f"Category · {self.category.name}"
        if self.brand:
            return f"Brand · {self.brand}"
        return "Whole basket"

    def __str__(self) -> str:
        return self.name


class ModifierGroup(TimeStampedModel):
    """Optional add-ons for menu items (size, toppings, prep)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="modifier_groups",
    )
    name = models.CharField(max_length=128)
    min_selections = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minimum options the guest must pick from this group (0 = optional).",
    )
    max_selections = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Maximum picks; blank = no limit.",
    )

    class Meta:
        ordering = ["name"]
        unique_together = [["tenant", "name"]]

    def __str__(self) -> str:
        return self.name


class ModifierOption(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name="options",
    )
    name = models.CharField(max_length=128)
    price_delta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Added to each unit's price before tax (per sold unit).",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["group", "sort_order", "name"]
        unique_together = [["group", "name"]]

    def __str__(self) -> str:
        return f"{self.group.name}: {self.name}"


class MenuItemModifierGroup(models.Model):
    """Attach a modifier group to a menu item (many-to-many with ordering)."""

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="modifier_group_links",
    )
    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name="menu_item_links",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["menu_item", "sort_order", "group__name"]
        unique_together = [["menu_item", "group"]]

    def __str__(self) -> str:
        return f"{self.menu_item} ← {self.group}"
