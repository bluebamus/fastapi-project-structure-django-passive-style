"""하네스 자체의 계약 — 접속 대상 검사·복제·기동 상태."""

from __future__ import annotations

import pytest

from tests.e2e.conftest import PORTS, Stack, verify_local_targets, wait_for
from tests.e2e.ledger import covers

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(300)]


@pytest.mark.parametrize(
    "override",
    [
        {"MYSQL_HOST": "115.68.199.140"},
        {"MYSQL_PORT": "3306"},
        {"REDIS_PORT": "6379"},
        {"REDIS_HOST": "localhost"},
        {"MYSQL_REPLICA_HOSTS": '["10.0.0.5"]'},
        {"MYSQL_REPLICA_PORT": "3309"},
    ],
)
def test_harness_refuses_non_local_targets(stack: Stack, override):
    env = {**stack.app_env(), **override}
    with pytest.raises(pytest.exit.Exception):
        verify_local_targets(env)


def test_ready_and_replication_are_live(stack: Stack, api):
    assert api.get("/health").status_code == 200
    assert api.get("/ready").json() == {"status": "ready"}
    status = stack.sql("SHOW REPLICA STATUS", target="replica", root=True)[0]
    assert (status["Replica_IO_Running"], status["Replica_SQL_Running"]) == ("Yes", "Yes")
    stack.sql(
        "INSERT INTO blog_posts (id, title, content, created_at, updated_at) "
        "VALUES (UUID(), 'probe', 'x', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
    )
    stack.wait_replicated("blog_posts", "title=%s", ("probe",))
    stack.sql("DELETE FROM blog_posts WHERE title='probe'")
    wait_for(
        lambda: not stack.sql("SELECT 1 FROM blog_posts WHERE title='probe'", target="replica"),
        15,
        "삭제가 복제되지 않았다",
    )
    covers("harness", "기동", "복제")
    assert PORTS["app"] == 18093
