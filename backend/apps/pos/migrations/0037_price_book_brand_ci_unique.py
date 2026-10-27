from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0036_price_book_scoped_rules"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="pricebookrule",
            name="uniq_price_book_brand_tier",
        ),
        migrations.AddConstraint(
            model_name="pricebookrule",
            constraint=models.UniqueConstraint(
                Lower("brand"),
                "price_book",
                "minimum_quantity",
                condition=~models.Q(("brand", "")),
                name="uniq_price_book_brand_tier",
            ),
        ),
    ]
