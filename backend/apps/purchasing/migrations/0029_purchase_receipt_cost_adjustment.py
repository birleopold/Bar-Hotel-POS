import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0028_landed_cost_allocation_modes"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseReceiptCostAdjustment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=128)),
                ("amount", models.DecimalField(decimal_places=2, help_text="Signed landed-cost change: positive additional cost, negative supplier/freight credit.", max_digits=14)),
                ("allocation_method", models.CharField(choices=[
                    ("exclude", "Do not add to inventory cost"),
                    ("by_cost", "Distribute by received supplier cost"),
                    ("by_quantity", "Distribute by received quantity"),
                    ("manual", "Manual per-line allocation"),
                ], max_length=16)),
                ("reason", models.CharField(max_length=512)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_receipt_cost_adjustments", to="accounts.user")),
                ("receipt", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cost_adjustments", to="purchasing.purchasereceipt")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchase_receipt_cost_adjustments", to="tenants.tenant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PurchaseReceiptCostAdjustmentLine",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, help_text="Signed landed-cost value applied to this receipt line.", max_digits=14)),
                ("adjustment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="purchasing.purchasereceiptcostadjustment")),
                ("receipt_line", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cost_adjustment_lines", to="purchasing.purchasereceiptline")),
            ],
            options={"ordering": ["adjustment", "receipt_line"]},
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptcostadjustment",
            constraint=models.UniqueConstraint(fields=("tenant", "receipt", "reference"), name="uniq_receipt_cost_adjustment_reference"),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptcostadjustment",
            constraint=models.CheckConstraint(condition=~models.Q(("amount", Decimal("0"))), name="receipt_cost_adjustment_nonzero"),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptcostadjustmentline",
            constraint=models.UniqueConstraint(fields=("adjustment", "receipt_line"), name="uniq_receipt_cost_adjustment_line"),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptcostadjustmentline",
            constraint=models.CheckConstraint(condition=~models.Q(("amount", Decimal("0"))), name="receipt_cost_adjustment_line_nonzero"),
        ),
    ]
