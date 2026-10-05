from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_userinvite"), ("tenants", "0016_alter_outlet_outlet_type_and_more")]

    operations = [
        migrations.AddField(
            model_name="userinvite",
            name="sites",
            field=models.ManyToManyField(blank=True, related_name="user_invites", to="tenants.site"),
        ),
        migrations.AddField(
            model_name="userinvite",
            name="outlets",
            field=models.ManyToManyField(blank=True, related_name="user_invites", to="tenants.outlet"),
        ),
    ]
