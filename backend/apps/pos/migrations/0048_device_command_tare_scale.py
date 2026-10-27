from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0047_workstation_bridge_command_rls"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workstationdevicecommand",
            name="command_type",
            field=models.CharField(
                choices=[
                    ("ping", "Ping device"),
                    ("print_receipt", "Print receipt"),
                    ("print_kitchen", "Print kitchen ticket"),
                    ("open_drawer", "Open cash drawer"),
                    ("read_scale", "Read scale"),
                    ("tare_scale", "Tare scale"),
                ],
                max_length=24,
            ),
        ),
    ]
