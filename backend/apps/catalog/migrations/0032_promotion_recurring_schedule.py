from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0031_product_label_markdown_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="schedule_weekdays",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Optional ISO weekdays 1=Monday through 7=Sunday. Empty means every day.",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="schedule_start_time",
            field=models.TimeField(
                blank=True,
                null=True,
                help_text="Optional local start time in the business timezone.",
            ),
        ),
        migrations.AddField(
            model_name="promotion",
            name="schedule_end_time",
            field=models.TimeField(
                blank=True,
                null=True,
                help_text="Optional local end time in the business timezone. Overnight windows are not supported.",
            ),
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(schedule_start_time__isnull=True, schedule_end_time__isnull=True)
                    | models.Q(schedule_start_time__isnull=False, schedule_end_time__isnull=False)
                ),
                name="promotion_schedule_time_pair",
            ),
        ),
    ]
