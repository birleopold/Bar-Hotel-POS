import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0014_supplierpayment_invoice"),
        ("inventory", "0014_merge_transfer_workflows"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="SupplierInvoiceLine", fields=[
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("quantity", models.DecimalField(max_digits=14, decimal_places=3)),
            ("unit_cost", models.DecimalField(max_digits=12, decimal_places=2)),
            ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
            ("invoice", models.ForeignKey(to="purchasing.supplierinvoice", on_delete=django.db.models.deletion.PROTECT, related_name="matched_lines")),
            ("purchase_order_line", models.ForeignKey(to="purchasing.purchaseorderline", on_delete=django.db.models.deletion.PROTECT, related_name="invoice_matches")),
        ]),
        migrations.AddConstraint(model_name="supplierinvoiceline", constraint=models.UniqueConstraint(fields=("invoice", "purchase_order_line"), name="uniq_supplier_invoice_line_po_line")),
        migrations.AddConstraint(model_name="supplierinvoiceline", constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="supplier_invoice_line_qty_positive")),
        migrations.AddConstraint(model_name="supplierinvoiceline", constraint=models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name="supplier_invoice_line_cost_nonnegative")),
        migrations.AddConstraint(model_name="supplierinvoiceline", constraint=models.CheckConstraint(condition=models.Q(amount__gte=0), name="supplier_invoice_line_amount_nonnegative")),
        migrations.CreateModel(name="SupplierReturn", fields=[
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("reference", models.CharField(max_length=128)),
            ("quantity", models.DecimalField(max_digits=14, decimal_places=3)),
            ("note", models.CharField(max_length=512)),
            ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="supplier_returns")),
            ("purchase_order", models.ForeignKey(to="purchasing.purchaseorder", on_delete=django.db.models.deletion.PROTECT, related_name="returns_to_supplier")),
            ("receipt_line", models.ForeignKey(to="purchasing.purchasereceiptline", on_delete=django.db.models.deletion.PROTECT, related_name="supplier_returns")),
            ("movement", models.OneToOneField(to="inventory.stockmovement", on_delete=django.db.models.deletion.PROTECT, related_name="supplier_return")),
            ("returned_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name="supplier_returns_processed")),
        ]),
        migrations.AddConstraint(model_name="supplierreturn", constraint=models.UniqueConstraint(fields=("purchase_order", "reference"), name="uniq_supplier_return_reference_po")),
        migrations.AddConstraint(model_name="supplierreturn", constraint=models.CheckConstraint(condition=models.Q(quantity__gt=0), name="supplier_return_quantity_positive")),
    ]
