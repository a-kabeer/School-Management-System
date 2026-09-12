from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="timetable",
            constraint=models.UniqueConstraint(
                fields=("academic_year", "teacher", "weekday", "period"),
                condition=Q(teacher__isnull=False),
                name="uq_timetable_teacher_slot",
            ),
        ),
        migrations.AddConstraint(
            model_name="timetable",
            constraint=models.UniqueConstraint(
                fields=("branch", "academic_year", "room", "weekday", "period"),
                condition=~Q(room=""),
                name="uq_timetable_room_slot",
            ),
        ),
    ]
