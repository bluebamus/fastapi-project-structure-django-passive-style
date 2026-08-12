"""관리자 전용 API 접근 제어 (설정 기반 Bearer 토큰).

**왜 로그인이 아니라 공유 토큰인가.** 이 저장소에는 자격증명 저장소가 없다 —
``User`` 모델에 비밀번호 컬럼이 없고, 해싱·토큰 발급 의존성도 설치돼 있지 않다.
사용자 로그인을 붙이려면 비밀번호 컬럼·해싱 라이브러리·토큰 발급 엔드포인트·
계정 생성 흐름 변경이 함께 와야 하는데, 이는 "전체 인증 제품 기능" 으로 범위
밖이다. 반면 보호해야 할 대상(접속로그 조회·사용자 CRUD)은 성격상 **운영자
전용**이라 사용자별 신원이 필요하지 않다. 그래서 설정에 둔 단일 토큰으로 막는다.

**fail-closed.** 토큰이 설정돼 있지 않으면 모든 요청을 거부한다. "설정을 안 했으니
일단 열어둔다" 는 곧 설정을 잊은 배포가 공개 상태가 된다는 뜻이다.

**401 만 쓰고 403 은 쓰지 않는 이유.** 공유 토큰 방식에는 "인증은 됐으나 권한이
없는" 상태가 존재하지 않는다. 토큰이 없거나 틀리면 둘 다 "유효한 자격 증명이
없음" 이므로 401 이 맞다(RFC 7235). 역할 구분이 생기면 그때 403 이 의미를 갖는다.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.utils.logs import get_logger
from config import app_settings

logger = get_logger("authenticator")

# auto_error=False: 헤더 부재를 여기서 직접 처리해 응답 형태를 통일한다.
bearer_scheme = HTTPBearer(auto_error=False, description="관리자 API 토큰")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="관리자 인증이 필요합니다.",
    headers={"WWW-Authenticate": "Bearer"},
)


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """관리자 토큰이 유효하지 않으면 401 로 거부한다.

    Raises:
        HTTPException: 토큰 미설정·헤더 부재·토큰 불일치 — 모두 401.
    """
    configured = app_settings.ADMIN_API_TOKEN
    expected = configured.get_secret_value() if configured else ""

    if not expected:
        # 거부 자체는 옳지만, 운영자가 원인을 알 수 있어야 한다.
        logger.error(
            "ADMIN_API_TOKEN 이 설정되지 않아 관리자 API 요청을 거부했습니다. "
            ".env 에 ADMIN_API_TOKEN 을 설정하세요."
        )
        raise _UNAUTHORIZED

    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED

    # 타이밍 공격으로 토큰을 한 글자씩 알아내는 것을 막는다.
    if not secrets.compare_digest(credentials.credentials, expected):
        raise _UNAUTHORIZED
