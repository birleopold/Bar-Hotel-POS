import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0014_merge_transfer_workflows"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="StockShelfLocation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("aisle", models.CharField(blank=True, max_length=32)),
                ("shelf", models.CharField(blank=True, max_length=32)),
                ("bin_code", models.CharField(blank=True, max_length=32)),
                ("note", models.CharField(blank=True, max_length=160)),
                ("menu_item", models.ForeignKey(to="catalog.menuitem", on_delete=django.db.models.deletion.CASCADE, related_name="shelf_locations")),
                ("outlet", models.ForeignKey(to="tenants.outlet", on_delete=django.db.models.deletion.CASCADE, related_name="shelf_locations")),
                ("tenant", models.ForeignKey(to="tenants.tenant", on_delete=django.db.models.deletion.CASCADE, related_name="stock_shelf_locations")),
                ("updated_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="shelf_locations_updated")),
            ],
        ),
        migrations.AddConstraint(
            model_name="stockshelflocation",
            constraint=models.UniqueConstraint(fields=("outlet", "menu_item"), name="uniq_shelf_location_outlet_product"),
        ),
    ]
