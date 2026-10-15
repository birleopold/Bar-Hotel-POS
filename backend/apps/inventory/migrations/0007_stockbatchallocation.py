import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0006_inventorybatch_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockBatchAllocation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_batch_allocations", to="tenants.tenant")),
                ("stock_movement", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="batch_allocations", to="inventory.stockmovement")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movement_allocations", to="inventory.inventorybatch")),
            ],
            options={
                "ordering": ["created_at"],
                "constraints": [
                    models.UniqueConstraint(fields=("stock_movement", "batch"), name="uniq_stock_movement_batch_link"),
                    models.CheckConstraint(condition=models.Q(quantity__gt=0), name="stock_batch_allocation_positive"),
                ],
            },
        ),
    ]
