from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0023_serial_warranty_started_at"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="inventoryserialunit",
            constraint=models.UniqueConstraint(
                Lower("serial_number"),
                "tenant",
                name="uniq_tenant_serial_number_ci",
            ),
        ),
    ]
