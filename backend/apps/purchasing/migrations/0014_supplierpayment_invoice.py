from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0013_suppliercreditnote_rls")]

    operations = [
        migrations.AddField(
            model_name="supplierpayment", name="invoice",
            field=models.ForeignKey(
                to="purchasing.supplierinvoice",
                on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="allocated_payments",
                help_text="Verified invoice; legacy PO payments are unallocated.",
            ),
        ),
    ]
