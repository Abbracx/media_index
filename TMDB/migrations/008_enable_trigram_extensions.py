from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations
from django.db.models import Index


class Migration(migrations.Migration):

    dependencies = [
        ("TMDB", "0007_alter_movie_created_at_and_more"),
    ]

    operations = [
        TrigramExtension(),
        UnaccentExtension(),
        migrations.AddIndex(
            model_name="movie",
            index=GinIndex(
                fields=["title"],
                name="movie_title_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="movie",
            index=GinIndex(
                fields=["original_title"],
                name="movie_orig_title_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="movie",
            index=Index(fields=["-vote_count"], name="movie_vote_count_idx"),
        ),
    ]
