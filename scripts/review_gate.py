"""검수 게이트 — 흩어진 검사를 한 번에, 같은 순서로 돌린다 (requirements TEST-008).

여러 명령을 손으로 나눠 돌리면 두 가지가 조용히 생긴다. 하나는 **빠뜨리는 것**이고,
다른 하나는 **순서에 따라 결과가 달라지는 것**이다. 여기서 순서를 고정한다.

    uv run python -m scripts.review_gate            # 전체
    uv run python -m scripts.review_gate --fast     # MySQL 통합 제외
    uv run python -m scripts.review_gate --list     # 무엇을 도는지만 본다

설계에서 신경 쓴 것 셋:

**1. UTF-8 고정.** Windows 콘솔 기본값은 cp949 다. 게이트가 한글 실패 메시지를 찍다
   ``UnicodeEncodeError`` 로 죽으면, 보이는 것은 실제 결함이 아니라 인코딩 예외다.
   자기 stdout/stderr 뿐 아니라 **자식 프로세스**에도 ``PYTHONIOENCODING`` 을 넘긴다.

**2. 캐시·temp 격리.** 게이트를 두 개 동시에 돌려도 서로의 캐시를 밟지 않도록 실행마다
   고유 디렉터리를 준다. 이게 없으면 병렬 실행이 "가끔" 실패하고, 그 실패는 재현이
   안 돼서 결국 아무도 안 믿게 된다.

**3. 실패해도 끝까지 간다.** 첫 실패에서 멈추면 한 번에 하나씩만 고치게 된다. 전부
   돌리고 마지막에 요약한다 — 다만 종료 코드는 실패를 그대로 반영한다.

MySQL 통합은 **skip 을 실패로 본다**(NFR-012). 인프라가 없어서 안 돈 것과 돌아서
통과한 것은 다르고, 그 차이가 게이트에서 보이지 않으면 "전체 green" 이 거짓말이 된다.
로컬에서 컨테이너를 못 띄우는 상황이라면 ``--fast`` 로 **명시적으로** 빼야 한다.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: MySQL 통합 테스트가 **실행되지 않았을 때** pytest 가 내는 문장들.
#:
#: ``deselected`` 는 넣지 않는다 — `-m mysql` 은 나머지를 정상적으로 deselect 하므로
#: 성공 실행에도 항상 나타난다. 그걸 실패로 보면 게이트가 영원히 빨간불이다(실제로
#: 첫 실행에서 그렇게 됐다).
SKIP_MARKERS = ("skipped", "no tests ran")


def _force_utf8() -> None:
    """자기 출력 스트림을 UTF-8 로 고정한다.

    리다이렉트되면 ``TextIOWrapper`` 가 아닐 수 있으므로 확인하고 손댄다.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


@dataclass
class Step:
    """게이트 한 단계."""

    name: str
    argv: list[str]
    why: str
    #: 이 단계의 출력에 이 문자열이 있으면 종료 코드가 0 이어도 실패로 본다.
    forbidden: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


