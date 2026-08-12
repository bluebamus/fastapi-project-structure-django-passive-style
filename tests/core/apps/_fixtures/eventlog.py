"""population 단계 순서를 관찰하기 위한 프로세스 로컬 이벤트 로그."""

EVENTS: list[str] = []


def record(phase: str, label: str) -> None:
    EVENTS.append(f"{phase}:{label}")


def reset() -> None:
    EVENTS.clear()
