import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_menuitem_product_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductFamily",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="product_families", to="catalog.menucategory")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_families", to="tenants.tenant")),
            ],
            options={
                "ordering": ["category__sort_order", "category__name", "name"],
                "unique_together": {("tenant", "name")},
            },
        ),
        migrations.AddField(
            model_name="menuitem",
            name="product_family",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional parent product used to group concrete size/colour/style variants.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="variants",
                to="catalog.productfamily",
            ),
        ),
        migrations.CreateModel(
            name="ProductPackage",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text="For example 6-pack, case of 24, or carton.", max_length=96)),
                ("units_per_package", models.DecimalField(decimal_places=3, help_text="Number of base stock units represented by one package.", max_digits=14, validators=[MinValueValidator(Decimal("0.001"))])),
                ("barcode", models.CharField(blank=True, db_index=True, help_text="Optional barcode that identifies this package size.", max_length=64)),
                ("sku_alias", models.CharField(blank=True, help_text="Optional supplier/internal code for this package.", max_length=64)),
                ("sell_price", models.DecimalField(blank=True, decimal_places=2, help_text="Optional package selling price. Blank means base unit price × package quantity.", max_digits=12, null=True, validators=[MinValueValidator(Decimal("0"))])),
                ("is_sellable", models.BooleanField(default=True)),
                ("is_purchasable", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="packages", to="catalog.menuitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_packages", to="tenants.tenant")),
            ],
            options={
                "ordering": ["menu_item__name", "units_per_package", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="productpackage",
            constraint=models.UniqueConstraint(condition=~models.Q(("barcode", "")), fields=("tenant", "barcode"), name="uniq_tenant_product_package_barcode"),
        ),
        migrations.AddConstraint(
            model_name="productpackage",
            constraint=models.UniqueConstraint(condition=~models.Q(("sku_alias", "")), fields=("tenant", "sku_alias"), name="uniq_tenant_product_package_sku_alias"),
        ),
        migrations.AddConstraint(
            model_name="productpackage",
            constraint=models.UniqueConstraint(fields=("menu_item", "name"), name="uniq_product_package_name_per_item"),
        ),
    ]
