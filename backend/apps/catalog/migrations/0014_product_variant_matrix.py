from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0013_product_family_and_packages"),
    ]

    operations = [
        migrations.AddField(
            model_name="productfamily",
            name="variant_schema",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Ordered variant dimensions and allowed values for matrix-generated sellable SKUs.",
            ),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="variant_key",
            field=models.CharField(
                blank=True,
                help_text="Canonical key for a matrix-generated variant; blank for ordinary/manual products.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="variant_values",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Variant dimension snapshot such as Colour=Black and Size=M.",
            ),
        ),
        migrations.AddConstraint(
            model_name="menuitem",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("variant_key", "")),
                fields=("product_family", "variant_key"),
                name="uniq_product_family_variant_key",
            ),
        ),
    ]
