from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0004_alter_stockmovement_reason"),
        ("tenants", "0001_initial"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="InventoryBatch",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("batch_code", models.CharField(max_length=128)),
                ("received_at", models.DateField()),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("received_quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                ("remaining_quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                ("quarantined", models.BooleanField(default=False)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_batches", to="catalog.menuitem")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_batches", to="tenants.outlet")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_batches", to="tenants.tenant")),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("outlet", "menu_item", "batch_code"), name="uniq_inventory_batch_per_item_outlet"),
                models.CheckConstraint(condition=models.Q(("received_quantity__gte", 0)), name="inventory_batch_received_nonnegative"),
                models.CheckConstraint(condition=models.Q(("remaining_quantity__gte", 0)), name="inventory_batch_remaining_nonnegative"),
            ]},
        ),
    ]
