import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0021_merchandise_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductLabelQueueEntry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.CharField(choices=[("new_product", "New product"), ("price_change", "Price change"), ("receiving", "Goods received"), ("manual", "Manual request")], max_length=24)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("printed", "Printed"), ("dismissed", "Dismissed")], default="pending", max_length=16)),
                ("price_snapshot", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, validators=[MinValueValidator(Decimal("0"))])),
                ("note", models.CharField(blank=True, max_length=255)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="product_label_completions", to="accounts.user")),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="label_queue_entries", to="catalog.menuitem")),
                ("outlet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_label_queue_entries", to="tenants.outlet")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="product_label_requests", to="accounts.user")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_label_queue_entries", to="tenants.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="productlabelqueueentry",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "pending")), fields=("outlet", "menu_item", "reason"), name="uniq_pending_label_reason_item_outlet"),
        ),
    ]
