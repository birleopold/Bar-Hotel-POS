from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0022_serialized_return_link_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventoryserialunit",
            name="warranty_started_at",
            field=models.DateField(blank=True, null=True),
        ),
    ]
