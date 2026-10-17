import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0024_hardware_check_rls"),
        ("catalog", "0011_scale_label_optin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="WholesalePriceRule",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("minimum_quantity", models.DecimalField(max_digits=10, decimal_places=3)),
                ("unit_price", models.DecimalField(max_digits=12, decimal_places=2)),
                ("starts_at", models.DateTimeField(null=True, blank=True)),
                ("ends_at", models.DateTimeField(null=True, blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(to="tenants.tenant", related_name="wholesale_price_rules", on_delete=django.db.models.deletion.CASCADE)),
                ("outlet", models.ForeignKey(to="tenants.outlet", related_name="wholesale_price_rules", on_delete=django.db.models.deletion.PROTECT)),
                ("menu_item", models.ForeignKey(to="catalog.menuitem", related_name="wholesale_price_rules", on_delete=django.db.models.deletion.PROTECT)),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL)),
            ],
            options={"ordering": ["outlet", "menu_item", "-minimum_quantity"]},
        ),
        migrations.AddConstraint(model_name="wholesalepricerule", constraint=models.UniqueConstraint(fields=["outlet","menu_item","minimum_quantity"], name="uniq_wholesale_tier_per_outlet")),
        migrations.AddConstraint(model_name="wholesalepricerule", constraint=models.CheckConstraint(condition=models.Q(minimum_quantity__gt=0), name="wholesale_tier_qty_positive")),
        migrations.AddConstraint(model_name="wholesalepricerule", constraint=models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="wholesale_tier_price_nonnegative")),
    ]
