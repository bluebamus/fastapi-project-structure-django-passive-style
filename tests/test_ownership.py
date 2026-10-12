"""작성자 소유권 — blog·sns·reply 공통 (service-hardening ADR-018 · ledger F-022).

세 기능은 같은 정책을 따른다: 생성은 인증, 작성자(``author_id``·``author``)는 서버가 채우고,
수정·삭제는 소유자 또는 슈퍼유저. 소유자 기록 이전의 행(``author_id`` NULL)은 슈퍼유저만
수정한다. 판정은 core ``OwnershipPolicy`` 한 곳이다 — 단위 테스트도 여기 둔다.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.exception import ForbiddenException
from app.core.security import OwnershipPolicy, Principal
from app.features.blog.models.models import Post
from app.features.reply.models.models import Reply
from app.features.sns.models.models import SnsPost
from main import app
from tests.auth_headers import USER_ID, admin_headers, other_headers, user_headers
from tests.session_overrides import sqlite_session_overrides

# ---------------------------------------------------------------------------
# OwnershipPolicy 단위
# ---------------------------------------------------------------------------
_OWNER = Principal(id="u1", username="owner", is_superuser=False)
_STRANGER = Principal(id="u2", username="stranger", is_superuser=False)
_ROOT = Principal(id="r1", username="root", is_superuser=True)


def test_owner_may_modify():
    OwnershipPolicy().ensure_can_modify("u1", _OWNER)


def test_superuser_may_modify_anything():
    OwnershipPolicy().ensure_can_modify("u1", _ROOT)
    OwnershipPolicy().ensure_can_modify(None, _ROOT)


@pytest.mark.parametrize("owner_id", ["u1", None], ids=["someone-else", "no-owner-recorded"])
def test_non_owner_is_forbidden(owner_id):
    with pytest.raises(ForbiddenException):
        OwnershipPolicy().ensure_can_modify(owner_id, _STRANGER)


def test_principal_is_immutable():
    with pytest.raises(AttributeError):
        _OWNER.is_superuser = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------
class Resource(NamedTuple):
    name: str
    collection: str
    model: type
    create: dict
    update: dict


RESOURCES = [
    Resource("blog", "/api/v1/blog/posts", Post, {"title": "t", "content": "c"}, {"title": "n"}),
    Resource("sns", "/api/v1/sns/posts", SnsPost, {"content": "c"}, {"content": "n"}),
    Resource("reply", "/api/v1/reply/replies", Reply, {"content": "c"}, {"content": "n"}),
]


@pytest.fixture(params=RESOURCES, ids=lambda r: r.name)
def resource(request) -> Resource:
    return request.param


@pytest_asyncio.fixture
async def env():
    async with sqlite_session_overrides(app) as maker:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, maker


async def _create_as_user(client: AsyncClient, resource: Resource) -> dict:
    resp = await client.post(
        resource.collection,
        json={**resource.create, "author": "spoofed", "author_id": "spoofed-id"},
        headers=user_headers(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_requires_a_token(env, resource):
    client, _ = env
    resp = await client.post(resource.collection, json=resource.create)
    assert resp.status_code == 401


async def test_author_is_filled_by_the_server(env, resource):
    """본문의 author·author_id 는 무시되고 인증 주체로 채워진다(IDOR 방지)."""
    client, _ = env
    body = await _create_as_user(client, resource)

    assert (body["author_id"], body["author"]) == (USER_ID, "alice")


async def test_owner_can_update_and_delete(env, resource):
    client, _ = env
    item = await _create_as_user(client, resource)
    url = f"{resource.collection}/{item['id']}"

    patched = await client.patch(url, json=resource.update, headers=user_headers())
    deleted = await client.delete(url, headers=user_headers())

    assert (patched.status_code, deleted.status_code) == (200, 204)


async def test_someone_else_cannot_update_or_delete(env, resource):
    client, _ = env
    item = await _create_as_user(client, resource)
    url = f"{resource.collection}/{item['id']}"

    patched = await client.patch(url, json=resource.update, headers=other_headers())
    deleted = await client.delete(url, headers=other_headers())

    assert (patched.status_code, deleted.status_code) == (403, 403)
    assert (await client.get(url)).status_code == 200, "거부된 삭제가 행을 지웠다"


async def test_superuser_bypasses_ownership(env, resource):
    client, _ = env
    item = await _create_as_user(client, resource)
    url = f"{resource.collection}/{item['id']}"

    patched = await client.patch(url, json=resource.update, headers=admin_headers())
    deleted = await client.delete(url, headers=admin_headers())

    assert (patched.status_code, deleted.status_code) == (200, 204)


async def test_rows_without_an_owner_are_superuser_only(env, resource):
    """인가 리비전 이전에 만든 행(author_id NULL)은 일반 사용자가 고칠 수 없다."""
    client, maker = env
    async with maker() as session:
        row = resource.model(**resource.create)
        session.add(row)
        await session.commit()
        row_id = row.id
    url = f"{resource.collection}/{row_id}"

    as_user = await client.patch(url, json=resource.update, headers=user_headers())
    as_admin = await client.patch(url, json=resource.update, headers=admin_headers())

    assert (as_user.status_code, as_admin.status_code) == (403, 200)


async def test_missing_resource_is_404_before_ownership(env, resource):
    client, _ = env
    resp = await client.patch(
        f"{resource.collection}/missing", json=resource.update, headers=user_headers()
    )
    assert resp.status_code == 404
