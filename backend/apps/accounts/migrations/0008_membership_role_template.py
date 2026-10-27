from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_roletemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="role_template",
            field=models.ForeignKey(
                blank=True,
                help_text="Template last applied to this membership; role/scope are copied, not live-linked.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="memberships",
                to="accounts.roletemplate",
            ),
        ),
    ]
