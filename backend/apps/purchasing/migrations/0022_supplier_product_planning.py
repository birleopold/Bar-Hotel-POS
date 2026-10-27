from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0021_purchase_receipt_landed_cost"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierproductcode",
            name="default_unit_cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Planning cost per base unit for new purchase orders from this supplier.",
                max_digits=12,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="supplierproductcode",
            name="is_preferred",
            field=models.BooleanField(
                default=False,
                help_text="Preferred supplier relationship for this product. Only one preferred supplier may exist per product.",
            ),
        ),
        migrations.AddConstraint(
            model_name="supplierproductcode",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_preferred=True),
                fields=("tenant", "menu_item"),
                name="uniq_preferred_supplier_per_product",
            ),
        ),
    ]
