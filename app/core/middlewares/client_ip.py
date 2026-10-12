"""
클라이언트 IP 해석기

!! 배포 전 확인: 프록시(로드밸런서·nginx) 뒤에 배포하면 ``TRUSTED_PROXY_HOPS`` 를 앞단 프록시 단 수로
설정한다. 0 이면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋(API·/admin)이
전체 사용자를 한 사람으로 취급한다. 실제보다 크게 잡으면 클라이언트가 보낸 ``X-Forwarded-For`` 를
믿게 되어 IP 를 위조할 수 있다.

접속 로그가 기록할 클라이언트 IP 를 정하는 한 곳이다(service-hardening ADR-005). API 로그인·가입과
``/admin`` 로그인의 레이트 리밋도 같은 해석기로 IP 를 정한다.

``X-Forwarded-For`` 는 누구나 보낼 수 있는 헤더라 무조건 믿으면 기록 IP 를 위조할 수 있다.
그래서 신뢰는 "앞단에 몇 홉의 프록시를 운영하는가" 라는 배포 사실(``TRUSTED_PROXY_HOPS``)로만
정한다. 각 프록시는 받은 요청의 직접 피어를 XFF 오른쪽 끝에 붙이므로, XFF 목록 + 직접 피어를
이어 붙인 목록에서 직접 피어를 0번째로 센 **오른쪽 N번째** 가 가장 바깥 신뢰 프록시가 본
클라이언트다(XFF 만 놓고 보면 오른쪽 N번째). 그보다 왼쪽은
클라이언트가 마음대로 쓴 값이라 쓰지 않는다.
"""

import ipaddress

from starlette.requests import Request


class ClientIPResolver:
    """신뢰 프록시 홉 수로 클라이언트 IP 를 정한다.

    Args:
        trusted_proxy_hops: 앞단에서 운영하는 신뢰 프록시 수. 0 이면 헤더를 보지 않고 직접 피어를 쓴다.
    """

    def __init__(self, trusted_proxy_hops: int = 0) -> None:
        if trusted_proxy_hops < 0:
            raise ValueError("trusted_proxy_hops 는 0 이상이어야 한다")
        self.trusted_proxy_hops = trusted_proxy_hops

    def resolve(self, request: Request) -> str:
        """요청의 클라이언트 IP 를 돌려준다. 직접 피어도 없으면 ``"unknown"``."""
        peer = request.client.host if request.client else "unknown"
        hops = self.trusted_proxy_hops
        if hops == 0:
            return peer

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # 직접 피어(= 마지막 신뢰 프록시)를 0번째로 세어 오른쪽 N번째 — XFF 의 오른쪽 N번째와 같다.
            chain = [part.strip() for part in forwarded_for.split(",")] + [peer]
            # 체인이 홉 수보다 짧으면 선언한 프록시를 다 거치지 않은 요청이다 — 직접 피어를 쓴다.
            candidate = chain[-(hops + 1)] if hops < len(chain) else peer
        else:
            # X-Real-IP 는 XFF 가 없을 때만 본다(프록시가 하나만 쓰는 배포).
            candidate = (request.headers.get("X-Real-IP") or "").strip()

        return candidate if _is_ip(candidate) else peer


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
