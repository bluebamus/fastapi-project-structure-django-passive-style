"""설정 일원화 계약 테스트.

두 가지 불변식을 지킨다:

1. **`.env` 의 모든 정보는 config.py 에 로드된다.**
   `.env.example` 에 적힌 키(주석 처리된 예시 포함)는 반드시 어떤 Settings 클래스의
   필드로 존재해야 한다. 반대로 config.py 의 모든 설정 필드는 `.env.example` 에
   문서화되어야 한다. 두 방향을 모두 검사해 문서와 코드가 갈라지지 않게 한다.

2. **config.py 외의 모듈은 환경변수를 직접 읽지 않는다.**
   설정이 필요한 모듈은 `from config import ...` 로 가져다 쓴다. `os.environ` /
   `os.getenv` 가 코드 여기저기 흩어지면 "이 값이 어디서 오는가"를 추적할 수 없고,
   `.env.example` 에 문서화되지 않은 숨은 설정이 생긴다.

3. **설정 필드는 운영 코드가 읽는다 — 지운 설정이 남아 있어도 기동은 깨지지 않는다.**
   선언만 있는 설정은 값을 바꿔도 아무 일도 없다(config-cleanup 에서 ``SMTP_*``·``UPLOAD_*``·
   ``SESSION_EXPIRE_SECONDS``, config-cleanup-2 에서 ``API_VERSION`` 을 지운 이유). 예외 목록은 없다.
   지운 키가 `.env` 에 남아도 ``extra="ignore"`` 로 무시된다.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

import config as config_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

# `KEY=value` 또는 주석 처리된 `# KEY=value` 형태의 설정 키만 뽑는다.
# (`# 예: ...`, `# - true: ...` 같은 산문 주석은 걸리지 않는다)
ENV_KEY_PATTERN = re.compile(r"^\s*(?:#\s*)?([A-Z][A-Z0-9_]*)\s*=")

# 환경변수 직접 접근 패턴
ENV_ACCESS_PATTERN = re.compile(r"os\.environ|os\.getenv")

# 환경변수 직접 접근을 검사할 소스 트리 (테스트 하네스는 제외)
SOURCE_ROOTS = ("app", "migrations", "scripts")
SOURCE_FILES = ("main.py",)

# 이 규칙이 막는 것은 "애플리케이션 설정을 config.py 밖에서 읽는 것"이다. 검수 게이트는
# 설정을 읽지 않는다 — **자식 프로세스에 넘길 환경**을 구성한다(UTF-8 강제·캐시 격리).
# 그건 config.py 의 책임이 아니고, 여기 넣지 않으면 게이트가 자기 목적을 수행할 수 없다.
# 예외는 파일 이름으로 좁힌다 — 디렉터리째 빼면 다음 스크립트가 조용히 따라 들어온다.
ENV_ACCESS_ALLOWED = frozenset({"review_gate.py"})


def _env_example_keys() -> set[str]:
    """`.env.example` 이 문서화한 설정 키 전체."""
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = ENV_KEY_PATTERN.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _config_setting_fields() -> set[str]:
    """config.py 의 모든 Settings 클래스가 로드하는 필드 전체."""
    fields: set[str] = set()
    for obj in vars(config_module).values():
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings:
            fields |= set(obj.model_fields)
    return fields


def _python_sources() -> list[Path]:
    """환경변수 직접 접근을 금지할 소스 파일 목록."""
    paths = [PROJECT_ROOT / name for name in SOURCE_FILES]
    for root in SOURCE_ROOTS:
        paths.extend((PROJECT_ROOT / root).rglob("*.py"))
    return [
        path
        for path in paths
        if path.exists()
        and "tests" not in path.parts
        and "__pycache__" not in path.parts
        and path.name not in ENV_ACCESS_ALLOWED
    ]


# =============================================================================
# 1. .env ↔ config.py 일원화
# =============================================================================
def test_every_env_example_key_is_loaded_in_config():
    """`.env.example` 의 모든 키는 config.py 의 Settings 필드로 로드되어야 한다."""
    missing = sorted(_env_example_keys() - _config_setting_fields())
    assert not missing, (
        f".env.example 에만 있고 config.py 가 로드하지 않는 키: {missing}\n"
        "설정은 반드시 config.py 를 거쳐야 합니다."
    )


def test_every_config_field_is_documented_in_env_example():
    """config.py 의 모든 설정 필드는 `.env.example` 에 문서화되어야 한다."""
    undocumented = sorted(_config_setting_fields() - _env_example_keys())
    assert not undocumented, (
        f"config.py 에만 있고 .env.example 에 문서화되지 않은 키: {undocumented}\n"
        ".env.example 은 지원하는 설정의 단일 목록입니다."
    )


def test_config_defines_at_least_one_setting_field():
    """위 두 테스트가 '필드를 하나도 못 찾아서' 통과하는 상황을 막는다."""
    assert len(_config_setting_fields()) > 20
    assert len(_env_example_keys()) > 20


# =============================================================================
# 2. config.py 만이 환경변수를 읽는다
# =============================================================================
def test_only_config_reads_environment_directly():
    """config.py 외의 모듈은 os.environ / os.getenv 를 쓰지 않는다."""
    offenders = []
    for path in _python_sources():
        if ENV_ACCESS_PATTERN.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert not offenders, (
        f"환경변수를 직접 읽는 모듈: {sorted(offenders)}\n"
        "설정은 config.py 에서 로드하고 `from config import ...` 로 가져다 쓰세요."
    )


def test_environment_access_check_scans_real_files():
    """검사 대상 파일 목록이 비어 있어 위 테스트가 헛통과하는 것을 막는다."""
    sources = _python_sources()
    assert len(sources) > 10
    assert any(path.name == "env.py" and "migrations" in path.parts for path in sources)


# =============================================================================
# 3. 설정 필드는 운영 코드가 읽는다 · 지운 설정은 무시된다
# =============================================================================
#: 필드를 "읽는지" 볼 운영 코드 — 테스트는 제외한다(테스트만 읽는 설정은 소비처가 아니다).
#: config.py 도 넣는다(DSN 조립·교차 검증처럼 config 안에서 읽는 필드가 있다).
READ_SCAN_FILES = [PROJECT_ROOT / "config.py", *_python_sources()]

#: 지운 설정 — 로컬·운영 `.env` 에 남아 있어도 무시돼야 한다(레거시 ADMIN 과 달리 기동 거부 대상이 아니다).
REMOVED_KEYS = {
    "SMTP_SERVER": "localhost",
    "SMTP_PASSWORD": "your-app-password",
    "UPLOAD_DIR": "uploads",
    "UPLOAD_ALLOWED_EXTENSIONS": '[".jpg"]',
    "SESSION_EXPIRE_SECONDS": "86400",
    "API_VERSION": "v1",
    # logging-overhaul — 날짜·크기·보관일수 회전으로 바뀌며 지웠다(README 업그레이드 노트).
    "LOG_APP_FILENAME": "{date}_app.log",
    "LOG_ERROR_FILENAME": "{date}_error.log",
    "LOG_BACKUP_COUNT": "5",
}

SETTINGS_CLASSES = [
    obj
    for obj in vars(config_module).values()
    if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
]


def _names_read_by_source() -> set[str]:
    """운영 코드가 **읽는** 이름 — 속성 접근(``settings.X``·``self.X``)과 ``getattr(obj, "X")``.

    주석·docstring·문자열 목록은 세지 않는다 — 이름을 적는 것은 읽는 것이 아니다.
    """
    names: set[str] = set()
    for path in READ_SCAN_FILES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
            ):
                names.add(str(node.args[1].value))
    return names


def test_every_setting_field_is_read_by_source_code():
    """설정 필드는 운영 코드 어딘가에서 읽혀야 한다 — 선언만 있는 설정은 값을 바꿔도 아무 일도 없다."""
    read = _names_read_by_source()
    fields = _config_setting_fields()
    assert len(READ_SCAN_FILES) > 10 and len(fields) > 20, "검사 대상이 비어 헛통과한다"

    unread = sorted(fields - read)
    assert not unread, f"읽는 곳이 없는 설정 필드: {unread} — 지우거나 쓰는 코드를 넣는다"


@pytest.mark.parametrize("cls", SETTINGS_CLASSES, ids=lambda cls: cls.__name__)
def test_removed_keys_left_in_environment_are_ignored(
    monkeypatch: pytest.MonkeyPatch, cls: type[BaseSettings]
):
    """지운 키가 환경에 남아 있어도 설정 생성이 실패하지 않고, 속성으로 생기지도 않는다."""
    for key, value in REMOVED_KEYS.items():
        monkeypatch.setenv(key, value)

    settings = cls(_env_file=None)  # type: ignore[call-arg]

    for key in REMOVED_KEYS:
        assert not hasattr(settings, key), f"{cls.__name__} 에 지운 설정 {key} 가 남아 있다"


# =============================================================================
# 4. 비밀 설정은 로그 가리기 목록에 있다 (logging-overhaul L7)
# =============================================================================
#: 이름이 이 모양이면 비밀 설정으로 본다 — 새 필드가 생기면 LOG_REDACTED_SETTINGS 에도 넣어야 한다.
SECRET_FIELD_NAME = re.compile(r"PASSWORD|SECRET|_KEY$|_USER$")


def test_every_secret_setting_is_redacted_from_logs():
    """비밀처럼 생긴 설정 필드는 모두 ``config.LOG_REDACTED_SETTINGS`` 에 있고, 목록의 이름은 실제 필드다."""
    fields = _config_setting_fields()
    secret_like = {name for name in fields if SECRET_FIELD_NAME.search(name)}
    assert len(secret_like) >= 8, "검사 대상이 비어 헛통과한다"

    listed = set(config_module.LOG_REDACTED_SETTINGS)
    assert (
        not secret_like - listed
    ), f"로그 가리기 목록에 없는 비밀 설정: {sorted(secret_like - listed)}"
    assert not listed - fields, f"목록에 있지만 설정 필드가 아니다: {sorted(listed - fields)}"
