"""L3 — 연동 시나리오. 응답만이 아니라 DB·Redis 상태까지 본다."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from tests.e2e.conftest import (
    BASE_URL,
    HOST,
    PORTS,
    REPO_ROOT,
    USER_PASSWORD,
    AdminClient,
    Stack,
    bearer,
    login,
    register_and_login,
    unique,
    wait_for,
)
from tests.e2e.ledger import covers

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(600)]


def celery_client():
    from celery import Celery

    url = f"redis://{HOST}:{PORTS['redis']}/0"
    return Celery("e2e-client", broker=url, backend=url)


def _fam(refresh: str) -> str:
    return jwt.decode(refresh, options={"verify_signature": False})["fam"]


# ── 1. 인증 수명 주기 ─────────────────────────────────────────────────────
def test_auth_lifecycle_rotation_reuse_and_logout(stack: Stack, api: httpx.Client):
    user = register_and_login(api)
    redis = stack.redis()
    fam = _fam(user["refresh"])
    assert redis.sismember(f"auth:user:{user['id']}:fams", fam)

    rotated = api.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh"]})
    assert rotated.status_code == 200
    new = rotated.json()
    assert _fam(new["refresh_token"]) == fam, "회전은 같은 family 안에서 일어난다"
    assert api.get("/api/v1/auth/me", headers=bearer(new["access_token"])).status_code == 200

    # 이전 refresh 재사용 → 거부 + family 전체 폐기(새 refresh 도 죽는다)
    reused = api.post("/api/v1/auth/refresh", json={"refresh_token": user["refresh"]})
    assert reused.status_code == 401
    assert redis.exists(f"auth:fam:{fam}:revoked")
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code
        == 401
    )

    # 새로 로그인 → logout → 그 refresh 재사용 거부
    again = login(api, user["username"])
    assert (
        api.post("/api/v1/auth/logout", json={"refresh_token": again["refresh"]}).status_code == 204
    )
    assert (
        api.post("/api/v1/auth/refresh", json={"refresh_token": again["refresh"]}).status_code
        == 401
    )
    covers("scenario", "L3-1 인증 수명")


# ── 2. 레이트 리밋 ────────────────────────────────────────────────────────
@pytest.fixture
def tight_limits(stack: Stack):
    stack.start_app(
        AUTH_LOGIN_MAX_ATTEMPTS="3",
        AUTH_LOGIN_IP_MAX_ATTEMPTS="5",
        AUTH_LOGIN_WINDOW_SECONDS="4",
        AUTH_REGISTER_MAX_ATTEMPTS="2",
        AUTH_REGISTER_WINDOW_SECONDS="4",
    )
    stack.redis().delete(*stack.redis().keys("rl:*") or ["-"])
    yield
    stack.start_app()


def test_login_and_register_rate_limits_429_then_recover(stack: Stack, tight_limits):
    redis = stack.redis()
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        name = unique("rl")
        for _ in range(2):
            ok = api.post(
                "/api/v1/auth/register",
                json={
                    "username": unique("r"),
                    "email": f"{unique('r')}@example.com",
                    "password": USER_PASSWORD,
                },
            )
            assert ok.status_code == 201
        limited = api.post(
            "/api/v1/auth/register",
            json={"username": name, "email": f"{name}@example.com", "password": USER_PASSWORD},
        )
        assert limited.status_code == 429
        assert 1 <= int(limited.headers["retry-after"]) <= 4
        ttl = redis.ttl("rl:register:ip:127.0.0.1")
        assert 0 < ttl <= 4, ttl

        statuses = [
            api.post(
                "/api/v1/auth/login", data={"username": "nobody", "password": "wrong-password"}
            ).status_code
            for _ in range(4)
        ]
        assert statuses == [401, 401, 401, 429], statuses
        user_keys = redis.keys("rl:login:user:127.0.0.1:*")
        assert user_keys and 0 < redis.ttl(user_keys[0]) <= 4
        assert redis.get("rl:login:ip:127.0.0.1") == "4"

        # 창이 지나면 회복한다(고정 창 — 첫 hit 기준 4초).
        wait_for(
            lambda: not redis.exists("rl:register:ip:127.0.0.1"), 10, "가입 창이 만료되지 않았다"
        )
        assert (
            api.post(
                "/api/v1/auth/register",
                json={"username": name, "email": f"{name}@example.com", "password": USER_PASSWORD},
            ).status_code
            == 201
        )
        wait_for(
            lambda: not redis.keys("rl:login:user:127.0.0.1:*"), 10, "로그인 창이 만료되지 않았다"
        )
        assert (
            api.post(
                "/api/v1/auth/login", data={"username": name, "password": USER_PASSWORD}
            ).status_code
            == 200
        )
    covers("scenario", "L3-2 레이트 리밋")


# ── 3. 소유권 ─────────────────────────────────────────────────────────────
def test_ownership_flow_on_posts_and_replies(stack: Stack, api: httpx.Client, superuser):
    a, b = register_and_login(api), register_and_login(api)
    post = api.post(
        "/api/v1/blog/posts",
        json={"title": "A 의 글", "content": "본문"},
        headers=bearer(a["access"]),
    )
    post_id = post.json()["id"]
    assert (
        stack.sql("SELECT author_id FROM blog_posts WHERE id=%s", post_id)[0]["author_id"]
        == a["id"]
    )
    reply = api.post(
        "/api/v1/reply/replies",
        json={"content": "B 의 댓글", "post_id": post_id},
        headers=bearer(b["access"]),
    )
    reply_id = reply.json()["id"]

    assert (
        api.patch(
            f"/api/v1/blog/posts/{post_id}", json={"title": "B"}, headers=bearer(b["access"])
        ).status_code
        == 403
    )
    assert (
        api.delete(f"/api/v1/reply/replies/{reply_id}", headers=bearer(a["access"])).status_code
        == 403
    )
    assert (
        api.patch(
            f"/api/v1/blog/posts/{post_id}",
            json={"title": "본인 수정"},
            headers=bearer(a["access"]),
        ).status_code
        == 200
    )
    assert (
        api.patch(
            f"/api/v1/blog/posts/{post_id}",
            json={"title": "관리자 수정"},
            headers=bearer(superuser["access"]),
        ).status_code
        == 200
    )
    assert (
        stack.sql("SELECT title FROM blog_posts WHERE id=%s", post_id)[0]["title"] == "관리자 수정"
    )
    assert (
        api.delete(f"/api/v1/reply/replies/{reply_id}", headers=bearer(b["access"])).status_code
        == 204
    )
    assert (
        api.delete(f"/api/v1/blog/posts/{post_id}", headers=bearer(a["access"])).status_code == 204
    )
    assert not stack.sql("SELECT 1 FROM blog_posts WHERE id=%s", post_id)
    covers("scenario", "L3-3 소유권")


# ── 4. 사용자 변경과 세션 폐기 ────────────────────────────────────────────
@pytest.mark.parametrize(
    ("change", "revoked"),
    [
        ({"is_active": False}, True),
        ({"is_superuser": False}, True),
        ({"email": "renamed@example.com"}, False),
        ("delete", True),
    ],
    ids=["deactivate", "demote", "rename", "delete"],
)
def test_user_changes_revoke_refresh_and_admin_sessions(
    stack: Stack, api: httpx.Client, superuser, change, revoked
):
    name = unique("victim")
    assert stack.create_superuser(name, USER_PASSWORD).returncode == 0
    tokens = login(api, name)
    user_id = api.get("/api/v1/auth/me", headers=bearer(tokens["access"])).json()["id"]
    admin = AdminClient()
    try:
        assert admin.login(name).status_code == 302
        assert admin.is_logged_in()
        redis = stack.redis()
        assert redis.scard(f"admin:user_sessions:{user_id}") == 1

        if change == "delete":
            done = api.delete(f"/api/v1/user/users/{user_id}", headers=bearer(superuser["access"]))
        else:
            done = api.patch(
                f"/api/v1/user/users/{user_id}", json=change, headers=bearer(superuser["access"])
            )
        assert done.status_code in (200, 204), done.text

        refresh = api.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh"]}
        ).status_code
        assert (refresh == 401) is revoked, refresh
        assert (redis.scard(f"admin:user_sessions:{user_id}") == 0) is revoked
        # 이름만 바꾼 경우 관리 세션은 살아 있다. 나머지는 끊긴다.
        assert admin.is_logged_in() is (not revoked)
    finally:
        admin.close()
    covers("scenario", f"L3-4 {('delete' if change == 'delete' else next(iter(change)))}")


# ── 5. 접속 로그 → 조회 → 보존 삭제 ──────────────────────────────────────
def test_access_log_records_forwarded_ip_and_user(stack: Stack, superuser):
    stack.start_app(TRUSTED_PROXY_HOPS="1")
    try:
        with httpx.Client(base_url=BASE_URL, timeout=30) as api:
            user = register_and_login(api)
            # 사용자 ID 는 인증 의존성(get_current_principal)이 도는 라우트에서만 채워진다 — Public 라우트에
            # 토큰을 실어 보내도 남지 않는다(설계: DB 조회 없는 Principal 은 의존성이 만든다).
            marker = f"/api/v1/auth/me?probe={uuid.uuid4().hex}"
            response = api.get(
                marker, headers={**bearer(user["access"]), "X-Forwarded-For": "203.0.113.7"}
            )
            assert response.status_code == 200
            row = wait_for(
                lambda: stack.sql(
                    "SELECT ip_address, forwarded_for, user_id, request_path, query_string, response_status "
                    "FROM user_access_logs WHERE query_string LIKE %s",
                    (f"%{marker.rsplit('=', 1)[1]}%",),
                ),
                15,
                "접속 로그가 적재되지 않았다",
            )[0]
            assert row["ip_address"] == "203.0.113.7"
            assert row["forwarded_for"] == "203.0.113.7"
            assert row["user_id"] == user["id"]
            assert (row["request_path"], row["response_status"]) == ("/api/v1/auth/me", 200)

            stack.wait_replicated("user_access_logs", "ip_address=%s", ("203.0.113.7",))
            by_ip = api.get(
                "/api/v1/home/access-logs/by-ip/203.0.113.7", headers=bearer(superuser["access"])
            )
            assert any(item["user_id"] == user["id"] for item in by_ip.json())
            by_user = api.get(
                f"/api/v1/home/access-logs/by-user/{user['id']}",
                headers=bearer(superuser["access"]),
            )
            assert any(item["ip_address"] == "203.0.113.7" for item in by_user.json())
    finally:
        stack.start_app()
    covers("scenario", "L3-5 접속 로그 적재·조회")


def test_retention_purge_task_runs_on_the_worker_in_batches(stack: Stack):
    """보존 365일 경계 — 366일 전 행은 지우고 364일 전 행은 남긴다. 12,000행은 5,000행 배치를 세 번 돈다."""
    tag = unique("purge")
    now = datetime.now(UTC).replace(tzinfo=None)
    old, fresh = now - timedelta(days=366), now - timedelta(days=364)
    stack.sql("SET GLOBAL cte_max_recursion_depth = 20000", root=True)
    stack.sql(
        "INSERT INTO user_access_logs (id, ip_address, request_path, request_method, is_bot, user_agent, created_at) "
        "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 12000) "
        "SELECT UUID(), '198.51.100.1', '/old', 'GET', 0, %s, %s FROM seq",
        (tag, old),
    )
    stack.sql(
        "INSERT INTO user_access_logs (id, ip_address, request_path, request_method, is_bot, user_agent, created_at) "
        "VALUES (UUID(), '198.51.100.2', '/fresh', 'GET', 0, %s, %s)",
        (tag, fresh),
    )
    result = celery_client().send_task("home.purge_expired_access_logs").get(timeout=120)
    assert result >= 12000
    left = stack.sql("SELECT request_path FROM user_access_logs WHERE user_agent=%s", (tag,))
    assert [r["request_path"] for r in left] == ["/fresh"]
    logs = (stack.run_dir / "logs" / "celery.log").read_text("utf-8")
    assert "접속 로그 보존 삭제: deleted=" in logs
    covers("task:home.purge_expired_access_logs", "실행")
    covers("scenario", "L3-5 보존 삭제")


# ── 7. Celery 왕복·beat 등록 ──────────────────────────────────────────────
def test_celery_task_round_trip_through_the_worker(stack: Stack):
    total = stack.sql("SELECT COUNT(*) AS n FROM user_access_logs")[0]["n"]
    result = celery_client().send_task("home.aggregate_access_stats").get(timeout=60)
    assert result["total"] >= 0 and abs(result["total"] - total) < 1000
    assert stack.redis().keys("celery-task-meta-*"), "결과 백엔드에 결과가 없다"
    covers("task:home.aggregate_access_stats", "실행")
    covers("redis:celery", "broker·backend")


def test_beat_registers_the_purge_schedule_and_logs_to_its_own_file(stack: Stack):
    import subprocess
    import sys

    out = stack.run_dir / "beat.out"
    schedule = stack.run_dir / "beat-schedule"
    launcher = [sys.executable, "-X", "utf8", "-m", "celery"]
    with out.open("wb") as sink:
        beat = subprocess.Popen(  # noqa: S603 - 인터프리터 고정
            [*launcher, "-A", "app.celery.app", "beat", "--loglevel=DEBUG", "-s", str(schedule)],
            cwd=stack.run_dir,
            # beat 는 일정 목록을 DEBUG 로 남긴다 — celery 헤더만 DEBUG 로 내린다(LOG_APP_LEVELS).
            env=stack.app_env(
                LOG_APP_LEVELS="celery=DEBUG", LOG_FILE_LEVEL="DEBUG", LOG_CONSOLE_LEVEL="DEBUG"
            ),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for(
                lambda: b"home.purge_expired_access_logs" in out.read_bytes(),
                60,
                "beat 가 일정을 읽지 않았다",
            )
        finally:
            stack._stop(beat)
    stack.outputs.append(out)
    beat_log = (stack.run_dir / "logs" / "celery-beat.log").read_text("utf-8")
    assert "beat: Starting" in beat_log
    assert "home.purge_expired_access_logs" in beat_log
    covers("beat:home.purge_expired_access_logs", "등록")
    assert REPO_ROOT  # 실행 디렉터리는 저장소 밖이다 — .env 를 읽지 않는다


# ── 8. 읽기/쓰기 분리 ────────────────────────────────────────────────────
def test_reads_go_to_replica_and_writes_to_primary(stack: Stack, api: httpx.Client):
    """replica 에만 있는 행이 API 조회에 보이면 읽기는 replica 로 갔다. 그 행을 수정하면 404 — 쓰기는 primary 다."""
    user = register_and_login(api)
    only_replica = str(uuid.uuid4())
    stack.sql(
        "INSERT INTO blog_posts (id, title, content, author_id, created_at, updated_at) "
        "VALUES (%s, 'replica-only', 'x', %s, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))",
        (only_replica, user["id"]),
        target="replica",
        root=True,
    )
    try:
        assert (
            api.get(f"/api/v1/blog/posts/{only_replica}").status_code == 200
        ), "읽기가 replica 로 가지 않았다"
        patched = api.patch(
            f"/api/v1/blog/posts/{only_replica}",
            json={"title": "x"},
            headers=bearer(user["access"]),
        )
        assert patched.status_code == 404, "쓰기 경로가 replica 를 봤다"
    finally:
        stack.sql(
            "DELETE FROM blog_posts WHERE id=%s", (only_replica,), target="replica", root=True
        )
    covers("scenario", "L3-8 replica 읽기")


def test_write_then_read_consistency_under_replication_lag(stack: Stack, api: httpx.Client):
    """복제를 멈추고 쓰면 — 쓰기 응답(primary)은 새 값, 다음 요청의 읽기(replica)는 아직 없다(요청 간 sticky 없음)."""
    user = register_and_login(api)
    stack.sql("STOP REPLICA SQL_THREAD", target="replica", root=True)
    try:
        created = api.post(
            "/api/v1/blog/posts",
            json={"title": "lag", "content": "x"},
            headers=bearer(user["access"]),
        )
        assert created.status_code == 201 and created.json()["title"] == "lag"
        post_id = created.json()["id"]
        assert api.get(f"/api/v1/blog/posts/{post_id}").status_code == 404
        updated = api.patch(
            f"/api/v1/blog/posts/{post_id}", json={"title": "lag-2"}, headers=bearer(user["access"])
        )
        assert (
            updated.status_code == 200 and updated.json()["title"] == "lag-2"
        ), "쓰기 직후 같은 요청의 읽기는 primary 다"
    finally:
        stack.sql("START REPLICA SQL_THREAD", target="replica", root=True)
    wait_for(
        lambda: api.get(f"/api/v1/blog/posts/{post_id}").status_code == 200,
        20,
        "복제 재개 후에도 안 보인다",
    )
    assert api.get(f"/api/v1/blog/posts/{post_id}").json()["title"] == "lag-2"
    covers("scenario", "L3-8 sticky·지연")
