import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0010_stock_count_review"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="StockTransferReceipt", fields=[
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("transfer_batch", models.UUIDField(unique=True)),
            ("dispatched_quantity", models.DecimalField(max_digits=14, decimal_places=3)),
            ("received_quantity", models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)),
            ("status", models.CharField(max_length=16, default="awaiting", choices=[
                ("awaiting", "Awaiting check"), ("matched", "Matched"), ("disputed", "Discrepancy"),
            ])),
            ("checked_at", models.DateTimeField(null=True, blank=True)),
            ("discrepancy_note", models.CharField(max_length=512, blank=True)),
            ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="transfer_receipts")),
            ("from_outlet", models.ForeignKey(to="tenants.outlet", on_delete=django.db.models.deletion.PROTECT, related_name="sent_transfer_receipts")),
            ("to_outlet", models.ForeignKey(to="tenants.outlet", on_delete=django.db.models.deletion.PROTECT, related_name="received_transfer_receipts")),
            ("menu_item", models.ForeignKey(to="catalog.menuitem", on_delete=django.db.models.deletion.PROTECT, related_name="transfer_receipts")),
            ("dispatched_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transfer_dispatches")),
            ("checked_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transfer_checks")),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(model_name="stocktransferreceipt",constraint=models.CheckConstraint(condition=models.Q(dispatched_quantity__gt=0), name="transfer_receipt_dispatched_positive")),
        migrations.AddConstraint(model_name="stocktransferreceipt",constraint=models.CheckConstraint(condition=models.Q(received_quantity__gte=0) | models.Q(received_quantity__isnull=True), name="transfer_receipt_received_nonnegative")),
    ]
