from django.db import migrations, models


DEFAULT_WORKING_WEEKDAYS = [0, 1, 2, 3, 4]


def set_default_working_weekdays(apps, schema_editor):
    Branch = apps.get_model("tenants", "Branch")
    Branch.objects.all().update(working_weekdays=DEFAULT_WORKING_WEEKDAYS)


class Migration(migrations.Migration):
    dependencies = [("tenants", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="working_weekdays",
            field=models.JSONField(
                default=list,
                help_text="Days used by this branch for recurring weekly timetables. Monday=0 through Sunday=6.",
                verbose_name="working days",
            ),
        ),
        migrations.RunPython(set_default_working_weekdays, migrations.RunPython.noop),
    ]
