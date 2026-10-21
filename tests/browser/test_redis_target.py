"""브라우저 하네스의 Redis 대상은 명시해야 한다 (integration-e2e W0).

자식 서버(uvicorn·``scripts.create_superuser``)가 어느 Redis 에 붙을지는 ``server_env()`` 가 정한다.
기본 포트로 떨어지면 개발 머신에 떠 있는 **남의** Redis 에 붙는다 — 실제로 그런 사고가 있었다.
그래서 ``REDIS_HOST``·``REDIS_PORT`` 가 환경에 없으면 접속을 시도하기 전에 실패한다.

이 파일에는 ``browser`` 마커가 없다 — 접속하지 않는 검사라 단위 게이트에서 돈다.
"""

from __future__ import annotations

import pytest

from tests.browser.conftest import server_env


@pytest.mark.parametrize("missing", ["REDIS_HOST", "REDIS_PORT"])
def test_server_env_fails_without_explicit_redis_target(monkeypatch, missing):
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "16393")
    monkeypatch.delenv(missing)

    with pytest.raises(pytest.fail.Exception, match=missing):
        server_env()


def test_server_env_passes_explicit_redis_target_to_child(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "16393")
    monkeypatch.setenv("REDIS_TEST_PORT", "6380")

    env = server_env()

    assert (env["REDIS_HOST"], env["REDIS_PORT"], env["REDIS_PASSWORD"]) == (
        "127.0.0.1",
        "16393",
        "",
    )
