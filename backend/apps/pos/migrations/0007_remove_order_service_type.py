from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0006_order_service_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="service_type",
        ),
    ]
