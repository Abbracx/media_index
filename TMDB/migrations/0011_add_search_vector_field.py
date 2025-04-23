from django.db import migrations
import django.contrib.postgres.search


class Migration(migrations.Migration):
    dependencies = [
        ("TMDB", "0010_remove_movie_tmdb_movie_title_db16a7_idx_and_more"),
    ]

    operations = [
        # First create the column
        migrations.AddField(
            model_name="movie",
            name="title_vector",
            field=django.contrib.postgres.search.SearchVectorField(null=True),
        ),
        # Update existing records
        migrations.RunSQL(
            sql="""
               UPDATE "TMDB_movie"
               SET title_vector = to_tsvector('english', title);
               """,
            reverse_sql="",
        ),
        # Add trigger to keep it updated
        migrations.RunSQL(
            sql="""
               CREATE OR REPLACE FUNCTION update_title_vector_trigger() RETURNS trigger AS $$
               BEGIN
                   NEW.title_vector := to_tsvector('english', NEW.title);
                   RETURN NEW;
               END;
               $$ LANGUAGE plpgsql;

               CREATE TRIGGER title_vector_update 
                   BEFORE INSERT OR UPDATE ON "TMDB_movie"
                   FOR EACH ROW 
                   EXECUTE FUNCTION update_title_vector_trigger();
               """,
            reverse_sql="""
               DROP TRIGGER IF EXISTS title_vector_update ON "TMDB_movie";
               DROP FUNCTION IF EXISTS update_title_vector_trigger();
               """,
        ),
        # Add the GIN index
        migrations.RunSQL(
            sql="""
               CREATE INDEX title_vector_idx ON "TMDB_movie" USING gin(title_vector);
               """,
            reverse_sql="""
               DROP INDEX IF EXISTS title_vector_idx;
               """,
        ),
    ]
