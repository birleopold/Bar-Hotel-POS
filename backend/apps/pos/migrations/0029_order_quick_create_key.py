from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pos", "0028_retail_pickup_rls")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="quick_create_key",
            field=models.UUIDField(blank=True, null=True, help_text="Idempotency key for staff quick basket creation."),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=("tenant", "quick_create_key"), name="uniq_quick_basket_key_per_tenant"),
        ),
    ]
