from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0012_tenantsettings_hardware_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="business_lines",
            field=models.JSONField(
                default=list,
                help_text=(
                    "Business lines enabled for this workspace. "
                    "Keys: bar, lounge, restaurant, cafeteria, lodging, retail, supermarket, events."
                ),
            ),
        ),
    ]
