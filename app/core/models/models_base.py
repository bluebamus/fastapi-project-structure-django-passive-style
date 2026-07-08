"""
SQLAlchemy Base 클래스

모든 ORM 모델의 기반이 되는 Base 클래스를 정의합니다.
이 파일은 모든 도메인 모듈에서 공통으로 사용됩니다.

사용법:
    from app.core.models.models_base import Base, TimestampMixin, UUIDMixin

    class MyModel(Base, TimestampMixin):
        __tablename__ = "my_table"
        ...
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import timezone_settings


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base

    모든 모델이 상속받는 기본 클래스입니다.
    공통 필드와 메서드를 제공합니다.
    """

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }

    if TYPE_CHECKING:
        # 타입 전용 계약: BaseRepository/pagination 등 제네릭 코드는 모든
        # Repository 대상 모델이 String(36) UUID 기본키 `id` 를 갖는다고 전제한다.
        # 실제 매핑은 각 도메인 모델(또는 UUIDMixin)이 제공하므로 여기서는
        # 런타임 컬럼을 만들지 않고(타입 검사 시에만 노출) 그 불변식만 선언한다.
        id: Mapped[str]

    def to_dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TimestampMixin:
    """
    타임스탬프 믹스인

    created_at 필드를 자동으로 추가합니다.
    설정된 타임존(기본값: Asia/Seoul)이 적용됩니다.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    UUID 기본키 믹스인

    String(36) 타입의 UUID id 필드를 자동으로 추가합니다.
    MySQL, PostgreSQL 모두 호환됩니다.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
