"""SQLAlchemy Base 와 공통 필드 Mixin.

모든 ORM 모델의 기반이다. 공통 필드는 **책임 단위로 쪼갠 Mixin** 으로 제공하고,
모델은 필요한 것만 조합한다(development-plan Phase 2).

쪼갠 이유는 실제 모델이 그렇게 생겼기 때문이다. 대부분은 생성·수정 시각을 모두
갖지만, 접속 로그처럼 **한 번 쓰고 고치지 않는** 테이블은 ``updated_at`` 이 없다.
하나로 묶인 Mixin 만 있으면 그런 모델은 필드를 손으로 다시 쓰거나, 쓰지도 않는
컬럼을 떠안게 된다.

사용법::

    from app.core.models.models_base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

    class AccessLog(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
        __tablename__ = "access_logs"

    class Post(Base, UUIDPrimaryKeyMixin, TimestampMixin):   # created + updated
        __tablename__ = "posts"

컬럼 순서: mixin 컬럼은 기본적으로 모델 자신의 컬럼 **뒤로** 밀린다. 그대로 두면
``create_all`` 로 만든 개발 DB 와 migration 으로 만든 운영 DB 의 컬럼 순서가 갈리므로,
``sort_order`` 로 원래 배치(id → 도메인 컬럼 → created_at → updated_at)를 고정한다.
Alembic 은 컬럼을 이름으로 비교해 순서를 diff 로 잡지 않기 때문에, 이걸 놓치면
**아무 경고 없이** 두 환경이 어긋난다.
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

    if TYPE_CHECKING:
        # 저장소(BaseRepository)가 관리하는 모든 모델은 UUIDPrimaryKeyMixin 을 통해
        # 문자열 ``id`` 기본키를 갖는다는 것이 이 프로젝트의 불변식이다. 런타임에는
        # 각 모델/믹스인이 실제 컬럼을 정의하므로, 여기서는 제네릭 코드(self.model.id)의
        # 타입 체크를 위한 선언만 둔다(TYPE_CHECKING 가드로 런타임 매핑에는 영향 없음).
        id: Mapped[str]

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }

    def to_dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class UUIDPrimaryKeyMixin:
    """UUID 문자열 기본키 ``id``.

    ``String(36)`` 이라 MySQL·PostgreSQL·SQLite 어디서든 같은 모양이다. 네이티브
    UUID 타입을 쓰지 않는 것은 방언마다 표현이 갈려 migration 이 복잡해지기 때문이다.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        # 기본키는 맨 앞. sort_order 를 주지 않으면 mixin 컬럼이 모델 자신의 컬럼
        # **뒤로** 밀려, create_all 로 만든 개발 DB 와 migration 으로 만든 운영 DB 의
        # 컬럼 순서가 갈린다. 논리 스키마는 같지만 그런 종류의 차이는 나중에
        # "왜 여기서만 다르지"로 돌아온다.
        sort_order=-100,
    )


class CreatedAtMixin:
    """생성 시각 ``created_at``.

    앱 설정 타임존(기본 Asia/Seoul)의 시각을 **애플리케이션이** 넣는다. DB 의
    ``CURRENT_TIMESTAMP`` 를 쓰지 않는 이유는 DB 서버 타임존에 값이 좌우되기
    때문이다 — 서버를 옮기면 조용히 달라진다.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
        sort_order=100,  # 도메인 컬럼 뒤 (기존 배치 유지)
    )


class UpdatedAtMixin:
    """수정 시각 ``updated_at``.

    ``onupdate`` 는 ORM 이 UPDATE 를 낼 때만 동작한다. Raw SQL 로 갱신하면 갱신되지
    않는다 — Raw 경로에서는 이 컬럼을 명시적으로 써야 한다(Phase 4 계약).
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        onupdate=lambda: timezone_settings.now(),
        nullable=False,
        sort_order=101,  # created_at 바로 뒤 (기존 배치 유지)
    )


class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    """생성·수정 시각을 함께 갖는 조합.

    대부분의 도메인 테이블이 이 조합이다. 한쪽만 필요하면 ``CreatedAtMixin`` 또는
    ``UpdatedAtMixin`` 을 직접 쓴다.

    .. note::
       이전 버전의 ``TimestampMixin`` 은 ``created_at`` **만** 제공했다(이름과 내용이
       어긋나 있었다). 어떤 모델도 그것을 쓰지 않았으므로 스키마 영향은 없다.
    """


#: 옛 이름. 새 이름이 "무엇의 기본키인지"를 드러낸다.
UUIDMixin = UUIDPrimaryKeyMixin
