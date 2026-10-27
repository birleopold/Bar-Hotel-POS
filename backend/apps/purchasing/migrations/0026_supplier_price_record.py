import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def enable_supplier_price_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "purchasing_supplierpricerecord"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}" FOR ALL USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            )'''
        )


def disable_supplier_price_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "purchasing_supplierpricerecord"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0025_supplier_product_ordering_terms"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupplierPriceRecord",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("unit_cost", models.DecimalField(
                    decimal_places=2, max_digits=12,
                    validators=[MinValueValidator(Decimal("0"))],
                )),
                ("minimum_quantity", models.DecimalField(
                    decimal_places=3, default=Decimal("0.001"),
                    help_text="Minimum base-stock quantity required for this price.",
                    max_digits=14,
                    validators=[MinValueValidator(Decimal("0.001"))],
                )),
                ("valid_from", models.DateField(blank=True, null=True)),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("source_reference", models.CharField(
                    blank=True,
                    help_text="Supplier contract, price-list or quotation reference.",
                    max_length=128,
                )),
                ("note", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("menu_item", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="supplier_price_records",
                    to="catalog.menuitem",
                )),
                ("product_package", models.ForeignKey(
                    blank=True,
                    help_text="Optional purchasing package this supplier price applies to.",
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="supplier_price_records",
                    to="catalog.productpackage",
                )),
                ("supplier", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="price_records",
                    to="purchasing.supplier",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="supplier_price_records",
                    to="tenants.tenant",
                )),
            ],
            options={
                "ordering": [
                    "supplier__name", "menu_item__name",
                    "-minimum_quantity", "-valid_from", "-created_at",
                ]
            },
        ),
        migrations.RunPython(enable_supplier_price_rls, disable_supplier_price_rls),
    ]
