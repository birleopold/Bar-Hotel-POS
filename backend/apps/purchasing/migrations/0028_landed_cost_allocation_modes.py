from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchasing", "0027_purchaseorder_request_context"),
    ]

    operations = [
        migrations.AlterField(
            model_name="purchasereceipt",
            name="landed_cost_allocation",
            field=models.CharField(
                choices=[
                    ("exclude", "Do not add to inventory cost"),
                    ("by_cost", "Distribute by received supplier cost"),
                    ("by_quantity", "Distribute by received quantity"),
                    ("manual", "Manual per-line allocation"),
                ],
                default="exclude",
                max_length=16,
            ),
        ),
    ]
