from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0018_retail_product_groups"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="retailproductgroup",
            constraint=models.UniqueConstraint(
                Lower("name"),
                "tenant",
                name="uniq_retail_group_name_tenant_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="retailproductgroup",
            constraint=models.UniqueConstraint(
                Lower("code"),
                "tenant",
                condition=~models.Q(("code", "")),
                name="uniq_retail_group_code_tenant_ci",
            ),
        ),
    ]
