from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    password: str


class DeviceTokenRequest(BaseModel):
    password: str
    name: str


class DeviceTokenResponse(BaseModel):
    device_id: str
    name: str
    token: str
    created_at: int


class DeviceSchema(BaseModel):
    device_id: str
    name: str
    created_at: int
    last_used_at: int
    revoked_at: int | None = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceSchema]


class ItemCreateRequest(BaseModel):
    kind: str
    url: str | None = None
    path: str | None = None
    upload_id: str | None = None
    feed_url: str | None = None
    episode_guid: str | None = None
    enclosure_url: str | None = None


class ItemPatchRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    tags: list[str] | None = None


class BookLocatorRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=2, alias="schema")
    chapter_index: int = Field(ge=0)
    paragraph_index: int | None = Field(default=None, ge=0)
    scroll_ratio: float = Field(default=0.0, ge=0, le=1)
    epub_href: str | None = None
    epub_progression: float | None = Field(default=None, ge=0, le=1)
    epub_total_progression: float | None = Field(default=None, ge=0, le=1)


class ProgressRequest(BaseModel):
    position_sec: float | None = Field(default=None, ge=0)
    consumption_state: str | None = None
    book_locator: BookLocatorRequest | None = None
    client_updated_at: int | None = Field(default=None, ge=0)


class TagsRequest(BaseModel):
    tags: list[str]
    client_updated_at: int | None = Field(default=None, ge=0)


class FeedPreviewRequest(BaseModel):
    url: str


class ReprocessRequest(BaseModel):
    from_stage: str = "organizing"


class TagRequest(BaseModel):
    tag: str



class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class OkResponse(BaseModel):
    ok: bool


class ArtifactSchema(BaseModel):
    kind: str
    sha256: str
    size: int
    mime: str
    duration_sec: float | None = None
    url: str | None = None


class AiResultSchema(BaseModel):
    summary: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    generated_at: int


class TagItemSchema(BaseModel):
    name: str
    source: str


class RunStepSchema(BaseModel):
    stage: str
    state: str
    attempt: int
    error_code: str | None = None
    error_message: str | None = None
    started_at: int | None = None
    finished_at: int | None = None


class RunSchema(BaseModel):
    id: str
    state: str
    label: str
    current_stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancel_requested: bool
    created_at: int
    started_at: int | None = None
    finished_at: int | None = None
    heartbeat_at: int | None = None
    steps: list[RunStepSchema] = Field(default_factory=list)
    log_tail: list[str] = Field(default_factory=list)


class ItemSchema(BaseModel):
    id: str
    version: int
    source_key: str
    source_type: str
    source_type_label: str
    platform: str
    platform_label: str
    source_url_raw: str | None = None
    source_url_canonical: str | None = None
    title: str
    author: str | None = None
    published_at: str | None = None
    fetched_at: int | None = None
    language: str | None = None
    duration_sec: float | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    tag_items: list[TagItemSchema] = Field(default_factory=list)
    consumption_state: str
    consumption_label: str
    audio_position_sec: float
    book_locator: str | None = None
    created_at: int
    updated_at: int
    processing_state: str
    processing_label: str
    status_category: str
    has_audio: bool
    has_book: bool
    has_cover: bool
    audio_url: str | None = None
    cover_url: str | None = None
    artifacts: list[ArtifactSchema] = Field(default_factory=list)
    ai: AiResultSchema | None = None
    run: RunSchema | None = None


class ItemListResponse(BaseModel):
    items: list[ItemSchema]
    count: int
    total: int
    limit: int | None = None
    offset: int = 0


class ItemCreateResponse(BaseModel):
    item: ItemSchema
    deduplicated: bool


class ReprocessResponse(BaseModel):
    run_id: str
    item: ItemSchema


class MutationResponse(BaseModel):
    ok: bool
    applied: bool = True
    item: ItemSchema
    field_clocks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class TranscriptSegmentSchema(BaseModel):
    seq: int
    start_ms: int
    end_ms: int
    text: str


class TranscriptResponse(BaseModel):
    item_id: str
    segments: list[TranscriptSegmentSchema]


class BookChapterResponse(BaseModel):
    item_id: str
    chapter_index: int
    title: str
    html: str
    text: str
    paragraphs: list[str]


class TagCountSchema(BaseModel):
    name: str
    count: int


class TagListResponse(BaseModel):
    tags: list[TagCountSchema]


class SearchEvidenceSchema(BaseModel):
    doc_kind: str
    ref: str
    text: str
    snippet: str
    score: float
    url: str


class SearchResultSchema(BaseModel):
    item: ItemSchema
    score: float
    evidence: list[SearchEvidenceSchema]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultSchema]
    count: int
    limit: int | None = None
    offset: int = 0


class ContinueEntrySchema(BaseModel):
    item: ItemSchema
    kind: str
    progress: str
    url: str


class ContinueResponse(BaseModel):
    entries: list[ContinueEntrySchema]


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    sha256: str
    size: int
    kind: str


class FeedEpisodeSchema(BaseModel):
    guid: str | None = None
    title: str
    author: str | None = None
    published_at: str | None = None
    duration_sec: float | None = None
    enclosure_url: str
    enclosure_type: str | None = None
    enclosure_size: int | None = None


class FeedPreviewResponse(BaseModel):
    title: str
    author: str | None = None
    link: str | None = None
    episodes: list[FeedEpisodeSchema]


class RunItemRef(BaseModel):
    id: str
    title: str


class RunDetailResponse(BaseModel):
    run: RunSchema
    item: RunItemRef


class HealthResponse(BaseModel):
    api_version: str
    capabilities: dict[str, bool]
    host: dict[str, Any]
    database: dict[str, Any]
    worker: dict[str, Any]


class SyncFileSchema(BaseModel):
    kind: str
    sha256: str
    size: int
    mime: str
    version: int
    url: str


class SyncItemSchema(BaseModel):
    id: str
    version: int
    source_type: str
    platform: str
    title: str
    author: str | None = None
    published_at: str | None = None
    fetched_at: int
    language: str | None = None
    duration_sec: float | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    processing_state: str
    error_code: str | None = None
    error_message: str | None = None
    has_audio: bool
    has_book: bool
    files: list[SyncFileSchema] = Field(default_factory=list)


class SyncTombstoneSchema(BaseModel):
    id: str
    version: int
    deleted_at: int
    epoch: str


class ManifestResponse(BaseModel):
    items: list[SyncItemSchema]
    tombstones: list[SyncTombstoneSchema]
    next_cursor: str
    has_more: bool
    epoch: str


class SyncStateItemSchema(BaseModel):
    id: str
    state_seq: int
    audio_position_sec: float
    book_locator: str | None = None
    consumption_state: str
    last_consumed_at: int | None = None


class SyncStateResponse(BaseModel):
    items: list[SyncStateItemSchema]
    next_cursor: str
    has_more: bool
    epoch: str
