from django.db import migrations


def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name='Editor')
    Group.objects.get_or_create(name='Root Editor')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_attendance_status_and_constraints'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Reverse is intentionally a no-op: deleting the groups on rollback
        # would strip roles from users who were assigned them manually.
        migrations.RunPython(create_groups, migrations.RunPython.noop),
    ]
