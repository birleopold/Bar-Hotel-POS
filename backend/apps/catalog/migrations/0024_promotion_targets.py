from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0023_custom_field_key_ci"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="menu_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="promotions",
                to="catalog.menuitem",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="product_family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="promotions",
                to="catalog.productfamily",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="promotions",
                to="catalog.menucategory",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="brand",
            field=models.CharField(
                blank=True,
                help_text="Optional case-insensitive brand target. Leave all targets blank for a whole-basket promotion.",
                max_length=128,
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("category__isnull", True), ("menu_item__isnull", True), ("product_family__isnull", True))
                    | models.Q(("brand", ""), ("category__isnull", True), ("menu_item__isnull", False), ("product_family__isnull", True))
                    | models.Q(("brand", ""), ("category__isnull", True), ("menu_item__isnull", True), ("product_family__isnull", False))
                    | models.Q(("brand", ""), ("category__isnull", False), ("menu_item__isnull", True), ("product_family__isnull", True))
                ),
                name="promotion_at_most_one_structured_target",
            ),
        ),
    ]
