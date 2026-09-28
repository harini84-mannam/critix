from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('critix', '0015_moviecast_moviemedia'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='tmdb_id',
            field=models.PositiveIntegerField(
                blank=True,
                editable=False,
                null=True,
                unique=True,
            ),
        ),
    ]
