"""공개 엔드포인트 인벤토리 고정 (계획서 Phase 0 — 안전망).

이 저장소가 노출하는 HTTP 표면 전체를 한곳에 적어두고, 실제와 어긋나면 실패한다.

**왜 필요한가.** 이 저장소의 라우터는 `INSTALLED_APPS` + 네이밍 컨벤션으로
결선된다. 편리한 대신, 앱을 목록에서 빼거나 라우터 변수명을 바꾸면 엔드포인트가
**조용히 사라지고** 아무 테스트도 실패하지 않는다. 반대로 새 앱을 등록하면
엔드포인트가 조용히 생긴다 — 인증을 빠뜨린 채로도.

같은 종류의 침묵이 이미 한 번 사고를 냈다: 마이그레이션이 테이블 4개를 빠뜨렸는데
테스트 146개가 전부 green 이었다(하니스가 create_all 을 쓰기 때문). 그래서 "무엇이
있어야 하는가" 를 코드 밖에 적어둔다.

인증이 걸려야 하는 대상은 ``test_admin_api_auth.py``, Admin 화면은
``test_admin_wiring.py``, DB 테이블은 ``test_migration_chain.py`` 가 같은 방식으로
고정한다.
"""

from fastapi.routing import APIRoute

from app.core.bootstrap import create_app

# (HTTP 메서드, 경로) — 이 목록이 곧 공개 계약이다.
# 엔드포인트를 의도적으로 추가·삭제할 때만 이 목록을 함께 고친다.
EXPECTED_ENDPOINTS = {
    # 헬스체크
    ("GET", "/health"),
    # home — 접속 로그 (전부 관리자 전용)
    ("GET", "/api/v1/home/access-logs"),
    ("GET", "/api/v1/home/access-logs/recent"),
    ("GET", "/api/v1/home/access-logs/stats"),
    ("GET", "/api/v1/home/access-logs/by-ip/{ip_address}"),
    ("GET", "/api/v1/home/access-logs/by-user/{user_id}"),
    # user — 사용자 CRUD (전부 관리자 전용)
    ("POST", "/api/v1/user/users"),
    ("GET", "/api/v1/user/users"),
    ("GET", "/api/v1/user/users/{user_id}"),
    ("PATCH", "/api/v1/user/users/{user_id}"),
    ("DELETE", "/api/v1/user/users/{user_id}"),
    # blog
    ("POST", "/api/v1/blog/posts"),
    ("GET", "/api/v1/blog/posts"),
    ("GET", "/api/v1/blog/posts/{post_id}"),
    ("PATCH", "/api/v1/blog/posts/{post_id}"),
    ("DELETE", "/api/v1/blog/posts/{post_id}"),
    # reply
    ("POST", "/api/v1/reply/replies"),
    ("GET", "/api/v1/reply/replies"),
    ("GET", "/api/v1/reply/replies/{reply_id}"),
    ("PATCH", "/api/v1/reply/replies/{reply_id}"),
    ("DELETE", "/api/v1/reply/replies/{reply_id}"),
    # sns
    ("POST", "/api/v1/sns/posts"),
    ("GET", "/api/v1/sns/posts"),
    ("GET", "/api/v1/sns/posts/{post_id}"),
    ("PATCH", "/api/v1/sns/posts/{post_id}"),
    ("DELETE", "/api/v1/sns/posts/{post_id}"),
}

# DEBUG=true 에서만 붙는 문서 라우트 (테스트 환경은 DEBUG=true)
_DEBUG_ONLY = {("GET", "/docs")}


def _actual_endpoints() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in create_app().routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "HEAD"
    }


def test_endpoint_inventory_is_exact():
    actual = _actual_endpoints() - _DEBUG_ONLY

    added = actual - EXPECTED_ENDPOINTS
    removed = EXPECTED_ENDPOINTS - actual

    assert not added, (
        f"목록에 없는 엔드포인트가 노출되고 있습니다: {sorted(added)}\n"
        "의도한 추가라면 EXPECTED_ENDPOINTS 에 넣고, 인증이 필요한지 "
        "test_admin_api_auth.py 도 함께 확인하세요."
    )
    assert not removed, (
        f"있어야 할 엔드포인트가 사라졌습니다: {sorted(removed)}\n"
        "INSTALLED_APPS 등록 누락이나 라우터 변수명 변경일 수 있습니다."
    )


def test_every_installed_app_contributes_routes():
    """등록된 앱이 실제로 라우터를 붙였는지 본다.

    AppRegistry.install_routers 는 라우터가 없는 앱을 경고만 남기고 건너뛴다.
    그 경고는 아무도 읽지 않는다.
    """
    from config import INSTALLED_APPS

    paths = {path for _, path in _actual_endpoints()}
    for name in INSTALLED_APPS:
        assert any(f"/api/v1/{name}/" in path for path in paths), (
            f"INSTALLED_APPS 의 '{name}' 앱이 라우터를 하나도 붙이지 않았습니다."
        )
