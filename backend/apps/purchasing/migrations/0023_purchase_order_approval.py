from django.db import migrations, models
import django.db.models.deletion


def approve_existing_purchase_orders(apps, schema_editor):
    PurchaseOrder = apps.get_model("purchasing", "PurchaseOrder")
    PurchaseOrder.objects.all().update(approval_status="approved")


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0022_supplier_product_planning"),
        ("accounts", "__latest__"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending approval"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="review_note",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="purchase_orders_reviewed",
                to="accounts.user",
            ),
        ),
        migrations.RunPython(approve_existing_purchase_orders, migrations.RunPython.noop),
    ]
