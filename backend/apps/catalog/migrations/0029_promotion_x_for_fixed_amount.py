from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0028_promotion_bogo_constraints"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="promotion",
            name="promotion_offer_type_fields_valid",
        ),
        migrations.RemoveConstraint(
            model_name="promotion",
            name="promotion_bogo_requires_target",
        ),
        migrations.AddField(
            model_name="promotion",
            name="fixed_bundle_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                help_text="For X for fixed amount, total selling price for each qualifying set.",
                validators=[django.core.validators.MinValueValidator(0.01)],
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="fixed_quantity",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="For X for fixed amount, number of qualifying whole units in each deal set.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AlterField(
            model_name="promotion",
            name="offer_type",
            field=models.CharField(
                choices=[
                    ("standard", "Amount / percent off"),
                    ("buy_x_get_y", "Buy X get Y free"),
                    ("x_for_fixed_amount", "X for fixed amount"),
                ],
                default="standard",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="promotion",
            name="max_uses_per_order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="Optional maximum number of quantity-deal sets discounted on one order.",
                validators=[django.core.validators.MinValueValidator(1)],
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
                        fixed_quantity__isnull=True,
                        fixed_bundle_amount__isnull=True,
                        max_uses_per_order__isnull=True,
                    )
                    | models.Q(
                        offer_type="standard",
                        discount_percent__isnull=True,
                        discount_amount__isnull=False,
                        buy_quantity__isnull=True,
                        get_quantity__isnull=True,
                        fixed_quantity__isnull=True,
                        fixed_bundle_amount__isnull=True,
                        max_uses_per_order__isnull=True,
                    )
                    | models.Q(
                        offer_type="buy_x_get_y",
                        discount_percent__isnull=True,
                        discount_amount__isnull=True,
                        buy_quantity__isnull=False,
                        get_quantity__isnull=False,
                        fixed_quantity__isnull=True,
                        fixed_bundle_amount__isnull=True,
                    )
                    | models.Q(
                        offer_type="x_for_fixed_amount",
                        discount_percent__isnull=True,
                        discount_amount__isnull=True,
                        buy_quantity__isnull=True,
                        get_quantity__isnull=True,
                        fixed_quantity__isnull=False,
                        fixed_bundle_amount__isnull=False,
                    )
                ),
                name="promotion_offer_type_fields_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(offer_type="standard")
                    | models.Q(menu_item__isnull=False)
                    | models.Q(product_family__isnull=False)
                    | models.Q(category__isnull=False)
                    | ~models.Q(brand="")
                ),
                name="promotion_quantity_deal_requires_target",
            ),
        ),
    ]
