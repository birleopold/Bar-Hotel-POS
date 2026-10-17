import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0011_carton_receiving_snapshots"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="SupplierCreditNote",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=128)),
                ("credit_date", models.DateField()),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
                ("reason", models.CharField(max_length=512)),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="supplier_credit_notes")),
                ("purchase_order", models.ForeignKey(to="purchasing.purchaseorder", on_delete=django.db.models.deletion.PROTECT, related_name="credits")),
                ("invoice", models.ForeignKey(to="purchasing.supplierinvoice", on_delete=django.db.models.deletion.PROTECT, related_name="credits")),
                ("recorded_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="supplier_credit_notes_recorded")),
            ], options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="suppliercreditnote",
            constraint=models.UniqueConstraint(
                fields=["tenant", "purchase_order", "reference"], name="uniq_supplier_credit_reference_po",
            ),
        ),
        migrations.AddConstraint(
            model_name="suppliercreditnote",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="supplier_credit_amount_positive",
            ),
        ),
    ]
