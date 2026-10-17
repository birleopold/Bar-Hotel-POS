from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_menuitem_units_per_carton")]
    operations = [
        migrations.AddField(
            model_name="supermarketskuprofile", name="scale_prefix",
            field=models.CharField(blank=True, max_length=2, help_text="Configured local variable-weight EAN-13 prefix 20–29."),
        ),
        migrations.AddField(
            model_name="supermarketskuprofile", name="scale_item_code",
            field=models.CharField(blank=True, max_length=5, help_text="Five digits identifying this weighed product within the local label format."),
        ),
        migrations.AlterUniqueTogether(
            name="supermarketskuprofile", unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="supermarketskuprofile",
            constraint=models.UniqueConstraint(
                fields=("tenant", "plu_code"), condition=~models.Q(plu_code=""), name="uniq_nonblank_supermarket_plu",
            ),
        ),
        migrations.AddConstraint(
            model_name="supermarketskuprofile",
            constraint=models.UniqueConstraint(
                fields=("tenant", "scale_prefix", "scale_item_code"),
                condition=~models.Q(scale_prefix=""), name="uniq_tenant_scale_weight_code",
            ),
        ),
    ]
