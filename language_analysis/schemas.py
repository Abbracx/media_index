from datetime import datetime
from typing import Any
from ninja import Schema
from pydantic import field_validator
from language_analysis.processor.schema import LinguisticProfile

class ProcessTextRequest(Schema):
    text: str
    type: str
    original_language: str

    @field_validator('text')
    def check_text_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text cannot be empty")
        return value


class ProcessTextResponse(Schema):
    status: str
    data: LinguisticProfile


class UploadMediaTextRequest(Schema):
    movie_text: str
    main_language: str
    source: str


class MediaAnalysisStatsResponse(Schema):
    id: int
    movie_id: int
    version: str
    created_at: datetime
    lexical_stats: dict[str, Any]


class JobResponse(Schema):
    job_id: str


# For convinience
class ErrorResponse(Schema):
    error: dict[str, str]
