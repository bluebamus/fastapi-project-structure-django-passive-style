"""e2e 실행 기록 — 어떤 인벤토리 칸을 **실제로 실행한** 테스트가 있는지 모은다.

테스트는 검사를 마친 자리에서 ``covers(item, cell)`` 을 부른다(데코레이터가 아니라 호출이다 —
실행되지 않은 테스트는 칸을 채우지 못한다). ``test_zz_inventory.py`` 가 마지막에 앱에서 뽑은
인벤토리와 이 기록을 대조해 빈 칸이 있으면 실패한다.
"""

from __future__ import annotations

from collections import defaultdict

#: item → 채워진 칸.
COVERED: dict[str, set[str]] = defaultdict(set)

#: 실행 중 Redis 에서 관찰한 키(인벤토리의 Redis 접두어 대조용).
SEEN_REDIS_KEYS: set[str] = set()

#: 실행 중 발급된 Bearer·refresh 토큰 — 로그 비밀값 검사(L6-4)가 찾는다.
ISSUED_TOKENS: set[str] = set()


def covers(item: str, *cells: str) -> None:
    for cell in cells:
        COVERED[item].add(cell)


#: 고치지 않고 보고할 관측(정책·계약 판단이 필요한 것). ``test_zz_inventory`` 가 실행 디렉터리에 적는다.
OBSERVATIONS: set[str] = set()
