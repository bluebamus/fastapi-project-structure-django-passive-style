"""CORSSettings 검증 회귀 테스트 (계획서 P2-1).

CORS 스펙상 ``Access-Control-Allow-Origin: *`` 과
``Access-Control-Allow-Credentials: true`` 는 함께 쓸 수 없다. 브라우저가 응답을
거부하므로 서버는 200 을 반환하는데 프론트만 실패한다 — 서버 로그에 아무것도 남지
않아 원인 추적이 오래 걸린다. 설정 로드 시점에 실패시키는 편이 싸다.
"""

import pytest
from pydantic import ValidationError

from config import CORSSettings


def test_wildcard_origin_with_credentials_is_rejected():
    with pytest.raises(ValidationError) as exc:
        CORSSettings(CORS_ALLOW_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=True)
    assert "CORS_ALLOW_CREDENTIALS" in str(exc.value)


def test_wildcard_among_several_origins_is_also_rejected():
    """와일드카드가 목록 중간에 섞여 있어도 같은 문제다."""
    with pytest.raises(ValidationError):
        CORSSettings(
            CORS_ALLOW_ORIGINS=["https://app.example.com", "*"],
            CORS_ALLOW_CREDENTIALS=True,
        )


def test_wildcard_without_credentials_is_allowed():
    """공개 API 의 정상 구성 — 막으면 안 된다."""
    settings = CORSSettings(CORS_ALLOW_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=False)
    assert settings.CORS_ALLOW_ORIGINS == ["*"]


def test_explicit_origins_with_credentials_is_allowed():
    settings = CORSSettings(
        CORS_ALLOW_ORIGINS=["https://app.example.com"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    assert settings.CORS_ALLOW_CREDENTIALS is True
