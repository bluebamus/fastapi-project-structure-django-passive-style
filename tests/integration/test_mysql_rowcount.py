"""MySQL 방언 확인 — UPDATE rowcount 의 의미 (Phase 3a · ledger F-021).

MySQL 서버는 UPDATE 에 **값이 바뀐** 행 수를 돌려주는 것이 기본이다. 그래서 같은 값으로
덮어쓰는 no-op PATCH 는 0 이 될 수 있고, 그 0 을 "행이 없다"로 읽으면 존재하는 리소스가
404 가 된다.

다만 **실측 결과 이 스택에서는 1 이 나온다** — aiomysql/PyMySQL 이 접속 시
``CLIENT_FOUND_ROWS`` 를 켜서 "매칭된 행 수"를 세기 때문이다(2026-08-19 확인). 즉 지금
당장 404 가 나지는 않는다.

그래서 이 테스트들이 고정하는 것은 "rowcount 가 몇이냐"가 아니라 **Repository 가 그 값에
의존하지 않는다**는 것이다. 드라이버를 바꾸거나 접속 플래그가 달라지면 rowcount 의 의미가
조용히 뒤집히는데, 그때 존재하는 리소스가 404 로 사라지는 것을 코드가 아니라 설정이
결정하게 두지 않는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.repositories.repository_base import BaseRepository
from app.features.blog.models.models import Post

pytestmark = pytest.mark.mysql


class PostRepository(BaseRepository[Post]):
    model = Post


@pytest.mark.asyncio
async def test_unchanged_update_rowcount_is_driver_dependent(mysql_session_maker):
    """rowcount 의 의미가 드라이버 설정에 달렸음을 기록한다.

    현재 스택(aiomysql, CLIENT_FOUND_ROWS)에서는 매칭된 행 수인 1 이 나온다. 서버
    기본 동작이라면 0 이다. **어느 쪽이든** Repository 가 존재 여부를 이 값으로
    판단해서는 안 된다는 것이 요점이다.
    """
    async with mysql_session_maker() as session:
        await session.execute(
            text(
                "INSERT INTO blog_posts (id, title, content, author, created_at, updated_at) "
                "VALUES (:id, :title, :content, NULL, NOW(), NOW())"
            ),
            {"id": "rowcount-probe", "title": "제목", "content": "본문"},
        )
        await session.commit()

        result = await session.execute(
            text("UPDATE blog_posts SET title = :title WHERE id = :id"),
            {"id": "rowcount-probe", "title": "제목"},  # 같은 값
        )
        # 값은 환경에 따라 0(변경된 행) 또는 1(매칭된 행)이다. 둘 다 정상이며,
        # 그래서 이 값으로 존재 여부를 판단할 수 없다.
        assert result.rowcount in (0, 1)


@pytest.mark.asyncio
async def test_no_op_patch_is_not_a_404_on_mysql(mysql_session_maker):
    """값이 그대로인 PATCH 가 404 로 둔갑하지 않는다.

    Repository 가 rowcount 로 존재 여부를 판단하면, 그 값이 0 이 되는 설정에서
    존재하는 리소스에 404 를 돌려준다. 조회로 판단하면 설정과 무관하게 옳다.
    """
    async with mysql_session_maker() as session:
        repo = PostRepository(session)
        created = await repo.create({"title": "그대로", "content": "본문"})
        await session.commit()

        updated = await repo.update(created.id, {"title": "그대로"})  # 같은 값

        assert updated is not None, "MySQL 에서 no-op PATCH 가 404 로 취급됐다"
        assert updated.id == created.id
        assert updated.title == "그대로"


@pytest.mark.asyncio
async def test_missing_row_still_returns_none_on_mysql(mysql_session_maker):
    """진짜 없는 행은 None — 404 의 의미는 유지된다."""
    async with mysql_session_maker() as session:
        repo = PostRepository(session)

        assert await repo.update("없는-id", {"title": "x"}) is None
