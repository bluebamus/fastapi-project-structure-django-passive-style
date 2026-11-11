"""설정 계약 — 지운 설정 키가 남아 있어도 기동하고, 비밀 설정은 로그 가리기 목록에 있다."""

import inspect
import re

import pytest
from pydantic_settings import BaseSettings

import config as config_module


def _config_setting_fields() -> set[str]:
    """config.py 의 모든 Settings 클래스가 로드하는 필드 전체."""
    fields: set[str] = set()
    for obj in vars(config_module).values():
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings:
            fields |= set(obj.model_fields)
    return fields


#: 지운 설정 — 로컬·운영 `.env` 에 남아 있어도 무시돼야 한다(레거시 ADMIN 과 달리 기동 거부 대상이 아니다).
REMOVED_KEYS = {
    "SMTP_SERVER": "localhost",
    "SMTP_PASSWORD": "your-app-password",
    "UPLOAD_DIR": "uploads",
    "UPLOAD_ALLOWED_EXTENSIONS": '[".jpg"]',
    "SESSION_EXPIRE_SECONDS": "86400",
    "API_VERSION": "v1",
    # 날짜·크기·보관일수 회전으로 바뀌며 지웠다.
    "LOG_APP_FILENAME": "{date}_app.log",
    "LOG_ERROR_FILENAME": "{date}_error.log",
    "LOG_BACKUP_COUNT": "5",
}

SETTINGS_CLASSES = [
    obj
    for obj in vars(config_module).values()
    if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
]


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
# 4. 비밀 설정은 로그 가리기 목록에 있다
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
