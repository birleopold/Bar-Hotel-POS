import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "inventory_stocktransferrequest"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(
            f"""CREATE POLICY tenant_isolation ON "{table}"
            FOR ALL USING (
                tenant_id::text = current_setting('app.tenant_id', true)
            )"""
        )


def _disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "inventory_stocktransferrequest"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0027_retailassemblyrun_cost_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockTransferRequest",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("requested_quantity", models.DecimalField(decimal_places=3, max_digits=14, validators=[MinValueValidator(Decimal("0.001"))])),
                ("approved_quantity", models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True, validators=[MinValueValidator(Decimal("0.001"))])),
                ("needed_by", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending approval"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("dispatched", "Dispatched"),
                    ("cancelled", "Cancelled"),
                ], default="pending", max_length=16)),
                ("request_note", models.CharField(blank=True, max_length=512)),
                ("review_note", models.CharField(blank=True, max_length=512)),
                ("from_outlet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_stock_transfer_requests", to="tenants.outlet")),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_transfer_requests", to="catalog.menuitem")),
                ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_transfer_requests_created", to="accounts.user")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_transfer_requests_reviewed", to="accounts.user")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stock_transfer_requests", to="tenants.tenant")),
                ("to_outlet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_stock_transfer_requests", to="tenants.outlet")),
                ("transfer_receipt", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_request", to="inventory.stocktransferreceipt")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="stocktransferrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("requested_quantity__gt", 0)),
                name="transfer_request_quantity_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="stocktransferrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(("approved_quantity__gt", 0), ("approved_quantity__isnull", True), _connector="OR"),
                name="transfer_request_approved_quantity_positive",
            ),
        ),
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
