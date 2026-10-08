"""검수 게이트의 판정 규칙 — 로컬 게이트와 CI 가 같은 것을 막는가 (ADR-038)."""

from __future__ import annotations

from pathlib import Path

from scripts.bandit_gate import DEFAULT_TARGETS, judge
from scripts.review_gate import build_steps

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bandit_unparsed_files_fail_the_gate():
    """파싱 못 한 파일은 검사되지 않았다 — ``results`` 가 비어도 실패다."""
    assert judge({"results": [], "errors": []}) == []
    unparsed = {"results": [], "errors": [{"filename": "app/x.py", "reason": "syntax error"}]}
    assert judge(unparsed), "bandit errors 가 게이트를 통과했다"
    medium = {
        "results": [
            {
                "issue_severity": "MEDIUM",
                "filename": "app/x.py",
                "line_number": 1,
                "issue_text": "t",
            }
        ]
    }
    assert judge(medium)
    assert "scripts" in DEFAULT_TARGETS


def test_local_pytest_steps_apply_the_same_rules_as_ci(tmp_path):
    """`-o addopts=` 가 지우는 규칙을 각 pytest 단계가 다시 명시하는가."""
    steps = [s for s in build_steps(cache_dir=tmp_path, include_slow=True) if "pytest" in s.argv]
    assert len(steps) == 3
    for step in steps:
        assert "--strict-markers" in step.argv, step.name
        assert {"skipped", "xfailed", "xpassed"} <= set(step.forbidden), step.name
    unit = steps[0]
    assert "--cov=app" in unit.argv


def test_coverage_threshold_has_one_source():
    """하한은 pyproject 하나 — 명령줄에 따로 적으면 로컬과 CI 가 갈린다."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "\nfail_under = 85\n" in pyproject
    assert "--cov-fail-under" not in workflow
    assert "scripts.openapi_revert_check" in workflow
