from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0022_supplier_product_planning"),
        ("accounts", "0006_passwordrecoveryrequest"),
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
                default="approved",
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
    ]
