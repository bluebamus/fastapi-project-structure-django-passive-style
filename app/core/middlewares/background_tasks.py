"""요청-밖 fire-and-forget 태스크의 상한(백프레셔) + 종료 시 drain 관리.

미들웨어(접속로그 저장)가 응답 후 던지는 백그라운드 태스크를 관리한다.

- **백프레셔**: 동시 실행 태스크를 ``max_concurrent`` 로 제한한다. 초과분은
  드롭하고 ``dropped`` 로 집계한다(요청 처리를 블로킹하지 않기 위해, 비핵심
  로그는 막지 않고 버린다). 상한이 없으면 고부하 시 태스크·커넥션이 무제한
  증가해 백그라운드 풀(pool_timeout) 대기가 누적된다.
- **Drain**: 앱 종료(lifespan shutdown)에서 in-flight 태스크를 기다린 뒤
  엔진을 정리하도록 ``drain()`` 을 제공한다. 이걸 빠뜨리면 진행 중이던 로그
  쓰기가 ``dispose_engine()`` 과 경합해 유실될 수 있다(검수 W1/REQ-009).

전역 싱글턴 ``access_log_tasks`` 를 미들웨어(spawn)와 main lifespan(drain)이
공유한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.utils.logs import get_logger

logger = get_logger("background_tasks")

# 동시 백그라운드 로그 태스크 상한 및 종료 drain 타임아웃(초).
# 정상 트래픽보다 넉넉하되 무제한 증가를 막는 안전판.
MAX_CONCURRENT_LOG_TASKS = 256
DRAIN_TIMEOUT_SECONDS = 5.0


class BackgroundTaskRunner:
    """동시 실행 상한과 종료 drain 을 갖춘 fire-and-forget 태스크 러너."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_LOG_TASKS) -> None:
        self._max = max_concurrent
        self._tasks: set[asyncio.Task[Any]] = set()
        self.dropped = 0

    @property
    def active(self) -> int:
        """추적 중인 in-flight 태스크 수."""
        return len(self._tasks)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> bool:
        """코루틴을 백그라운드 태스크로 실행한다.

        상한 도달 시 실행하지 않고 코루틴을 닫은 뒤 ``dropped`` 를 올린다.

        Returns:
            수락하여 태스크를 만들었으면 True, 상한 초과로 드롭했으면 False.
        """
        if len(self._tasks) >= self._max:
            self.dropped += 1
            coro.close()  # "coroutine was never awaited" 경고 방지
            logger.warning(
                "백그라운드 태스크 상한(%d) 초과 — 드롭(누적 %d)",
                self._max,
                self.dropped,
            )
            return False

        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def drain(self, timeout: float = DRAIN_TIMEOUT_SECONDS) -> None:
        """in-flight 태스크를 기다렸다가, 타임아웃분은 취소하고 예외까지 회수한다.

        정책은 **cancel-and-gather** 다. 반환 시점에 살아있는 태스크가 없다는 것을
        보장해야 호출자(lifespan)가 곧바로 ``dispose_engine()`` 을 호출해도 폐기된
        엔진으로 DB 를 만지는 경합이 생기지 않는다. 경고만 남기고 반환하면 그
        보장이 없다.

        타임아웃을 넘긴 로그는 유실을 허용한다 — 접속 로그는 비핵심이고, 종료를
        무한정 붙잡는 편이 더 나쁘다. 유실량은 경고 로그로 관측한다.
        """
        if not self._tasks:
            return
        pending = set(self._tasks)
        logger.info("백그라운드 태스크 drain 시작 — %d건 대기", len(pending))

        _, still_pending = await asyncio.wait(pending, timeout=timeout)
        for task in still_pending:
            task.cancel()

        # 완료분의 예외와 취소분의 CancelledError 를 여기서 모두 회수한다.
        # 회수하지 않으면 GC 시점에 "exception was never retrieved" 가 뜬다.
        results = await asyncio.gather(*pending, return_exceptions=True)
        failed = sum(
            1
            for r in results
            if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError)
        )

        if still_pending:
            logger.warning(
                "drain 타임아웃(%.1fs) — 미완료 %d건 취소(로그 유실)", timeout, len(still_pending)
            )
        if failed:
            logger.warning("drain 중 태스크 예외 %d건", failed)
        logger.info(
            "백그라운드 태스크 drain 완료 — 총 %d건(취소 %d, 예외 %d)",
            len(pending),
            len(still_pending),
            failed,
        )


# 미들웨어(spawn)와 lifespan(drain)이 공유하는 전역 싱글턴.
access_log_tasks = BackgroundTaskRunner()
