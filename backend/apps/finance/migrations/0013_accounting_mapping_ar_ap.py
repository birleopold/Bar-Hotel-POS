from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0012_accounting_bridge_rls"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountingmapping",
            name="kind",
            field=models.CharField(
                choices=[
                    ("revenue_default", "Revenue default"),
                    ("revenue_category", "Revenue category"),
                    ("returns", "Sales returns"),
                    ("tender", "Tender clearing"),
                    ("tax_liability", "Tax / VAT liability"),
                    ("accounts_receivable", "Accounts receivable"),
                    ("accounts_payable", "Accounts payable"),
                    ("inventory_default", "Inventory asset default"),
                    ("inventory_category", "Inventory asset category"),
                    ("cogs_default", "COGS default"),
                    ("cogs_category", "COGS category"),
                ],
                max_length=32,
            ),
        ),
    ]
