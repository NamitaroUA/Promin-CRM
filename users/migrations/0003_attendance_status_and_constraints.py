"""
Hand-written migration (not auto-generated): converts PostAttendance.status
from BooleanField to a CharField with choices WITHOUT losing data.
A plain AlterField would not map True/False to the new string values, so we
add a temporary column, copy the data (True -> 'approved', False -> 'pending'),
drop the old column and rename the new one.
"""
from django.db import migrations, models


def bool_to_choice(apps, schema_editor):
    PostAttendance = apps.get_model('users', 'PostAttendance')
    PostAttendance.objects.filter(status=True).update(status_new='approved')


def choice_to_bool(apps, schema_editor):
    PostAttendance = apps.get_model('users', 'PostAttendance')
    PostAttendance.objects.filter(status_new='approved').update(status=True)
    PostAttendance.objects.exclude(status_new='approved').update(status=False)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_post_postattendance_attachment_postfile_postimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='postattendance',
            name='status_new',
            field=models.CharField(choices=[('pending', 'Очікує розгляду'), ('approved', 'Підтверджено'), ('rejected', 'Відхилено')], default='pending', max_length=20, verbose_name='Статус'),
        ),
        migrations.RunPython(bool_to_choice, choice_to_bool),
        migrations.RemoveField(
            model_name='postattendance',
            name='status',
        ),
        migrations.RenameField(
            model_name='postattendance',
            old_name='status_new',
            new_name='status',
        ),
        migrations.AddField(
            model_name='postattendance',
            name='review_comment',
            field=models.TextField(blank=True, verbose_name='Причина відхилення'),
        ),
        migrations.AlterField(
            model_name='postattendance',
            name='post',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attendances', to='users.post'),
        ),
        migrations.AlterField(
            model_name='attachment',
            name='file',
            field=models.FileField(upload_to='attachments/%Y/%m/', verbose_name='Файл'),
        ),
        migrations.AddConstraint(
            model_name='postattendance',
            constraint=models.UniqueConstraint(fields=('user', 'post'), name='unique_attendance_per_post'),
        ),
    ]
