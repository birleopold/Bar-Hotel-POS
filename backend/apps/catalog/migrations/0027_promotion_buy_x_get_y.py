from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0026_promotion_redemption_limit_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="offer_type",
            field=models.CharField(
                choices=[("standard", "Amount / percent off"), ("buy_x_get_y", "Buy X get Y free")],
                default="standard",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="buy_quantity",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="For Buy X Get Y, number of qualifying units the customer buys.",
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="get_quantity",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="For Buy X Get Y, number of additional qualifying units discounted to free.",
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="max_uses_per_order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Optional maximum number of Buy X Get Y sets discounted on one order.",
                null=True,
                validators=[MinValueValidator(1)],
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        offer_type="standard",
                        discount_percent__isnull=False,
                        discount_amount__isnull=True,
                        buy_quantity__isnull=True,
                        get_quantity__isnull=True,
                    )
                    | models.Q(
                        offer_type="standard",
                        discount_percent__isnull=True,
                        discount_amount__isnull=False,
                        buy_quantity__isnull=True,
                        get_quantity__isnull=True,
                    )
                    | models.Q(
                        offer_type="buy_x_get_y",
                        discount_percent__isnull=True,
                        discount_amount__isnull=True,
                        buy_quantity__isnull=False,
                        get_quantity__isnull=False,
                    )
                ),
                name="promotion_offer_type_fields_valid",
            ),
        ),
    ]
