from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NumberAndRatio(BaseModel):
    number: int
    ratio: float


class ConceptOccurrence(BaseModel):
    context: str
    start_char: int
    end_char: int
    time: int | None = None


class ConceptProfile(BaseModel):
    concept: str
    num_occurrences: int
    examples: list[ConceptOccurrence]
    difficulty: float | None = None


class ConceptType(str, Enum):
    WORD = "word"
    PHRASAL_VERB = "phrasal_verb"
    IDIOM = "idiom"


class TimeRangeStats(BaseModel):
    start_time: int
    end_time: int
    difficulty: float | None = None


class LinguisticProfile(BaseModel):
    analysis_version: str

    concepts: dict[ConceptType, list[ConceptProfile]]

    pos_stats: dict[str, NumberAndRatio]
    sentences_count: int
    sentences_avg_length: float

    duration: int | None = None
    time_ranges: list[TimeRangeStats] | None = None

    difficulty: float | None = None


class PersonalConceptProfile(ConceptProfile):
    in_learning: bool
    prob_known: float | None = None
    personal_difficulty: float | None = None


class PersonalTimeRangeStats(TimeRangeStats):
    personal_difficulty: float | None = None
    estimated_unknown_concepts: NumberAndRatio | None = None


class PersonalMediaAnalysis(BaseModel):
    concepts: dict[ConceptType, list[PersonalConceptProfile]]
    personal_difficulty: float | None = None
    time_ranges: list[PersonalTimeRangeStats] | None = None
    estimated_unknown_concepts: dict[ConceptType, NumberAndRatio] | None
    recommended_concepts: list[str] | None = Field(
        default=None,
        description="Ranked list of concepts that are recommended to learn next",
    )
