from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0033_tenantsettings_retail_min_margin"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="is_training",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Isolated training workspace. Training status is chosen at creation "
                    "and cannot be converted into or out of a live business."
                ),
            ),
        ),
    ]
