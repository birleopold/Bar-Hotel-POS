from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0022_product_label_queue"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="productcustomfielddefinition",
            constraint=models.UniqueConstraint(
                Lower("key"),
                "tenant",
                name="uniq_product_custom_field_key_ci_tenant",
            ),
        ),
    ]
