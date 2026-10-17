from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0010_alter_supplierinvoice_amount_and_more"),
        ("catalog", "0010_menuitem_units_per_carton"),
    ]
    operations = [
        migrations.AddField(
            model_name="purchaseorderline", name="units_per_carton_snapshot",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="purchasereceiptline", name="cartons_received",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
