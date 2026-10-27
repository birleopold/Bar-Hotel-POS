from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0015_retail_assembly_component"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="serial_tracking",
            field=models.BooleanField(
                default=False,
                help_text="Track every physical unit by serial number or IMEI. Requires piece-based inventory tracking.",
            ),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="serial_identifier_type",
            field=models.CharField(
                choices=[
                    ("serial", "Serial number"),
                    ("imei", "IMEI"),
                    ("custom", "Custom identifier"),
                ],
                default="serial",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="warranty_months",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Optional default warranty term for serialized units, in months.",
                null=True,
                validators=[MinValueValidator(1), MaxValueValidator(240)],
            ),
        ),
    ]
