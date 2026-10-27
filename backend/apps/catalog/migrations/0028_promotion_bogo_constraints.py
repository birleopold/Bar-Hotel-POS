from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0027_promotion_buy_x_get_y"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="promotion",
            name="promotion_offer_type_fields_valid",
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
                name="promotion_bogo_requires_target",
            ),
        ),
    ]
