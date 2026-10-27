from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0048_device_command_tare_scale"),
    ]

    operations = [
        migrations.AddField(
            model_name="workstationhardwarecheck",
            name="evidence",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Structured non-sensitive diagnostic evidence; never raw barcode/payment data.",
            ),
        ),
    ]
