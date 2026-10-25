from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pos", "0031_delivery_fulfillment_rls")]

    operations = [
        migrations.AddField(
            model_name="supermarketlinereturn",
            name="idempotency_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional tenant-scoped retry identity for a physical return.",
                max_length=128,
            ),
        ),
        migrations.AddConstraint(
            model_name="supermarketlinereturn",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("tenant", "idempotency_key"),
                name="uniq_supermarket_return_retry_key",
            ),
        ),
    ]
