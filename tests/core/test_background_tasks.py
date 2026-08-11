"""BackgroundTaskRunner 회귀 테스트 (검수 W1/REQ-009).

미들웨어 접속로그 저장을 fire-and-forget 로 던지되,
- 동시 실행 태스크 수에 상한을 두어(백프레셔) 고부하 시 무제한 증가를 막고,
- 앱 종료 시 in-flight 태스크를 drain 하여 마지막 로그 유실/엔진 경합을 줄인다.
"""

import asyncio

from app.core.middlewares.background_tasks import BackgroundTaskRunner


async def test_backpressure_drops_tasks_over_capacity() -> None:
    runner = BackgroundTaskRunner(max_concurrent=2)
    gate = asyncio.Event()

    async def blocked() -> None:
        await gate.wait()

    accepted = [runner.spawn(blocked()) for _ in range(5)]

    assert accepted.count(True) == 2, "상한(2)까지만 수락해야 함"
    assert runner.dropped == 3, "초과분 3건은 드롭·집계되어야 함"

    gate.set()
    await runner.drain(timeout=1.0)


async def test_drain_waits_for_inflight_tasks() -> None:
    runner = BackgroundTaskRunner(max_concurrent=10)
    done: list[int] = []

    async def work(i: int) -> None:
        await asyncio.sleep(0.01)
        done.append(i)

    for i in range(5):
        assert runner.spawn(work(i)) is True

    await runner.drain(timeout=2.0)

    assert sorted(done) == [0, 1, 2, 3, 4], "drain 은 모든 in-flight 태스크 완료를 기다려야 함"


async def test_completed_tasks_are_not_retained() -> None:
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def quick() -> None:
        return None

    assert runner.spawn(quick()) is True
    await runner.drain(timeout=1.0)

    assert runner.active == 0, "완료된 태스크는 추적 집합에서 제거되어야 함(누수 방지)"


# ---------------------------------------------------------------------------
# drain 이 반환하면 lifespan 은 곧바로 dispose_engine() 을 호출한다.
# 그때까지 살아있는 태스크가 남아 있으면 폐기된 엔진으로 DB 를 만지게 된다.
# "경고만 하고 반환" 은 그 경합을 막지 못한다 (계획서 P2-2).
# ---------------------------------------------------------------------------


async def test_drain_cancels_tasks_that_exceed_timeout() -> None:
    runner = BackgroundTaskRunner(max_concurrent=5)
    started = asyncio.Event()

    async def never_finishes() -> None:
        started.set()
        await asyncio.sleep(3600)

    assert runner.spawn(never_finishes()) is True
    await started.wait()

    await runner.drain(timeout=0.05)

    assert runner.active == 0, "drain 반환 시 추적 중인 미완료 태스크가 없어야 함"


async def test_drain_retrieves_task_exceptions() -> None:
    """실패한 태스크의 예외를 회수한다 — 안 하면 GC 때 asyncio 경고가 뜬다."""
    runner = BackgroundTaskRunner(max_concurrent=5)

    async def boom() -> None:
        raise RuntimeError("로그 쓰기 실패")

    assert runner.spawn(boom()) is True
    await runner.drain(timeout=1.0)

    assert runner.active == 0


async def test_drain_on_empty_runner_is_noop() -> None:
    runner = BackgroundTaskRunner(max_concurrent=5)
    await runner.drain(timeout=0.01)
    assert runner.active == 0
