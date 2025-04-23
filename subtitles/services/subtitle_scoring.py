from dataclasses import dataclass
import math
import structlog
from subtitles.schemas import SubtitleSearchResponse

log: structlog.BoundLogger = structlog.get_logger(__name__)


@dataclass
class ScoringWeights:
    """Configuration for subtitle quality scoring weights"""

    TRUSTED_SOURCE_BONUS: float = 5.0
    AI_TRANSLATION_PENALTY: float = -1000.0  # Effectively excludes AI translations
    MACHINE_TRANSLATION_PENALTY: float = (
        -1000.0
    )  # Effectively excludes machine translations

    DOWNLOAD_COUNT_WEIGHT: float = 1.0


class SubtitleQualityScorer:
    """Scores subtitle quality based on specified criteria"""

    def __init__(self, weights: ScoringWeights = ScoringWeights()):
        self.weights = weights

    def score_subtitle(self, subtitle: SubtitleSearchResponse) -> float:
        """
        Calculate quality score for a subtitle based on criteria.

        Scoring factors:
        1. AI/Machine translation: Heavy penalty to exclude these
        2. Download count: Log-scaled score
        3. Trusted source: Fixed bonus

        Returns:
            float: Quality score (higher is better)
        """
        try:
            score = 0.0
            attributes = subtitle.attributes

            # Check for automatic translations - apply penalties
            if attributes.ai_translated:
                score += self.weights.AI_TRANSLATION_PENALTY

            if attributes.machine_translated:
                score += self.weights.MACHINE_TRANSLATION_PENALTY

            if attributes.from_trusted:
                score += self.weights.TRUSTED_SOURCE_BONUS

            if attributes.download_count > 0:
                download_score = (
                    math.log(attributes.download_count + 1)
                    * self.weights.DOWNLOAD_COUNT_WEIGHT
                )
                score += download_score

            return score

        except Exception as e:
            log.error(
                "Error scoring subtitle",
                subtitle_id=subtitle.id,
                error=str(e),
                exc_info=True,
            )
            return float("-inf")

    def select_best_subtitle(
        self, subtitles: list[SubtitleSearchResponse]
    ) -> SubtitleSearchResponse:
        """
        Select the best subtitle from a list based on quality scores.
        """
        if not subtitles:
            raise ValueError("No subtitles provided for selection")

        # Score all subtitles
        scored_subtitles = [
            (subtitle, self.score_subtitle(subtitle)) for subtitle in subtitles
        ]

        valid_subtitles = [
            (subtitle, score)
            for subtitle, score in scored_subtitles
            if score > float("-inf")
        ]

        if not valid_subtitles:
            raise ValueError("No valid subtitles found after scoring")

        # Sort by score (descending) and return the best one
        best_subtitle, best_score = max(valid_subtitles, key=lambda x: x[1])

        log.info(
            "Selected best subtitle",
            subtitle_id=best_subtitle.id,
            score=best_score,
            download_count=best_subtitle.attributes.download_count,
            from_trusted=best_subtitle.attributes.from_trusted,
            total_candidates=len(subtitles),
        )

        return best_subtitle
