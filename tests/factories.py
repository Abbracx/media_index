import factory
from django.utils import timezone
from TMDB.models import Movie
from subtitles.models import MovieSubtitle
from language_analysis.models import MediaAnalysisResult
from factory.django import DjangoModelFactory
from faker import Factory as FakerFactory
import random
from pytest_factoryboy import named_model
from datetime import datetime

faker = FakerFactory.create()

GenreList = named_model(list, "GenreList")


class TimeStampedFactory(DjangoModelFactory):
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)

# Factory for Movie
class MovieFactory(TimeStampedFactory):

    class Meta:
        model = Movie
        skip_postgeneration_save = True

    class Params:
        high_ranking = factory.Trait(
            vote_count=12000,
            vote_average=8.5,
        )
        medium_ranking = factory.Trait(
            vote_count=9000,
            vote_average=7.5,
        )
        low_ranking = factory.Trait(
            vote_count=8000,
            vote_average=6.5,
        )

    tmdb_id = factory.LazyAttribute(lambda x: random.randint(1, 100000))
    latest_analysis_id = factory.LazyAttribute(lambda x: random.randint(1, 100000))
    title = factory.Faker("sentence", nb_words=3)
    original_title = factory.Faker("sentence", nb_words=3)
    language = factory.LazyAttribute(lambda x: "en")
    original_language = factory.LazyAttribute(lambda x: "en")
    release_date = factory.LazyFunction(lambda: timezone.now().date())
    genres = factory.LazyFunction(lambda: GenreList([factory.Faker("word") for _ in range(3)]))
    runtime = factory.Faker("random_int", min=60, max=180)
    overview = factory.Faker("text", max_nb_chars=200)
    poster_url = factory.Faker("url")
    backdrop_url = factory.Faker("url")
    vote_average = factory.LazyAttribute(lambda x: round(random.uniform(0, 10), 1))
    vote_count = factory.Faker("random_int", min=0, max=1000)
    difficulty = factory.LazyAttribute(lambda x: round(random.uniform(0, 10), 1))
    author = factory.Faker("name")

    @factory.post_generation
    def with_title(self, create, extracted, **kwargs):
        if extracted:
            self.title = extracted
            self.original_title = extracted
            if create:
                self.save()


class MovieSubtitleFactory(TimeStampedFactory):
    class Meta:
        model = MovieSubtitle

    movie = factory.SubFactory(MovieFactory)
    subtitle_file = factory.LazyAttribute(lambda _: faker.file_path(extension='srt')) 
    source = factory.Faker("sentence", nb_words=3)
    subtitle_format = factory.Faker("random_element", elements=[choice[0] for choice in MovieSubtitle.SubtitleFormat.choices])
    version = factory.Faker("word")  
    language = factory.Faker("language_code")  
    content_hash = factory.Faker("sha256")  
    quality_score = factory.LazyAttribute(lambda _: round(faker.random_number(digits=2) / 100, 2))  
    metadata = factory.Faker("json")  
    is_active = factory.Faker("boolean")  
    processing_status = factory.Faker("random_element", elements=[choice[0] for choice in MovieSubtitle.ProcessingStatus.choices])
    processing_error = factory.Faker("sentence", nb_words=5)  
    processing_attempts = factory.Faker("random_int", min=0, max=10)  
    last_processing_attempt = factory.Faker("date_time_this_year", before_now=True)  
    processed_at = factory.Faker("date_time_this_year", after_now=True)  
    subtitle_is_processed = factory.Faker("boolean", chance_of_getting_true=50) 



class MediaAnalysisResultFactory(TimeStampedFactory):
    class Meta:
        model = MediaAnalysisResult
        skip_postgeneration_save = True

    subtitle_file = factory.LazyAttribute(lambda _: faker.file_path(extension='srt'))
    source = factory.Faker("sentence", nb_words=3)  
    subtitle_format = factory.Faker("random_element", elements=[choice[0] for choice in MovieSubtitle.SubtitleFormat.choices])
    version = factory.Faker("word")  
    language = factory.Faker("language_code")  
    content_hash = factory.Faker("sha256")
    quality_score = factory.LazyAttribute(lambda _: round(faker.random_number(digits=2) / 100, 2))
    metadata = factory.Faker("json")
    is_active = factory.Faker("boolean")
    processing_status = factory.Faker("random_element", elements=[choice[0] for choice in MovieSubtitle.ProcessingStatus.choices])
    processing_error = factory.Faker("sentence", nb_words=5)
    processing_attempts = factory.Faker("random_int", min=0, max=10)
    last_processing_attempt = factory.Faker("date_time_this_year", before_now=True) 
    processed_at = factory.Faker("date_time_this_year", after_now=True)
    subtitle_is_processed = factory.Faker("boolean", chance_of_getting_true=50) 

# Factory for MediaAnalysisResult
# class MediaAnalysisResultFactory(DjangoModelFactory):
#     class Meta:
#         model = MediaAnalysisResult
#         skip_postgeneration_save = True

#     movie = factory.SubFactory(MovieFactory)
#     version = factory.Faker("word")
#     kind = MediaAnalysisResult.MediaType.MOVIE
#     subtitle = factory.SubFactory(MovieSubtitleFactory)
#     subtitle_version = factory.Faker("word")
#     lexical_analysis = {
#         "concepts": {},
#         "pos_stats": {},
#         "sentences_count": 0,
#         "sentences_avg_length": 0,
#         "difficulty": 0,
#     }
#     is_latest = True
