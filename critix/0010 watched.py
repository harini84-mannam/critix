
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('critix', '0009_notification'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Watched',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('watched_at', models.DateTimeField(auto_now_add=True)),
                ('movie', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watched_by_users', to='critix.movie')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='watched', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-watched_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='watched',
            constraint=models.UniqueConstraint(fields=('user', 'movie'), name='unique_user_movie_watched'),
        ),
    ]