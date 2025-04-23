from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class UploaderInfo(BaseModel):
    uploader_id: int | None = None
    name: str
    rank: str


class FeatureDetails(BaseModel):
    feature_id: int
    feature_type: str | None = None
    year: int | None = None
    title: str | None = None
    movie_name: str | None = None
    imdb_id: int | None = None
    tmdb_id: int | None


class SubtitleFile(BaseModel):
    file_id: int
    cd_number: int
    file_name: str


class RelatedLink(BaseModel):
    label: str
    url: str
    img_url: str | None


class SubtitleMetadata(BaseModel):
    subtitle_id: str
    language: str
    download_count: int = 0
    new_download_count: int = 0
    hearing_impaired: bool = False
    hd: bool = False
    fps: float | None = None
    votes: int = 0
    ratings: float = 0.0
    from_trusted: bool | None = None
    foreign_parts_only: bool = False
    upload_date: datetime
    file_hashes: list[str] = Field(default_factory=list)
    ai_translated: bool = False
    nb_cd: int = 1
    slug: str | None = None
    machine_translated: bool = False
    release: str = ""
    comments: str | None = None
    legacy_subtitle_id: int | None = None
    legacy_uploader_id: int | None = None
    uploader: UploaderInfo
    feature_details: FeatureDetails
    url: str = ""
    related_links: list[RelatedLink]
    files: list[SubtitleFile]


class SubtitleSearchResponse(BaseModel):
    id: str
    type: str = "subtitle"
    attributes: SubtitleMetadata


class SubtitleUploadResponse(BaseModel):
    id: int
    file_path: str
    language: str
    quality_score: float | None = None


class SubtitleResponse(BaseModel):
    id: int
    movie_id: int
    language: str
    source: str
    version: str
    subtitle_format: str
    quality_score: float | None = None
    is_active: bool
    processing_status: str
    processing_error: str | None = None
    processing_attempts: int = 0
    last_processing_attempt: datetime | None = None
    processed_at: datetime | None = None
    metadata: dict[str, Any] = {}

    subtitle_file: Any = Field(alias="subtitle_file", exclude=True)

    @computed_field
    def file_url(self) -> str | None:
        """Get the file URL from the FileField"""
        if hasattr(self.subtitle_file, "url"):
            return str(self.subtitle_file.url)
        return None

    @computed_field
    def file_path(self) -> str | None:
        """Get the file path from the FileField"""
        if hasattr(self.subtitle_file, "name"):
            return str(self.subtitle_file.name)
        return None

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class SubtitleListResponse(BaseModel):
    subtitles: list[SubtitleResponse]


class SubtitleSyncResponse(BaseModel):
    status: str
    subtitle_id: int | None = None
    job_id: str | None = None
    error: str | None = None


class SubtitleDownloadRequest(BaseModel):
    language: str = "en"
    max_downloads: int = 100


class DownloadJobStatus(BaseModel):
    job_id: str
    status: str
    total_attempted: int | None = None
    successful: int | None = None
    failed: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: int | None = None


class DownloadStats(BaseModel):
    total_movies: int
    movies_with_subtitles: int
    movies_without_subtitles: int
    downloads_in_progress: int
