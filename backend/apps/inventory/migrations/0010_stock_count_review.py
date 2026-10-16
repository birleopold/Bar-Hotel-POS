from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0009_alter_stockbatchallocation_quantity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockcountsession", name="status",
            field=models.CharField(max_length=16, default="draft", choices=[
                ("draft", "Draft"), ("review", "Awaiting approval"),
                ("completed", "Completed"), ("cancelled", "Cancelled"),
            ]),
        ),
        migrations.AddField(
            model_name="stockcountsession", name="submitted_by",
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL, related_name="submitted_stock_counts"),
        ),
        migrations.AddField(model_name="stockcountsession", name="submitted_at",
            field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(
            model_name="stockcountsession", name="approved_by",
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL, related_name="approved_stock_counts"),
        ),
    ]
