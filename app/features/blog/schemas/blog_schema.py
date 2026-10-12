"""Blog 도메인 스키마 — 게시글 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema


class PostBase(BaseModel):
    """게시글 공통 필드."""

    title: str = Field(..., min_length=1, max_length=200, description="제목")
    content: str = Field(..., min_length=1, description="본문")
    author: str | None = Field(None, max_length=100, description="작성자(선택)")


class PostCreate(PostBase):
    """게시글 생성 요청."""


class PostUpdate(PatchSchema):
    """게시글 수정 요청 — 전달된 필드만 부분 수정한다."""

    nullable_fields = frozenset({"author"})

    title: str | None = Field(None, min_length=1, max_length=200, description="제목")
    content: str | None = Field(None, min_length=1, description="본문")
    author: str | None = Field(None, max_length=100, description="작성자")


class PostResponse(PostBase):
    """게시글 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime = Field(description="생성 시각(UTC, 오프셋 포함 ISO 8601)")
    updated_at: datetime = Field(description="수정 시각(UTC, 오프셋 포함 ISO 8601)")


class PostListResponse(BaseModel):
    """게시글 목록 응답(페이지네이션)."""

    items: list[PostResponse]
    total: int
    skip: int
    limit: int
