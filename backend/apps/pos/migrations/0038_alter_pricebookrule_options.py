from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0037_price_book_brand_ci_unique"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pricebookrule",
            options={"ordering": ["price_book", "-minimum_quantity", "pk"]},
        ),
    ]
