from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0016_serialized_inventory_settings"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="menuitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(serial_tracking=False)
                    | (
                        models.Q(track_inventory=True)
                        & models.Q(unit_of_measure="each")
                    )
                ),
                name="serialized_item_requires_piece_stock",
            ),
        ),
    ]
