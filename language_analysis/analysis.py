import gc
import structlog
from django.db import transaction

from TMDB.models import Movie
from language_analysis.models import MediaAnalysisResult
from language_analysis.processor.processor import LinguisticProcessor
from language_analysis.processor.schema import (
    LinguisticProfile,
)
from subtitles.models import MovieSubtitle

log: structlog.BoundLogger = structlog.get_logger(__name__)


class LinguisticProcessorSingleton:
    _instance: LinguisticProcessor | None = None

    @classmethod
    def get_instance(cls) -> LinguisticProcessor:
        if not cls._instance:
            log.info("Initializing new LinguisticProcessor instance")
            cls._instance = LinguisticProcessor()
        return cls._instance

    @classmethod
    def cleanup(cls) -> None:
        if cls._instance:
            log.info("Cleaning up LinguisticProcessor instance")
            cls._instance = None
            gc.collect()


class LanguageAnalysisService:
    """Service for handling linguistic analysis operations."""

    def process_text(
        self,
        text: str,
        media_type: str,
        original_language: str,
    ) -> LinguisticProfile:
        """
        Process text and generate linguistic analysis.
        """
        log.info(
            "Starting text analysis",
            text_length=len(text),
            media_type=media_type,
            original_language=original_language,
        )

        try:
            processor = LinguisticProcessorSingleton.get_instance()
            linguistic_profile = processor.process(text)
            return linguistic_profile

        except Exception as e:
            log.error("Error during linguistic analysis", error=str(e))
            raise

        finally:
            LinguisticProcessorSingleton.cleanup()

    def store_analysis_result(
        self,
        movie: Movie,
        linguistic_analysis: LinguisticProfile,
        subtitle: MovieSubtitle,
    ) -> MediaAnalysisResult:
        """
        Store analysis results in the database.
        """
        log.info(
            "Storing analysis result",
            tmdb_id=movie.tmdb_id,
            version=linguistic_analysis.analysis_version,
            subtitle_id=subtitle.id,
        )

        @transaction.atomic
        def create_analysis_result() -> MediaAnalysisResult:
            # Convert Pydantic models to dict format for JSON storage
            concepts_dict = {}
            for concept_type, concepts in linguistic_analysis.concepts.items():
                concepts_dict[concept_type] = [
                    {
                        "concept": c.concept,
                        "num_occurrences": c.num_occurrences,
                        "examples": [e.model_dump() for e in c.examples],
                        "difficulty": c.difficulty,
                    }
                    for c in concepts
                ]

            pos_stats_dict = {
                pos: {"number": stats.number, "ratio": stats.ratio}
                for pos, stats in linguistic_analysis.pos_stats.items()
            }
            # Create analysis result record
            result = MediaAnalysisResult.objects.create(
                movie=movie,
                version=str(linguistic_analysis.analysis_version),
                kind=MediaAnalysisResult.MediaType.MOVIE,
                subtitle_id=subtitle.id,
                subtitle_version=subtitle.version,
                is_latest=True,
                lexical_analysis={
                    "concepts": concepts_dict,
                    "pos_stats": pos_stats_dict,
                    "sentences_count": linguistic_analysis.sentences_count,
                    "sentences_avg_length": linguistic_analysis.sentences_avg_length,
                    "difficulty": linguistic_analysis.difficulty,
                    "duration": linguistic_analysis.duration,
                    "time_ranges": (
                        [tr.model_dump() for tr in linguistic_analysis.time_ranges]
                        if linguistic_analysis.time_ranges
                        else None
                    ),
                },
            )
            # Save movie difficulty score
            movie.difficulty = linguistic_analysis.difficulty
            movie.save()


            # Mark previous analyses as not latest
            MediaAnalysisResult.objects.filter(movie=movie, is_latest=True).exclude(
                id=result.id
            ).update(is_latest=False)

            return result

        result = create_analysis_result()

        log.info(
            "Stored analysis result",
            media_analysis_result_id=result.id,
            movie_id=movie.id,
        )
        return result
