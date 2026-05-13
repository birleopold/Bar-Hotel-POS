from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0011_tenantoutletmodulepolicy"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantsettings",
            name="hardware_barcode_scanner_enabled",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, scanner-first barcode/PLU controls appear in POS.",
            ),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="hardware_cash_drawer_enabled",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, cash-drawer specific hints/actions can be shown in POS.",
            ),
        ),
        migrations.AddField(
            model_name="tenantsettings",
            name="hardware_receipt_printer_enabled",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, receipt/bill print shortcuts appear in POS.",
            ),
        ),
    ]
