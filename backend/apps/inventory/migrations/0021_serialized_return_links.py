import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0020_serialized_unit_rls"),
        ("pos", "0034_orderline_seat_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventorySerialReturnLink",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("disposition", models.CharField(choices=[("restocked", "Returned to saleable stock"), ("quarantined", "Returned but quarantined")], max_length=16)),
                ("return_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="serialized_unit_links", to="pos.supermarketlinereturn")),
                ("serial_unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_links", to="inventory.inventoryserialunit")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="serialized_return_links", to="tenants.tenant")),
            ],
        ),
        migrations.AddConstraint(
            model_name="inventoryserialreturnlink",
            constraint=models.UniqueConstraint(fields=("serial_unit", "return_record"), name="uniq_serial_unit_return_record"),
        ),
    ]
