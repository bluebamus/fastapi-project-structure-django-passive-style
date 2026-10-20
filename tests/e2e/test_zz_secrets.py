"""L6-4 — 비밀값 grep. 이번 실행이 만든 비밀번호·키·발급 토큰이 어떤 로그에도 원문으로 없다.

마지막에 돈다(파일 이름 ``zz``). 대상: uvicorn·Celery worker·beat·스크립트 출력, 프로세스별 로그 파일,
compose 컨테이너 로그(MySQL·Redis).
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import USER_PASSWORD, Stack
from tests.e2e.ledger import ISSUED_TOKENS

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(300)]


def test_no_secret_appears_in_any_log(stack: Stack):
    secrets = {**stack.secrets, "USER_PASSWORD": USER_PASSWORD}
    secrets.update({f"token#{i}": token for i, token in enumerate(sorted(ISSUED_TOKENS))})
    corpus = {
        path.name: path.read_text("utf-8", "replace")
        for path in stack.log_files()
        if path.is_file()
    }
    for service in ("mysql-primary", "mysql-replica", "redis"):
        corpus[f"compose:{service}"] = stack.compose("logs", "--no-color", service, check=False)
    assert (
        sum(len(text) for text in corpus.values()) > 10_000
    ), "검사할 로그가 거의 없다 — 헛통과 방지"
    assert len(ISSUED_TOKENS) > 20, "발급 토큰이 기록되지 않았다 — 헛통과 방지"
    leaks = sorted(
        f"{name} ⊃ {label}"
        for label, value in secrets.items()
        for name, text in corpus.items()
        if value and value in text
    )
    assert not leaks, leaks
