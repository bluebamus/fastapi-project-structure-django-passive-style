"""Bandit MEDIUM 이상 게이트 — reporter 실패까지 게이트 실패로 보고한다.

`bandit` 을 그대로 부르면 두 가지 방식으로 조용히 무너진다.

1. **txt reporter 가 콘솔 인코딩으로 쓴다.** 한글이 섞인 리포트를 cp949 콘솔에
   출력하는 순간 ``UnicodeEncodeError`` 로 죽는다. 그러면 검사 결과가 아니라 도구
   크래시가 보이고, 그 크래시 뒤에 진짜 결과가 사라진다(ledger F-008).
2. **리포트가 안 나와도 종료 코드가 0 일 수 있다.** reporter 가 실패하면 "검사한
   적 없음"인데 게이트는 초록불이 된다.

그래서 JSON reporter(항상 UTF-8)로 파일에 받고, **파일이 실제로 생겼는지**까지
확인한 뒤 결과를 판정한다. 실패 시 stdout 과 stderr 를 함께 보존해 요약이 traceback
을 가리지 않게 한다.

임시 파일은 실행별 고유 디렉터리에 만들고 끝나면 지운다 — 공유 경로를 쓰면 앞선
실행의 잔재가 이번 결과에 섞인다.

    python -m scripts.bandit_gate            # 기본 대상: app main.py config.py
    python -m scripts.bandit_gate app        # 대상 지정
"""

from __future__ import annotations

import io
import json
import subprocess  # noqa: S404 - bandit 을 실행하는 것이 이 스크립트의 목적이다
import sys
import tempfile
from pathlib import Path

#: 기본 검사 대상. 테스트 코드는 assert·하드코딩 문자열 오탐이 대부분이라 제외한다.
DEFAULT_TARGETS = ("app", "main.py", "config.py")

#: MEDIUM 이상만 게이트로 삼는다 (bandit ``-ll`` 과 같은 의미).
BLOCKING_SEVERITIES = {"MEDIUM", "HIGH"}


def run_gate(targets: tuple[str, ...] = DEFAULT_TARGETS) -> int:
    """bandit 을 돌리고 종료 코드를 돌려준다. 0 = 통과."""
    with tempfile.TemporaryDirectory(prefix="bandit-gate-") as tmp_dir:
        report_path = Path(tmp_dir) / "bandit.json"

        proc = subprocess.run(  # noqa: S603 - 인자가 이 파일에 고정돼 있다
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "bandit",
                "-ll",
                "-r",
                *targets,
                "-f",
                "json",
                "-o",
                str(report_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # 도구 출력 인코딩이 어긋나도 게이트가 죽지 않게
            check=False,
        )

        # 판정 전에 먼저 다 보여준다 — 요약이 traceback 을 가리면 원인을 못 찾는다.
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)

        if not report_path.is_file() or report_path.stat().st_size == 0:
            print(
                "::error::bandit 리포트가 생성되지 않았습니다 — reporter 자체가 실패했습니다.",
                file=sys.stderr,
            )
            return 1

        report = json.loads(report_path.read_text(encoding="utf-8"))

    blocking = [
        issue
        for issue in report.get("results", [])
        if issue.get("issue_severity") in BLOCKING_SEVERITIES
    ]
    for issue in blocking:
        print(
            f"{issue['issue_severity']} {issue['filename']}:{issue['line_number']} "
            f"{issue['issue_text']}"
        )

    if blocking:
        print(f"::error::bandit MEDIUM 이상 {len(blocking)}건", file=sys.stderr)
        return 1

    scanned = len(report.get("metrics", {})) - 1  # _totals 제외
    print(f"bandit MEDIUM 이상 0건 (검사 파일 {scanned}개)")
    return 0


if __name__ == "__main__":
    # 게이트가 **실패를 보고하는 순간** 죽지 않게 자기 stdio 부터 UTF-8 로 돌린다.
    # 한글 결과를 cp949 콘솔에 쓰면 UnicodeEncodeError 가 나고, 그 크래시가 진짜
    # 실패를 덮는다 — 정확히 그 사고를 막으려고 만든 스크립트가 같은 이유로 죽는 꼴.
    for stream in (sys.stdout, sys.stderr):
        # 리다이렉트되면 TextIOWrapper 가 아닐 수 있다 — 그때는 손대지 않는다.
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")

    raise SystemExit(run_gate(tuple(sys.argv[1:]) or DEFAULT_TARGETS))
