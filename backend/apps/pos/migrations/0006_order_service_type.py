from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0005_supermarket_models_and_line_pricing"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_type",
            field=models.CharField(
                choices=[
                    ("mixed", "Mixed service"),
                    ("kitchen", "Kitchen / food"),
                    ("bar", "Bar / drinks"),
                ],
                default="mixed",
                max_length=16,
            ),
        ),
    ]
