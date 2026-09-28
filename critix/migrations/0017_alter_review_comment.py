from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("critix", "0016_movie_tmdb_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="review",
            name="comment",
            field=models.TextField(blank=True),
        ),
    ]
