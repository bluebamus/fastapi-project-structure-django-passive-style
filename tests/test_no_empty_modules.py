"""git 이 추적하는 ``.py`` 중 내용 없는 파일이 없다 — ``__init__.py`` 는 패키지 표식이라 예외.

빈 ``test_db.py`` 는 테스트가 있는 것처럼 보이게 하고, 빈 모듈은 "여기 뭔가 있어야 하나" 를
묻게 한다. 2026-11-11 에 기능 자리채움으로 남은 12개를 지우며 재발을 막으려 둔다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def empty_python_files(root: Path) -> list[str]:
    # shortcut: git 체크아웃에서만 돈다(소스 압축본이면 실패), 압축본 배포가 생기면 작업 트리 순회로 대체한다.
    listed = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z", "*.py"],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [
        path
        for path in listed.split("\0")
        if path
        and path.rsplit("/", 1)[-1] != "__init__.py"
        and (root / path).is_file()
        and (root / path).stat().st_size == 0
    ]


def test_only_tracked_empty_modules_are_reported(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S607
    (tmp_path / "pkg").mkdir()
    for name, text in {
        "__init__.py": "",
        "empty.py": "",
        "full.py": "x = 1\n",
        "untracked.py": "",
    }.items():
        (tmp_path / "pkg" / name).write_text(text, encoding="utf-8")
    subprocess.run(  # noqa: S607
        ["git", "add", "pkg/__init__.py", "pkg/empty.py", "pkg/full.py"], cwd=tmp_path, check=True
    )

    assert empty_python_files(tmp_path) == ["pkg/empty.py"]


def test_repository_has_no_empty_modules() -> None:
    assert empty_python_files(REPO_ROOT) == []
