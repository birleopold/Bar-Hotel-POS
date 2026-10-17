from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0012_stocktransferreceipt_rls"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name="stocktransferreceipt", name="mode", field=models.CharField(
            max_length=12, default="instant", choices=[
                ("instant", "Legacy immediate"), ("staged", "Dispatch then receive"),
            ])),
        migrations.AddField(model_name="stocktransferreceipt", name="posted_quantity",
            field=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))),
        migrations.AddField(model_name="stocktransferreceipt", name="returned_quantity",
            field=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))),
        migrations.AddField(model_name="stocktransferreceipt", name="written_off_quantity",
            field=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))),
        migrations.AddField(model_name="stocktransferreceipt", name="resolution_action",
            field=models.CharField(max_length=24, blank=True)),
        migrations.AddField(model_name="stocktransferreceipt", name="resolution_note",
            field=models.CharField(max_length=512, blank=True)),
        migrations.AddField(model_name="stocktransferreceipt", name="resolved_at",
            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="stocktransferreceipt", name="resolved_by",
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True, related_name="resolved_stock_transfers")),
        migrations.AlterField(model_name="stocktransferreceipt", name="status",
            field=models.CharField(max_length=16, default="awaiting", choices=[
                ("awaiting", "Awaiting check"), ("in_transit", "In transit"),
                ("matched", "Matched"), ("disputed", "Discrepancy"), ("resolved", "Resolved"),
            ])),
        migrations.AddConstraint(model_name="stocktransferreceipt", constraint=models.CheckConstraint(
            condition=models.Q(posted_quantity__gte=0), name="transfer_posted_nonnegative")),
        migrations.AddConstraint(model_name="stocktransferreceipt", constraint=models.CheckConstraint(
            condition=models.Q(returned_quantity__gte=0), name="transfer_returned_nonnegative")),
        migrations.AddConstraint(model_name="stocktransferreceipt", constraint=models.CheckConstraint(
            condition=models.Q(written_off_quantity__gte=0), name="transfer_writtenoff_nonnegative")),
        migrations.AddConstraint(model_name="stocktransferreceipt", constraint=models.CheckConstraint(
            condition=models.Q(dispatched_quantity__gte=models.F("posted_quantity") + models.F("returned_quantity") + models.F("written_off_quantity")),
            name="transfer_total_not_exceeded")),
    ]
