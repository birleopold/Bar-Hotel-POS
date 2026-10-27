from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0029_promotion_x_for_fixed_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="reward_brand",
            field=models.CharField(
                blank=True,
                help_text="Optional case-insensitive Buy X Get Y reward brand.",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="reward_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reward_promotions",
                to="catalog.menucategory",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="reward_menu_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="Optional Buy X Get Y reward product. Leave reward targets blank to reward from the same qualifying pool.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reward_promotions",
                to="catalog.menuitem",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="reward_product_family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reward_promotions",
                to="catalog.productfamily",
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        reward_menu_item__isnull=True,
                        reward_product_family__isnull=True,
                        reward_category__isnull=True,
                    )
                    | models.Q(
                        reward_menu_item__isnull=False,
                        reward_product_family__isnull=True,
                        reward_category__isnull=True,
                        reward_brand="",
                    )
                    | models.Q(
                        reward_menu_item__isnull=True,
                        reward_product_family__isnull=False,
                        reward_category__isnull=True,
                        reward_brand="",
                    )
                    | models.Q(
                        reward_menu_item__isnull=True,
                        reward_product_family__isnull=True,
                        reward_category__isnull=False,
                        reward_brand="",
                    )
                ),
                name="promotion_at_most_one_reward_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(offer_type="buy_x_get_y")
                    | models.Q(
                        reward_menu_item__isnull=True,
                        reward_product_family__isnull=True,
                        reward_category__isnull=True,
                        reward_brand="",
                    )
                ),
                name="promotion_reward_target_bogo_only",
            ),
        ),
    ]
