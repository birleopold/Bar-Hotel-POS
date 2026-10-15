import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0007_purchasereceiptline_inventory_batch")]

    operations = [
        migrations.CreateModel(
            name="SupplierInvoice",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=128)),
                ("invoice_date", models.DateField()),
                ("due_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("note", models.CharField(blank=True, max_length=512)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supplier_invoices", to="tenants.tenant")),
                ("purchase_order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="purchasing.purchaseorder")),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_invoices_recorded", to="accounts.user")),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant", "purchase_order", "reference"), name="uniq_supplier_invoice_reference_po"),
                    models.CheckConstraint(condition=models.Q(amount__gt=0), name="supplier_invoice_amount_positive"),
                ],
            },
        ),
    ]
