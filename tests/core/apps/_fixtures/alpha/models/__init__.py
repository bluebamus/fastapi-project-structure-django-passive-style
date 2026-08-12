"""alpha fixture 모델.

선언 base 를 이 모듈 안에서 만든다 — 테스트가 fixture 앱을 재import 할 때마다
새 ``MetaData`` 가 생기므로 "테이블이 이미 정의됨" 충돌이 없고, 실제 앱의
``Base.metadata`` 도 오염되지 않는다.
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tests.core.apps._fixtures.eventlog import record


class FixtureBase(DeclarativeBase):
    """이 fixture 앱 전용 declarative base."""


class AlphaThing(FixtureBase):
    __tablename__ = "fixture_alpha_thing"

    id: Mapped[int] = mapped_column(primary_key=True)


record("models", "alpha")
