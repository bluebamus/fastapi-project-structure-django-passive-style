"""
사용자 접속 정보 수집 미들웨어

모든 요청에서 사용자의 접속 정보를 수집하여 데이터베이스에 저장합니다.

수집에는 두 가지 경계가 걸려 있습니다:

- **신뢰 경계**: 전달 헤더(X-Forwarded-For / X-Real-IP)는 신뢰 프록시가 보낸
  경우에만 사용합니다. 이 헤더는 클라이언트가 임의로 보낼 수 있어서, 무조건
  믿으면 감사 로그의 IP 를 누구나 위조할 수 있습니다.
- **데이터 최소화**: 민감한 query parameter 값과 세션 ID 원문은 저장하지
  않습니다. 이 테이블이 유출됐을 때의 피해 범위를 줄이기 위해서입니다.
"""

import hashlib
import hmac
import ipaddress
import time
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp
from user_agents import parse as parse_user_agent

from app.core.middlewares.access_log_sink import get_access_log_sink
from app.core.middlewares.background_tasks import access_log_tasks
from app.utils.logs import get_logger
from config import middleware_settings, session_settings

logger = get_logger("user_info_middleware")

REDACTED = "[REDACTED]"

# 주소를 판별할 수 없을 때 저장하는 값. 자유 문자열("unknown") 대신 유효한 IP 를
# 쓰면 컬럼에 항상 파싱 가능한 값만 들어간다 — 조회·집계 쪽이 예외를 걱정하지 않는다.
UNKNOWN_IP = "0.0.0.0"  # noqa: S104  # nosec B104 - 바인드 주소가 아니라 '미상' 표식


def _is_valid_ip(address: str) -> bool:
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


