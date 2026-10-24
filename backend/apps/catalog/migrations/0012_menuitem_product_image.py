from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_scale_label_optin"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="product_image",
            field=models.ImageField(
                blank=True,
                help_text="Upload a JPEG, PNG, or WebP product photo (maximum 5 MB).",
                upload_to="products/%Y/%m/",
            ),
        ),
    ]
