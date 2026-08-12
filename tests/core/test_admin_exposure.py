"""Admin 노출 경계 테스트 (계획서 P0-1).

이 저장소는 SQLAdmin 에 **인증을 붙이지 않기로 결정했다**(ADR-PSV-003). 인증이
없는 관리 UI 가 안전한 유일한 상태는 운영에 존재하지 않는 것이므로, 안전은
로그인이 아니라 **노출 차단**으로 확보한다:

1. 기본값은 꺼짐 — 설정을 잊은 배포에서 /admin 이 열리지 않는다.
2. 운영에서는 켤 수 없음 — ENV=production 이면 기동 자체를 거부한다.
3. 감사 기록은 Admin 에서도 지우거나 내보낼 수 없다.

이 저장소는 템플릿이라 1번이 특히 중요하다 — 복제해 쓰는 쪽이 .env 를 손대지
않으면 그대로 배포된다.
"""

import pytest
from pydantic import ValidationError

from config import AppSettings


def test_admin_is_disabled_by_default():
    """필드 기본값 자체를 본다(.env 값에 영향받지 않도록)."""
    assert AppSettings.model_fields["ADMIN"].default is False


def test_admin_cannot_be_enabled_in_production():
    with pytest.raises(ValidationError) as exc:
        AppSettings(ENV="production", ADMIN=True)
    assert "ADMIN" in str(exc.value)


def test_admin_may_be_enabled_outside_production():
    for env in ("development", "staging", "test"):
        assert AppSettings(ENV=env, ADMIN=True).ADMIN is True


def test_production_without_admin_is_fine():
    assert AppSettings(ENV="production", ADMIN=False).ADMIN is False


def test_admin_routes_absent_when_disabled(monkeypatch):
    from app.core import bootstrap

    monkeypatch.setattr(bootstrap.app_settings, "ADMIN", False)
    app = bootstrap.create_app()

    assert not [r for r in app.routes if r.path.startswith("/admin")]


def test_admin_routes_present_when_enabled(monkeypatch):
    """차단이 과해서 개발용 Admin 까지 죽이면 안 된다."""
    from app.core import bootstrap

    monkeypatch.setattr(bootstrap.app_settings, "ADMIN", True)
    app = bootstrap.create_app()

    assert [r for r in app.routes if r.path.startswith("/admin")]


def test_access_log_admin_cannot_delete_or_export():
    """감사 기록은 Admin 에서 지우거나 내보낼 수 없다.

    삭제 가능하면 감사 기록으로서의 가치가 없고, 내보내기는 IP·사용자 ID 가
    묶인 개인정보를 파일로 빼내는 경로가 된다(F-05 가 줄이려는 바로 그 데이터).
    """
    from app.features.home.admin import UserAccessLogAdmin

    assert UserAccessLogAdmin.can_delete is False
    assert UserAccessLogAdmin.can_export is False
    # 이미 지켜지던 것 — 함께 고정한다
    assert UserAccessLogAdmin.can_create is False
    assert UserAccessLogAdmin.can_edit is False
