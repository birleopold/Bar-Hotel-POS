from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("catalog", "0009_menudisplay_fields")]
    operations = [
        migrations.AddField(
            model_name="menuitem", name="units_per_carton",
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(10000),
                ],
                help_text="Pieces in one supplier carton; 1 means cartons are not configured.",
            ),
        ),
    ]
