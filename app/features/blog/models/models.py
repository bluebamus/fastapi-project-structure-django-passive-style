"""
Blog 도메인 데이터베이스 모델

게시글(Post) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import TimestampMixin, UUIDPrimaryKeyMixin


class Post(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """블로그 게시글.

    Attributes:
        id: UUID 기본키
        title: 제목
        content: 본문
        author: 작성자 표시 이름(서버가 인증 주체의 username 으로 채운다)
        author_id: 작성자 사용자 ID(소유자 판정 키)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "blog_posts"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 소유자 판정 키(service-hardening ADR-018). 서버가 인증 주체로 채운다. NULL = 소유자 기록
    # 이전의 행 — 슈퍼유저만 수정·삭제할 수 있다.
    author_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, title={self.title!r})>"
