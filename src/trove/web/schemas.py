from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str


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
    chapter_index: int = Field(ge=0)
    paragraph_index: int | None = Field(default=None, ge=0)
    scroll_ratio: float = Field(default=0.0, ge=0, le=1)


class ProgressRequest(BaseModel):
    position_sec: float | None = Field(default=None, ge=0)
    consumption_state: str | None = None
    book_locator: BookLocatorRequest | None = None


class FeedPreviewRequest(BaseModel):
    url: str


class ReprocessRequest(BaseModel):
    from_stage: str = "organizing"


class TagRequest(BaseModel):
    tag: str
