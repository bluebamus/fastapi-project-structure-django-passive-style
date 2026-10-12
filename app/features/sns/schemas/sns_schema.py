"""SNS 도메인 스키마 — 피드 게시물 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema


class SnsPostBase(BaseModel):
    """피드 게시물 공통 필드."""

    content: str = Field(..., min_length=1, max_length=500, description="게시물 본문")


class SnsPostCreate(SnsPostBase):
    """피드 게시물 생성 요청. 작성자는 받지 않는다 — 서버가 인증 주체로 채운다(ADR-018)."""


class SnsPostUpdate(PatchSchema):
    """피드 게시물 수정 요청 — 전달된 필드만 부분 수정한다."""

    content: str | None = Field(None, min_length=1, max_length=500, description="본문")


class SnsPostResponse(SnsPostBase):
    """피드 게시물 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    author: str | None = Field(
        None, description="작성자 표시 이름(서버가 로그인 사용자명으로 채운다)"
    )
    author_id: str | None = Field(
        None, description="작성자 사용자 ID — 소유자 판정 키(NULL 이면 슈퍼유저만 수정)"
    )
    like_count: int
    created_at: datetime = Field(description="생성 시각(UTC, 오프셋 포함 ISO 8601)")
    updated_at: datetime = Field(description="수정 시각(UTC, 오프셋 포함 ISO 8601)")


class SnsPostListResponse(BaseModel):
    """피드 게시물 목록 응답(페이지네이션)."""

    items: list[SnsPostResponse]
    total: int
    skip: int
    limit: int
