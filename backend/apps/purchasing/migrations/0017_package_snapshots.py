from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0014_product_variant_matrix"),
        ("purchasing", "0016_supplier_invoice_match_return_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorderline",
            name="product_package",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional package selected when this PO line was created.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="purchase_order_lines",
                to="catalog.productpackage",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="package_name_snapshot",
            field=models.CharField(blank=True, max_length=96),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="package_units_snapshot",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Base stock units per selected package at the time the PO was created.",
                max_digits=14,
                null=True,
                validators=[MinValueValidator(Decimal("0.001"))],
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="package_quantity_ordered",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="purchasereceiptline",
            name="packages_received",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
