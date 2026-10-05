import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel


class MenuCategory(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="menu_categories",
    )
    name = models.CharField(max_length=128)
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
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_featured = models.BooleanField(
        default=False,
        help_text="Include this item in rotating Service TV menu highlights.",
    )
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
    track_inventory = models.BooleanField(
        default=False,
        help_text="When true, outlet stock is reduced when the order is paid.",
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

    def __str__(self) -> str:
        return self.name

    def unit_price_for_outlet(self, outlet_id: uuid.UUID) -> Decimal:
        link = self.outlet_links.filter(outlet_id=outlet_id).first()
        if link and link.price_override is not None:
            return link.price_override
        return self.unit_price


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
        unique_together = [["tenant", "plu_code"]]

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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="promotions",
    )
    name = models.CharField(max_length=128)
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
