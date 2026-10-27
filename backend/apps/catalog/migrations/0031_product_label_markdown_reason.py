from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0030_promotion_bogo_reward_target"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productlabelqueueentry",
            name="reason",
            field=models.CharField(
                choices=[
                    ("new_product", "New product"),
                    ("price_change", "Price change"),
                    ("receiving", "Goods received"),
                    ("markdown", "Scheduled markdown"),
                    ("manual", "Manual request"),
                ],
                max_length=24,
            ),
        ),
    ]