def _is_trusted(address: str) -> bool:
    """*address* 가 신뢰 프록시 목록에 드는가.

    목록이 비어 있으면(기본값) 어떤 상대도 신뢰하지 않는다 — 전달 헤더를 믿어도
    되는 배치인지는 운영자만 알 수 있고, 모르면 안 믿는 쪽이 안전하다.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    for entry in middleware_settings.ACCESS_LOG_TRUSTED_PROXIES:
        try:
            if ip in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            logger.warning("ACCESS_LOG_TRUSTED_PROXIES 항목을 해석할 수 없습니다: %r", entry)
    return False


def redact_query_string(query_string: str | None) -> str | None:
    """민감한 query parameter 의 **값만** 가린다.

    키와 나머지 파라미터는 남긴다 — 어떤 요청이었는지는 알아야 감사 로그로서
    쓸모가 있고, 위험한 것은 값 쪽이다(토큰·비밀번호·인증 코드).
    """
    if not query_string:
        return query_string

    sensitive = [key.lower() for key in middleware_settings.ACCESS_LOG_REDACT_QUERY_KEYS]
    pairs = parse_qsl(query_string, keep_blank_values=True)
    if not pairs:
        return query_string

    return urlencode(
        [
            (key, REDACTED if any(s in key.lower() for s in sensitive) else value)
            for key, value in pairs
        ]
    )


def hash_session_id(session_id: str | None) -> str | None:
    """세션 ID 를 되돌릴 수 없는 값으로 바꾼다(keyed hash).

    원문을 저장하면 이 테이블 유출이 곧 세션 탈취가 된다. 반면 세션 단위로 로그를
    묶어 보는 일은 남겨야 하므로, 지우지 않고 키를 섞어 해시한다. 키가 없으면
    같은 값이 어디서나 같은 해시가 되어 무지개표에 취약하다.
    """
    if not session_id:
        return None

    key = session_settings.SESSION_SECRET_KEY.encode("utf-8")
    return hmac.new(key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()


class UserInfoMiddleware(BaseHTTPMiddleware):
    """
    사용자 접속 정보 수집 미들웨어

    요청 시작 시 사용자 정보를 수집하고,
    응답 완료 후 백그라운드에서 데이터베이스에 저장합니다.

    수집 정보:
        - IP 주소 (X-Forwarded-For, X-Real-IP 포함)
        - User-Agent 파싱 (OS, 브라우저, 장치 정보)
        - 요청 경로 및 메서드
        - 응답 상태 코드 및 시간
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        미들웨어 초기화

        Args:
            app: ASGI 애플리케이션(다음 미들웨어/앱). Starlette 미들웨어 팩토리 규약.
        """
        super().__init__(app)
        self.enabled = middleware_settings.ACCESS_LOG_ENABLED
        self.exclude_paths = set(middleware_settings.ACCESS_LOG_EXCLUDE_PATHS)
        self.exclude_extensions = set(middleware_settings.ACCESS_LOG_EXCLUDE_EXTENSIONS)

    def _should_skip(self, path: str) -> bool:
        """
        로깅을 건너뛸지 결정합니다.

        Args:
            path: 요청 경로

        Returns:
            건너뛸 경우 True
        """
        # 비활성화된 경우
        if not self.enabled:
            return True

        # 제외 경로인 경우
        if path in self.exclude_paths:
            return True

        # 제외 확장자인 경우
        for ext in self.exclude_extensions:
            if path.endswith(ext):
                return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """
        클라이언트 IP 주소를 추출합니다.

        실제 TCP 피어가 신뢰 프록시일 때만 전달 헤더를 사용합니다. 그 외에는
        피어 주소를 그대로 씁니다 — 헤더는 클라이언트가 임의로 보낼 수 있습니다.

        Args:
            request: FastAPI Request 객체

        Returns:
            검증된 IP 주소 문자열. 판별 불가 시 "0.0.0.0".
        """
        peer = request.client.host if request.client else ""

        if not _is_trusted(peer):
            return peer if _is_valid_ip(peer) else UNKNOWN_IP

        # 신뢰 프록시 뒤 — 전달 헤더가 실제 클라이언트를 가리킨다.
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # 체인은 왼쪽이 원 클라이언트, 오른쪽이 최근 홉이다. 앞쪽은 클라이언트가
            # 위조해 끼워 넣을 수 있으므로, 오른쪽부터 훑어 신뢰 목록에 없는 첫
            # 항목을 클라이언트로 본다.
            for hop in reversed([part.strip() for part in forwarded_for.split(",")]):
                if _is_valid_ip(hop) and not _is_trusted(hop):
                    return hop

        real_ip = request.headers.get("X-Real-IP", "").strip()
        if _is_valid_ip(real_ip):
            return real_ip

        return peer if _is_valid_ip(peer) else UNKNOWN_IP

    def _parse_user_agent(self, user_agent_string: str | None) -> dict:
        """
        User-Agent 문자열을 파싱합니다.

        Args:
            user_agent_string: User-Agent 헤더 값

        Returns:
            파싱된 정보 딕셔너리
        """
        if not user_agent_string:
            return {
                "os_name": None,
                "os_version": None,
                "browser_name": None,
                "browser_version": None,
                "device_type": None,
                "device_brand": None,
                "device_model": None,
                "is_bot": False,
            }

        ua = parse_user_agent(user_agent_string)

        # 장치 유형 결정
        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        elif ua.is_pc:
            device_type = "desktop"
        else:
            device_type = "other"

        return {
            "os_name": ua.os.family if ua.os.family != "Other" else None,
            "os_version": ua.os.version_string or None,
            "browser_name": ua.browser.family if ua.browser.family != "Other" else None,
            "browser_version": ua.browser.version_string or None,
            "device_type": device_type,
            "device_brand": ua.device.brand or None,
            "device_model": ua.device.model or None,
            "is_bot": ua.is_bot,
        }

    def _collect_request_info(self, request: Request) -> dict:
        """
        요청에서 정보를 수집합니다.

        Args:
            request: FastAPI Request 객체

        Returns:
            수집된 정보 딕셔너리
        """
        # User-Agent 파싱
        user_agent_string = request.headers.get("User-Agent")
        ua_info = self._parse_user_agent(user_agent_string)

        # 쿼리 스트링 — 민감한 값은 가린 뒤 저장한다
        raw_query = str(request.query_params) if request.query_params else None
        query_string = redact_query_string(raw_query)

        return {
            # 네트워크 정보
            "ip_address": self._get_client_ip(request),
            # 전달 헤더 원문은 그대로 남긴다 — 위조 시도 자체가 조사 단서이고,
            # 신뢰 판정은 위 ip_address 에서 이미 끝났다.
            "forwarded_for": request.headers.get("X-Forwarded-For"),
            "real_ip": request.headers.get("X-Real-IP"),
            # User-Agent 정보
            "user_agent": user_agent_string,
            **ua_info,
            # 요청 정보
            "request_path": request.url.path,
            "request_method": request.method,
            "query_string": query_string,
            "referer": request.headers.get("Referer"),
            # 추가 헤더
            "accept_language": request.headers.get("Accept-Language"),
            # 사용자 정보 (인증 미들웨어에서 설정될 수 있음)
            # 세션 ID 는 원문 대신 keyed hash 로 저장한다 — 세션 단위 상관관계는
            # 유지하면서, 이 테이블 유출이 세션 탈취로 이어지지 않게 한다.
            "session_id": hash_session_id(request.cookies.get("session_id")),
            "user_id": getattr(request.state, "user_id", None),
        }

    async def _save_access_log(self, data: dict) -> None:
        """
        접속 로그를 백그라운드에서 저장합니다.

        Args:
            data: 저장할 접속 로그 데이터
        """
        try:
            sink = get_access_log_sink()
            if sink is None:
                return
            await sink.save(data)
        except Exception as e:
            # 로그 저장 실패가 요청 처리에 영향을 주지 않도록 함
            logger.error(f"접속 로그 저장 실패: {e}", exc_info=True)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        미들웨어 메인 로직

        Args:
            request: FastAPI Request 객체
            call_next: 다음 미들웨어 또는 라우터 호출 함수

        Returns:
            Response 객체
        """
        path = request.url.path

        # 로깅 제외 대상인 경우 바로 다음으로 전달
        if self._should_skip(path):
            return await call_next(request)

        # 요청 시작 시간 기록
        start_time = time.perf_counter()

        logger.debug(f"[요청 시작] {request.method} {path}")

        # 요청 정보 수집
        request_info = self._collect_request_info(request)

        # 요청 처리
        response: Response = await call_next(request)

        # 응답 시간 계산
        response_time_ms = int((time.perf_counter() - start_time) * 1000)

        # 응답 정보 추가
        request_info["response_status"] = response.status_code
        request_info["response_time_ms"] = response_time_ms

        logger.debug(
            f"[요청 완료] {request.method} {path} "
            f"- {response.status_code} ({response_time_ms}ms)"
        )

        # 백그라운드에서 로그 저장 (요청 처리를 블로킹하지 않음).
        # 상한 초과 시 드롭·집계되고, 앱 종료 시 lifespan 이 drain 한다(W1).
        access_log_tasks.spawn(self._save_access_log(request_info))

        return response


def setup_user_info_middleware(app: FastAPI) -> None:
    """
    UserInfoMiddleware를 FastAPI 앱에 등록합니다.

    Args:
        app: FastAPI 애플리케이션 인스턴스
    """
    app.add_middleware(UserInfoMiddleware)
    logger.info("UserInfoMiddleware 등록 완료")
