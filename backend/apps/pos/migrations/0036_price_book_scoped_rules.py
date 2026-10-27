from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0035_customer_price_books"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pricebookrule",
            name="menu_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="price_book_rules",
                to="catalog.menuitem",
            ),
        ),
        migrations.AddField(
            model_name="pricebookrule",
            name="product_family",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="price_book_rules",
                to="catalog.productfamily",
            ),
        ),
        migrations.AddField(
            model_name="pricebookrule",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="price_book_rules",
                to="catalog.menucategory",
            ),
        ),
        migrations.AddField(
            model_name="pricebookrule",
            name="brand",
            field=models.CharField(
                blank=True,
                help_text="Case-insensitive brand target. Leave blank unless this is a brand-wide rule.",
                max_length=128,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="pricebookrule",
            name="uniq_price_book_item_tier",
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("menu_item__isnull", False)),
                fields=("price_book", "menu_item", "minimum_quantity"),
                name="uniq_price_book_item_tier",
            ),
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("product_family__isnull", False)),
                fields=("price_book", "product_family", "minimum_quantity"),
                name="uniq_price_book_family_tier",
            ),
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("category__isnull", False)),
                fields=("price_book", "category", "minimum_quantity"),
                name="uniq_price_book_category_tier",
            ),
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("brand", "")),
                fields=("price_book", "brand", "minimum_quantity"),
                name="uniq_price_book_brand_tier",
            ),
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("brand", ""), ("category__isnull", True), ("menu_item__isnull", False), ("product_family__isnull", True))
                    | models.Q(("brand", ""), ("category__isnull", True), ("menu_item__isnull", True), ("product_family__isnull", False))
                    | models.Q(("brand", ""), ("category__isnull", False), ("menu_item__isnull", True), ("product_family__isnull", True))
                    | (models.Q(("category__isnull", True), ("menu_item__isnull", True), ("product_family__isnull", True)) & ~models.Q(("brand", "")))
                ),
                name="price_book_rule_exactly_one_target",
            ),
        ),
    ]
