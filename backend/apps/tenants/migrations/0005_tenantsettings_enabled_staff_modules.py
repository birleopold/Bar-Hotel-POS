# Generated manually — tenant-configurable staff UI modules.

from django.db import migrations, models


def default_enabled_staff_modules():
    return [
        "pos",
        "kitchen",
        "promotions",
        "inventory",
        "purchasing",
        "lodging",
        "events",
        "workspace",
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0004_extend_postgres_row_level_security"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="enabled_staff_modules",
            field=models.JSONField(
                default=default_enabled_staff_modules,
                help_text=(
                    "Which staff areas this tenant uses (signup / plan). "
                    "Keys: pos, kitchen, promotions, inventory, purchasing, lodging, events, workspace."
                ),
            ),
        ),
    ]
