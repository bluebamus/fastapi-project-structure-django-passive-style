"""BackgroundTaskRunner 회귀 테스트.

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


# =============================================================================
# drain — timeout 이후 취소 회수
# =============================================================================
async def test_drain_waits_for_tasks_that_finish_in_time():
    """제 시간에 끝나는 태스크는 그대로 완료된다."""
    runner = BackgroundTaskRunner()
    finished: list[str] = []

    async def quick() -> None:
        await asyncio.sleep(0.01)
        finished.append("done")

    runner.spawn(quick())
    await runner.drain(timeout=1.0)

    assert finished == ["done"]
    assert runner.cancelled == 0


async def test_drain_cancels_and_reaps_stragglers():
    """timeout 을 넘긴 태스크는 취소하고 **회수까지** 한다.

    취소만 하고 반환하면 태스크의 ``finally``(세션 rollback/close)가 실행되기 전에
    DB engine dispose 로 넘어간다. 그러면 이미 닫힌 pool 을 만지는 태스크가 남는다.
    """
    runner = BackgroundTaskRunner()
    cleaned: list[str] = []

    async def straggler() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            # 실제 코드에서는 여기가 session.rollback()/close() 다.
            cleaned.append("cleanup")

    runner.spawn(straggler())
    await runner.drain(timeout=0.05)

    assert cleaned == ["cleanup"], "취소한 태스크의 finally 가 실행되지 않았다"
    assert runner.cancelled == 1
    assert runner.active == 0, "추적 집합이 비워지지 않았다"


async def test_drain_budget_leaves_room_for_cancellation():
    """대기 예산과 취소 회수 예산이 분리돼 있다.

    바깥 guard 와 같은 값을 대기에 쓰면 취소 회수 도중 잘린다 — 정확히 그
    회수가 필요한 순간에.
    """
    from app.core import resources

    assert 0 < resources.DRAIN_WAIT_RATIO < 1, "대기 몫이 전체 예산과 같으면 회수가 잘린다"

    wait_budget = resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS * resources.DRAIN_WAIT_RATIO
    reclaim_budget = resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS - wait_budget
    assert (
        reclaim_budget >= 1.0
    ), f"취소 회수 예산이 {reclaim_budget:.1f}s 뿐이다 — finally 가 끝나기 전에 잘린다"
