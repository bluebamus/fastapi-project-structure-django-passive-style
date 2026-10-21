"""DSN 은 문자열 연결이 아니라 ``sqlalchemy.engine.URL`` 로 조립한다(service-hardening F-003).

문자열로 이어 붙이면 비밀번호의 ``@ : / # ?`` 가 구분자로 읽혀 **조용히 다른 호스트·계정**으로
접속을 시도하고, ``%`` 는 Alembic 의 ConfigParser 보간에서 ``ValueError`` 로 터진다. 여기서는
그런 비밀번호가 URL 을 거쳐 그대로 돌아오는지(왕복)를 본다 — 렌더링된 문자열 모양이 아니라
파싱한 결과의 의미로 비교한다.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from redis.connection import parse_url
from sqlalchemy.engine import make_url

import config as config_module
from config import DatabaseSettings, RedisSettings

#: 구분자로 오해되는 문자를 모두 담은 비밀번호.
TRICKY_PASSWORD = "p@ss:w/rd%#?"  # noqa: S105 - 테스트 픽스처 값


def _db(**overrides) -> DatabaseSettings:
    return DatabaseSettings(_env_file=None, **overrides)


def test_writer_url_round_trips_tricky_password():
    url = _db(MYSQL_USER="app", MYSQL_PASSWORD=TRICKY_PASSWORD).MYSQL_WRITER_URL

    parsed = make_url(url.render_as_string(hide_password=False))

    assert parsed.password == TRICKY_PASSWORD
    assert (parsed.username, parsed.host, parsed.port) == ("app", "localhost", 3306)


def test_replica_urls_round_trip_tricky_password_and_ipv6():
    settings = _db(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["[2001:db8::10]:3307", "replica-b"],
        MYSQL_REPLICA_PASSWORD=TRICKY_PASSWORD,
    )

    parsed = [
        make_url(u.render_as_string(hide_password=False)) for u in settings.MYSQL_REPLICA_URLS
    ]

    assert [(u.host, u.port, u.password) for u in parsed] == [
        ("2001:db8::10", 3307, TRICKY_PASSWORD),
        ("replica-b", 3306, TRICKY_PASSWORD),
    ]


def test_masked_routing_summary_hides_tricky_password():
    settings = _db(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_PASSWORD=TRICKY_PASSWORD,
        MYSQL_REPLICA_HOSTS=["replica-a"],
    )

    summary = settings.describe_routing()
    rendered = [summary["writer"], *summary["readers"]]

    for text in rendered:
        assert isinstance(text, str)
        assert make_url(text).password == "***"
        assert "p@ss" not in text and "p%40ss" not in text


def test_alembic_url_switches_only_the_driver():
    url = _db(MYSQL_PASSWORD=TRICKY_PASSWORD).ALEMBIC_URL

    assert url.drivername == "mysql+pymysql"
    assert url.password == TRICKY_PASSWORD


def test_alembic_url_override_is_parsed():
    url = _db(ALEMBIC_DATABASE_URL="sqlite:///./migrate.db").ALEMBIC_URL

    assert url == make_url("sqlite:///./migrate.db")


def test_alembic_env_escapes_percent_for_configparser(tmp_path, monkeypatch):
    """``%`` 가 든 DSN 을 env.py 가 ``%%`` 로 넘겨야 ConfigParser 보간이 터지지 않는다.

    설정 객체는 **호출 시점**에 ``config_module.db_settings`` 로 꺼내 patch 한다 — 다른 테스트가
    ``importlib.reload(config)`` 를 하면 import 시점에 잡아 둔 객체는 env.py 가 읽는 객체가 아니다.
    """
    db_file = tmp_path / "pct%dir" / "chain.db"
    db_file.parent.mkdir()
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(config_module.db_settings, "ALEMBIC_DATABASE_URL", url)

    command.upgrade(Config("alembic.ini"), "head")

    engine = sa.create_engine(url)
    try:
        assert "users" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.parametrize("password", [TRICKY_PASSWORD, "plain"])
def test_redis_url_round_trips_password(password: str):
    # 포트를 고정한다 — 테스트 실행은 REDIS_PORT 를 명시하므로(integration-e2e W0) 기본값에 기대면
    # 환경에 따라 결과가 갈린다. 이 검사의 대상은 비밀번호 왕복이다.
    settings = RedisSettings(
        _env_file=None, REDIS_HOST="cache", REDIS_PORT=6379, REDIS_PASSWORD=password
    )

    parsed = parse_url(settings.REDIS_URL)

    assert (parsed["password"], parsed["host"], parsed["port"]) == (password, "cache", 6379)


def test_redis_url_without_password_has_no_credentials():
    parsed = parse_url(RedisSettings(_env_file=None, REDIS_PASSWORD=None).REDIS_URL)

    assert "password" not in parsed


def test_mysql_rsa_auth_dependency_is_declared_through_the_driver():
    """MySQL 8.4 ``caching_sha2_password`` 전체 인증(TLS 아닌 연결)의 RSA 암호화에 cryptography 가 필요하다.

    유일한 사용처가 드라이버라 드라이버의 공식 추가 옵션 ``aiomysql[rsa]``(= ``PyMySQL[rsa]``)로 선언한다 —
    직접 적은 ``cryptography`` 는 사용처와 떨어져 낡는다(e2e-policy-2 의존성 통일).
    """
    import tomllib
    from pathlib import Path

    import pymysql._auth

    deps = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))["project"]["dependencies"]
    names = {dep.split("(")[0].split(">")[0].split("<")[0].strip(): dep for dep in deps}

    assert "aiomysql[rsa]" in names, deps
    assert (
        "cryptography" not in names
    ), "cryptography 를 직접 선언하지 않는다 — aiomysql[rsa] 가 끌어온다"
    assert "pymysql" in names, "Alembic(동기 드라이버)이 pymysql 을 직접 쓴다"
    assert pymysql._auth._have_cryptography is True