def build_steps(*, cache_dir: Path, include_slow: bool) -> list[Step]:
    """실행 순서대로 단계를 만든다.

    빠른 것부터 둔다 — 포맷 하나 틀린 것을 알려고 전체 테스트를 기다릴 이유가 없다.
    """
    python = sys.executable
    steps = [
        Step(
            name="ruff format",
            argv=[python, "-m", "ruff", "format", "--check", "."],
            why="포맷이 갈리면 diff 가 실제 변경을 가린다",
            env={"RUFF_CACHE_DIR": str(cache_dir / "ruff")},
        ),
        Step(
            name="ruff check",
            argv=[python, "-m", "ruff", "check", "."],
            why="lint",
            env={"RUFF_CACHE_DIR": str(cache_dir / "ruff")},
        ),
        Step(
            name="mypy",
            argv=[python, "-m", "mypy", "."],
            why="타입 계약",
            env={"MYPY_CACHE_DIR": str(cache_dir / "mypy")},
        ),
        Step(
            name="bandit (MEDIUM 이상)",
            argv=[python, "-m", "scripts.bandit_gate"],
            why="보안 정적 검사 — reporter 실패도 게이트 실패로 본다",
        ),
        Step(
            name="pytest (단위 + 계층 불변식 + 공개 API + OpenAPI 규칙)",
            argv=[
                python,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
                "-m",
                "not mysql and not browser",
            ],
            why="계층 불변식·공개 API baseline·OpenAPI 규칙이 모두 여기 들어 있다",
        ),
        Step(
            name="OpenAPI 규칙 fail-on-revert",
            argv=[python, "-m", "scripts.openapi_revert_check"],
            why="규칙이 실제로 결함을 잡는지 — 통과만으로는 알 수 없다",
        ),
    ]

    if include_slow:
        steps.append(
            Step(
                name="pytest -m mysql (skip 금지)",
                argv=[
                    python,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "addopts=",
                    "-m",
                    "mysql",
                    "-rsxX",
                ],
                why="방언 정확성은 SQLite 로 승인하지 않는다 (ADR-004)",
                # 인프라가 없어 안 돈 것과 돌아서 통과한 것은 다르다 (NFR-012).
                forbidden=SKIP_MARKERS,
            )
        )
        steps.append(
            Step(
                name="pytest -m browser (Scalar 실렌더링)",
                argv=[
                    python,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "-o",
                    "addopts=",
                    "-m",
                    "browser",
                    "-rsxX",
                ],
                why="스키마가 규격에 맞는 것과 화면이 그려지는 것은 다르다",
                forbidden=SKIP_MARKERS,
            )
        )
    return steps


def run_step(step: Step, *, env: dict[str, str]) -> tuple[bool, str]:
    """단계 하나를 돌리고 (성공 여부, 실패 사유) 를 돌려준다."""
    proc = subprocess.run(
        step.argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**env, **step.env},
    )
    output = (proc.stdout or "") + (proc.stderr or "")

    if proc.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-25:])
        return False, f"종료 코드 {proc.returncode}\n{tail}"

    hit = next((marker for marker in step.forbidden if marker in output), None)
    if hit is not None:
        tail = "\n".join(output.strip().splitlines()[-10:])
        return False, (
            f"통과했지만 '{hit}' 가 출력에 있다 — 인프라가 없어 실행되지 않았다는 뜻이다.\n"
            f"컨테이너를 띄우거나 --fast 로 명시적으로 제외할 것.\n{tail}"
        )
    return True, ""


def main(argv: list[str] | None = None) -> int:
    _force_utf8()

    parser = argparse.ArgumentParser(description="검수 게이트")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="MySQL 통합과 브라우저 테스트를 제외한다. 제외했다는 사실이 출력에 남는다.",
    )
    parser.add_argument("--list", action="store_true", help="실행하지 않고 단계만 출력한다")
    args = parser.parse_args(argv)

    # 실행마다 고유 캐시 — 게이트를 병렬로 돌려도 서로를 밟지 않는다.
    with tempfile.TemporaryDirectory(prefix="review-gate-") as tmp:
        cache_dir = Path(tmp)
        steps = build_steps(cache_dir=cache_dir, include_slow=not args.fast)

        if args.list:
            for index, step in enumerate(steps, 1):
                print(f"{index}. {step.name}\n   왜: {step.why}\n   {' '.join(step.argv[1:])}")
            return 0

        child_env = {
            **os.environ,
            # 자식 Python 의 stdio 도 UTF-8 로 고정한다 — 여기서 놓치면 도구가 한글
            # 출력을 하다 죽고, 그 죽음이 실제 결함을 가린다.
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTEST_ADDOPTS": "",
        }

        failures: list[tuple[str, str]] = []
        for index, step in enumerate(steps, 1):
            print(f"[{index}/{len(steps)}] {step.name} …", flush=True)
            ok, reason = run_step(step, env=child_env)
            if ok:
                print(f"      OK — {step.why}")
            else:
                print(f"      실패 — {reason}")
                failures.append((step.name, reason))

    print("\n" + "=" * 78)
    if args.fast:
        print(
            "주의: --fast 로 MySQL 통합과 브라우저 렌더링을 **실행하지 않았다**. "
            "방언 정확성과 Scalar 화면은 승인되지 않았다."
        )
    if failures:
        print(f"실패 {len(failures)}건:")
        for name, _ in failures:
            print(f"  - {name}")
        return 1
    print(f"전체 통과 ({len(steps)}단계).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
