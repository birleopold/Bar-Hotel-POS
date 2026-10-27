from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0020_purchasereceiptline_cost_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereceipt",
            name="shipping_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Shipping/freight paid for this physical delivery.",
                max_digits=14,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="purchasereceipt",
            name="duty_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Import duty, clearing or similar landed cost for this delivery.",
                max_digits=14,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="purchasereceipt",
            name="landed_cost_allocation",
            field=models.CharField(
                choices=[
                    ("exclude", "Do not add to inventory cost"),
                    ("by_cost", "Distribute by received supplier cost"),
                ],
                default="exclude",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="purchasereceiptline",
            name="landed_unit_cost_snapshot",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Supplier cost plus this receipt line's allocated landed costs per base unit.",
                max_digits=14,
                null=True,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="purchasereceiptline",
            name="landed_cost_allocated",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Shipping/duty amount allocated to this receipt line.",
                max_digits=14,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
