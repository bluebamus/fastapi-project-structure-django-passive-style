"""Phase 2 — 공통 필드 Mixin 계약 (development-plan Phase 2).

이 단계의 완료 조건은 **"겉으로는 아무것도 바뀌지 않는다"** 다. 그래서 여기서 보는
것은 Mixin 이 예쁘게 쪼개졌는가가 아니라, 쪼갠 결과가 **원래와 같은 스키마**를
만드는가다.

특히 컬럼 순서를 본다. Alembic 은 컬럼을 이름으로 비교해 순서 차이를 diff 로 잡지
않는다 — 그래서 순서가 어긋나도 `alembic check` 는 통과하고, ``create_all`` 로 만든
개발 DB 와 migration 으로 만든 운영 DB 가 **아무 경고 없이** 갈린다.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import DeclarativeBase

from app.core.models.models_base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UpdatedAtMixin,
    UUIDMixin,
    UUIDPrimaryKeyMixin,
)

#: Phase 2 이전의 실제 컬럼 배치. MySQL 8.4 에 ``create_all`` 로 만든 테이블의
#: ``SHOW CREATE TABLE`` 에서 그대로 옮겼다(2026-08-19 측정).
EXPECTED_COLUMN_ORDER = {
    "blog_posts": ["id", "title", "content", "author", "created_at", "updated_at"],
    "replies": ["id", "content", "author", "post_id", "created_at", "updated_at"],
    "sns_posts": ["id", "content", "author", "like_count", "created_at", "updated_at"],
    "users": [
        "id",
        "username",
        "email",
        "hashed_password",
        "is_active",
        "created_at",
        "updated_at",
    ],
}


def _table(name: str):
    from app.core.apps import apps
    from config import INSTALLED_APPS

    apps.populate(INSTALLED_APPS, run_ready=False)
    return Base.metadata.tables[name]


@pytest.mark.parametrize("table_name", sorted(EXPECTED_COLUMN_ORDER))
def test_mixin_columns_keep_their_original_position(table_name: str):
    """Mixin 으로 옮긴 뒤에도 컬럼 배치가 그대로다 (id → 도메인 → created → updated).

    ``sort_order`` 를 빼면 mixin 컬럼이 모델 자신의 컬럼 **뒤로** 밀려 id 가 중간에
    끼어든다. 그 상태는 `alembic check` 를 통과하므로 테스트가 없으면 못 잡는다.
    """
    columns = [column.name for column in _table(table_name).columns]
    assert columns == EXPECTED_COLUMN_ORDER[table_name]


def test_access_log_has_no_updated_at():
    """한 번 쓰고 고치지 않는 테이블은 ``updated_at`` 을 갖지 않는다.

    Mixin 을 하나로 묶어두면 이런 테이블이 쓰지도 않는 컬럼을 떠안는다 — 그래서
    책임 단위로 쪼갰다.
    """
    columns = [column.name for column in _table("user_access_logs").columns]

    assert "created_at" in columns
    assert "updated_at" not in columns
    assert columns[0] == "id"
    assert columns[-1] == "created_at"


def test_every_managed_model_uses_the_uuid_mixin():
    """Repository 가 다루는 모델은 전부 문자열 UUID 기본키다 (Base 의 불변식)."""
    from app.core.apps import apps
    from config import INSTALLED_APPS

    apps.populate(INSTALLED_APPS, run_ready=False)
    models = apps.get_models()
    assert models, "registry 에 모델이 없다 — 검사가 헛통과한다"

    offenders = [model.__name__ for model in models if not issubclass(model, UUIDPrimaryKeyMixin)]
    assert not offenders, f"UUIDPrimaryKeyMixin 을 쓰지 않는 모델: {offenders}"


def test_mixins_are_composable_independently():
    """세 Mixin 을 따로 조합할 수 있다 — 이게 쪼갠 이유다.

    application metadata 를 더럽히지 않도록 **별도 Base** 로 만든다(Phase 2 규칙).
    """

    class _IsolatedBase(DeclarativeBase):
        pass

    class _OnlyCreated(_IsolatedBase, UUIDPrimaryKeyMixin, CreatedAtMixin):
        __tablename__ = "probe_only_created"

    class _OnlyUpdated(_IsolatedBase, UUIDPrimaryKeyMixin, UpdatedAtMixin):
        __tablename__ = "probe_only_updated"

    class _Both(_IsolatedBase, UUIDPrimaryKeyMixin, TimestampMixin):
        __tablename__ = "probe_both"

    assert [c.name for c in _OnlyCreated.__table__.columns] == ["id", "created_at"]
    assert [c.name for c in _OnlyUpdated.__table__.columns] == ["id", "updated_at"]
    assert [c.name for c in _Both.__table__.columns] == ["id", "created_at", "updated_at"]

    # 테스트용 모델이 실제 애플리케이션 metadata 에 새어 들어가지 않았는지 확인한다.
    assert "probe_both" not in Base.metadata.tables


def test_timestamp_mixin_now_carries_both_columns():
    """``TimestampMixin`` 은 생성·수정 시각을 **함께** 갖는다.

    이전 버전은 이름과 달리 ``created_at`` 만 있었다. 어떤 모델도 쓰지 않았으므로
    스키마 영향은 없지만, 이름과 내용이 어긋난 채로 두면 다음 사람이 그대로 믿는다.
    """
    assert issubclass(TimestampMixin, CreatedAtMixin)
    assert issubclass(TimestampMixin, UpdatedAtMixin)


def test_old_uuid_mixin_name_is_the_same_class():
    """옛 이름은 같은 클래스다 — 상속 체인이 갈라지면 isinstance 검사가 깨진다."""
    assert UUIDMixin is UUIDPrimaryKeyMixin


def test_timestamp_defaults_come_from_the_app_not_the_database():
    """시각은 **애플리케이션이** 넣는다.

    DB 의 ``CURRENT_TIMESTAMP`` 를 쓰면 값이 DB 서버 타임존에 좌우된다 — 서버를
    옮기면 조용히 달라지고, 그때는 이미 쌓인 데이터가 섞여 있다.
    """
    for table_name in ("blog_posts", "users"):
        table = _table(table_name)
        for column_name in ("created_at", "updated_at"):
            column = table.columns[column_name]
            assert column.default is not None, f"{table_name}.{column_name} 에 기본값이 없다"
            assert (
                column.server_default is None
            ), f"{table_name}.{column_name} 이 DB 서버 시각을 쓴다"
