"""관리자 전용 API 접근 제어 테스트 (계획서 P0-3 + 발견 U-1).

두 묶음의 엔드포인트가 인증 없이 열려 있었다:

- 접속로그 조회 5개 — IP·사용자 ID·요청 경로·접속 시각·브라우저 정보를 반환한다.
  IP 와 사용자 ID 의 결합은 개인정보이자 보안 감사 데이터다.
- 사용자 CRUD 5개 — 계정 열거와 임의 삭제가 가능했다.

이 저장소에는 자격증명 저장소가 없다(User 모델에 비밀번호 컬럼이 없고 해싱·토큰
의존성도 없다). 로그인 제품은 범위 밖이므로(계획서 §9), 설정에 둔 단일 Bearer
토큰으로 보호한다. **미설정이면 전부 거부**한다 — 설정을 잊은 배포가 곧 공개
상태가 되는 것을 막는다.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.utils.authenticator import require_admin

_TOKEN = "test-admin-token"  # noqa: S105 - 실제 자격증명이 아니라 테스트 고정값

# 인증이 걸려야 하는 모든 엔드포인트 (경로, 메서드).
# 새 엔드포인트가 보호 없이 추가되면 이 목록과 실제가 어긋나므로,
# 아래 test_protected_inventory_matches_app 이 그 침묵을 막는다.
PROTECTED = [
    ("GET", "/api/v1/home/access-logs"),
    ("GET", "/api/v1/home/access-logs/recent"),
    ("GET", "/api/v1/home/access-logs/by-ip/1.2.3.4"),
    ("GET", "/api/v1/home/access-logs/by-user/some-id"),
    ("GET", "/api/v1/home/access-logs/stats"),
    ("GET", "/api/v1/user/users"),
    ("POST", "/api/v1/user/users"),
    ("GET", "/api/v1/user/users/some-id"),
    ("PATCH", "/api/v1/user/users/some-id"),
    ("DELETE", "/api/v1/user/users/some-id"),
]


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def configured(monkeypatch):
    """관리자 토큰이 설정된 상태."""
    from app.utils.authenticator import auth

    monkeypatch.setattr(auth.app_settings, "ADMIN_API_TOKEN", SecretStr(_TOKEN))


# ---------------------------------------------------------------------------
# Dependency 단위
# ---------------------------------------------------------------------------


def test_missing_credentials_are_rejected(configured):
    with pytest.raises(HTTPException) as exc:
        require_admin(None)
    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_token_is_rejected(configured):
    with pytest.raises(HTTPException) as exc:
        require_admin(_credentials("wrong-token"))
    assert exc.value.status_code == 401


def test_correct_token_is_accepted(configured):
    require_admin(_credentials(_TOKEN))  # 예외 없이 통과


def test_everything_is_rejected_when_token_not_configured(monkeypatch):
    """설정을 잊은 배포가 곧 공개 상태가 되면 안 된다(fail-closed)."""
    from app.utils.authenticator import auth

    monkeypatch.setattr(auth.app_settings, "ADMIN_API_TOKEN", None)

    with pytest.raises(HTTPException) as exc:
        require_admin(_credentials("anything"))
    assert exc.value.status_code == 401


def test_empty_token_counts_as_unconfigured(monkeypatch):
    """`.env` 에 `ADMIN_API_TOKEN=` 만 적힌 경우도 미설정으로 본다."""
    from app.utils.authenticator import auth

    monkeypatch.setattr(auth.app_settings, "ADMIN_API_TOKEN", SecretStr(""))

    with pytest.raises(HTTPException) as exc:
        require_admin(_credentials(""))
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# 진입점 매트릭스 — 앱 전체에서 실제로 막히는지
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from app.core.bootstrap import create_app

    return TestClient(create_app())


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_endpoints_reject_anonymous(client, configured, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} 가 익명 요청을 통과시켰다"


def test_protected_inventory_matches_app(client):
    """보호 목록이 실제 앱의 해당 라우터 엔드포인트를 빠짐없이 덮는지 확인한다.

    새 엔드포인트를 인증 없이 추가하면 여기서 걸린다 — 목록만 보고 안심하는 것을
    막는 검사다.
    """
    from fastapi.routing import APIRoute

    listed = {(m, p) for m, p in PROTECTED}
    actual = {
        (method, route.path)
        for route in client.app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method != "HEAD"
        and (
            route.path.startswith("/api/v1/home/access-logs")
            or route.path.startswith("/api/v1/user/users")
        )
    }

    # 경로 파라미터 표기 차이를 흡수해 개수로 비교한다
    assert len(actual) == len(listed), (
        f"보호 대상 엔드포인트 수가 다르다 — 앱 {len(actual)}개 / 목록 {len(listed)}개\n"
        f"앱: {sorted(actual)}"
    )
