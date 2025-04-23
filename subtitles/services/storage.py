import hashlib
import os
from io import BytesIO
import structlog
from django.db import transaction
from django.core.files import File
from tempfile import NamedTemporaryFile

from TMDB.models import Movie
from ..models import MovieSubtitle
from ..schemas import SubtitleMetadata

log: structlog.BoundLogger = structlog.get_logger(__name__)


class SubtitleStorageService:
    """Service for storing and retrieving subtitle files"""

    def _compute_hash(self, content: BytesIO) -> str:
        """Compute SHA-256 hash of content"""
        return hashlib.sha256(content.getvalue()).hexdigest()

    def _generate_file_path(
        self,
        movie_id: int,
        language: str,
        version: str,
        content_hash: str,
        subtitle_format: str,
    ) -> str:
        """Generate standardized file path"""
        return f"media/{movie_id}/subtitles/{language}/{version}_{content_hash}.{subtitle_format}"

    def store_subtitle(
        self,
        movie: Movie,
        subtitle_content: BytesIO,
        metadata: SubtitleMetadata,
        subtitle_format: str,
    ) -> MovieSubtitle:
        """
        Store subtitle content and create MovieSubtitle record.
        """
        log.info(
            "Storing subtitle",
            movie_id=movie.id,
            language=metadata.language,
            subtitle_format=subtitle_format,
        )

        try:
            content_hash = self._compute_hash(subtitle_content)
            file_path = self._generate_file_path(
                movie_id=movie.id,
                language=metadata.language,
                version=metadata.release,
                content_hash=content_hash,
                subtitle_format=subtitle_format,
            )

            with transaction.atomic():
                # Create subtitle record
                version = metadata.release[:50] if metadata.release else ""
                metadata_dict = metadata.model_dump()
                metadata_dict["upload_date"] = metadata_dict["upload_date"].isoformat()
                subtitle = MovieSubtitle.objects.create(
                    movie=movie,
                    language=metadata.language,
                    source="opensubtitles",
                    version=version,
                    content_hash=content_hash,
                    subtitle_format=subtitle_format,
                    metadata=metadata_dict,
                    quality_score=self._calculate_quality_score(metadata),
                )

                # Use context manager for temporary file
                with NamedTemporaryFile(
                    delete=False, suffix=f".{subtitle_format}"
                ) as temp_file:
                    # Write content to temporary file
                    subtitle_content.seek(0)
                    temp_file.write(subtitle_content.getvalue())
                    temp_file.flush()

                    # Save to S3 using Django's File
                    with open(temp_file.name, "rb") as f:
                        subtitle.subtitle_file.save(file_path, File(f), save=True)

                # Clean up temporary file
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)

                log.info(
                    "Subtitle stored successfully",
                    subtitle_id=subtitle.id,
                    path=subtitle.subtitle_file.name,
                )

                return subtitle

        except Exception as e:
            log.error(
                "Failed to store subtitle",
                movie_id=movie.id,
                language=metadata.language,
                error=str(e),
                exc_info=True,
            )
            raise
        finally:
            subtitle_content.close()

    async def get_subtitle(self, subtitle_id: int) -> BytesIO:
        """Retrieve stored subtitle content and metadata with proper cleanup"""
        log.info("Retrieving subtitle", subtitle_id=subtitle_id)

        content = BytesIO()
        try:
            subtitle = await MovieSubtitle.objects.aget(id=subtitle_id)

            if not subtitle.subtitle_file:
                raise FileNotFoundError(f"No file found for subtitle {subtitle_id}")

            # Read file content into memory and close file immediately
            with subtitle.subtitle_file.open("rb") as f:
                content.write(f.read())
            content.seek(0)

            # return content, SubtitleMetadata(**subtitle.metadata)
            return content

        except Exception as e:
            content.close()  # Ensure content is closed on error
            log.error(
                "Failed to retrieve subtitle",
                subtitle_id=subtitle_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def delete_subtitle(self, subtitle_id: int) -> None:
        """Delete stored subtitle file and record"""
        log.info("Deleting subtitle", subtitle_id=subtitle_id)

        try:
            subtitle = await MovieSubtitle.objects.aget(id=subtitle_id)

            # Delete file first
            if subtitle.subtitle_file:
                subtitle.subtitle_file.delete(save=False)
                log.debug("Deleted subtitle file", path=subtitle.subtitle_file.name)

            # Delete record
            await subtitle.adelete()

            log.info("Deleted subtitle successfully", subtitle_id=subtitle_id)

        except MovieSubtitle.DoesNotExist:
            log.warning("Subtitle not found for deletion", subtitle_id=subtitle_id)
        except Exception as e:
            log.error(
                "Failed to delete subtitle",
                subtitle_id=subtitle_id,
                error=str(e),
                exc_info=True,
            )
            raise

    def _calculate_quality_score(self, metadata: SubtitleMetadata) -> float:
        """Calculate quality score from metadata"""
        score = 0.0
        max_score = 0.0

        # Download count (0-0.3)
        if metadata.download_count > 0:
            from math import log

            score += min(0.3, log(metadata.download_count + 1) / 10)
        max_score += 0.3

        # Ratings (0-0.2)
        if metadata.votes > 0:
            score += (metadata.ratings / 10) * 0.2
        max_score += 0.2

        # HD (0-0.15)
        if metadata.hd:
            score += 0.15
        max_score += 0.15

        # Trusted source (0-0.15)
        if metadata.from_trusted:
            score += 0.15
        max_score += 0.15

        # Penalize machine/AI translation (-0.2)
        if metadata.machine_translated or metadata.ai_translated:
            score -= 0.2
            max_score += 0.2

        # Normalize score to 0-1 range
        if max_score > 0:
            return max(0.0, min(1.0, score / max_score))
        return 0.0
