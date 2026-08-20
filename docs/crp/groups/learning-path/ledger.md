# Ledger — learning-path (발견 사항 대장)

> 발견(F/L)은 append-only. 상태만 바꾼다: Open → Fixed / Accepted / Rejected.

| ID | 심각도 | 발견일 | 내용 | 상태 | 근거·해소 |
|---|---|---|---|---|---|
| L-001 | HIGH | 2026-08-20 | Raw 층이 진입 문서 3종에서 통째로 누락 (`RawRepositoryBase` 0회) | **Fixed** | T-2 에서 해소. README `## ORM / Raw 데이터 접근` 신설 + ARCHITECTURE·QUICKSTART 서술 → 세 문서 전부 등장. 회귀: `REQUIRED_IN_ENTRY_DOCS` (`d74ab5a`·`7b907cf`) |
| L-002 | HIGH | 2026-08-20 | `project-guide/v1.0` 이 Phase 4~7 을 모른다 (산출물 9종 전부 0회) | **Fixed** | T-1 에서 해소. `docs/project-guide/v1.1/` 신설로 Phase 4~7 산출물 반영, v1.0 보존 (`9acbad8`) |
| L-003 | MED | 2026-08-20 | 진입 문서가 `project-guide` 를 가리키지 않는다 (0회) | **Fixed** | T-2 에서 해소. 세 진입 문서 전부 v1.1 로 링크. 회귀: 최소 3문서 + 버전 드리프트 검사 (`d74ab5a`·`7b907cf`) |
| L-004 | MED | 2026-08-20 | ORM/Raw 선택 기준이 학습 문서에 없다 (`requirements.md` 에만) | **Fixed** | T-1 에서 해소. `09-orm-vs-raw-decision.md` 신설 — 판단 기준 표, Raw 전용 제약 5종, 자주 틀리는 지점, 결과 API 의미 (`9acbad8`) |
| L-005 | LOW | 2026-08-20 | README 제목이 `FastAPI Default Project Structure` — 정체성 불일치 | **Fixed** | T-2 에서 해소. README 제목 교체 + 구조 트리 루트·clone URL·v1.1 문서 01~08 메타데이터의 같은 잔재도 정리. 회귀: 제목 검사 (`d74ab5a`·`7b907cf`) |
| L-006 | LOW | 2026-08-20 | README 구조 트리에 `catalog`·`reports` 실물이 없다 | **Fixed** | T-2 에서 해소. 구조 트리에 catalog·reports 실물 추가. 회귀: 트리 블록 한정 검사 (`d74ab5a`·`7b907cf`) |
| L-007 | HIGH | 2026-08-20 | `project-guide` 가 존재하지 않는 세션 API 3개를 가르친다 | **Fixed** | T-1 에서 해소. v1.1 에서 죽은 세션 API 3종 0회. 회귀: 죽은 심볼 검사가 v1.1 까지 훑는다 (`9acbad8`) |
| L-008 | HIGH | 2026-08-20 | 죽은 참조 검사가 `project-guide` 를 훑지 않는다 (`BASE_DOCS` 3종뿐) | **Fixed** | T-4a 에서 해소. `BASE_DOCS` 가 최신 버전 폴더를 자동 편입. 09 문서 추가만으로 케이스가 40→43 으로 늘어 실증됐다 (`9acbad8`) |
| L-009 | LOW | 2026-08-20 | README 목차의 `레이트 리밋` 앵커가 죽어 있다 — `102cfe9` 가 섹션을 지우며 목차 줄을 남겼다 | **Fixed** | T-2 중 목차를 손대다 발견, 줄 제거 (`d74ab5a`) |
| L-010 | MED | 2026-08-20 | `tests/browser/test_scalar_rendering.py` 2건이 부하에 따라 간헐 실패 — Scalar 는 지연 렌더링하는데 검사가 networkidle 이후 **고정 2.5초**만 기다렸다. 흔들리는 게이트로는 수렴을 판정할 수 없다 | **Fixed** | 변경을 stash 하고 재현해 이 그룹의 회귀가 아님을 먼저 확인. 기대 문자열이 나타날 때까지 250ms 폴링(20초 상한)으로 교체, 단정은 유지. 3연속 통과 (`d74ab5a`). **재발** — 폴링은 원인의 절반만 덮었다. 실제 원인은 L-012 참조 |
| L-011 | LOW | 2026-08-20 | `pyproject.toml` 의 `name` 이 `fastapi-default-project-structure` — L-005 와 같은 잔재 | **Accepted** | 이 그룹의 diff 는 문서·테스트로 한정(INV-L1)이고 `name` 변경은 `uv.lock` 재생성을 동반한다 → residual-risk RL-05 |
| L-012 | MED | 2026-08-20 | L-010 수정 후에도 `test_raw_example_section_renders` 가 재발. 본문에 `Sales Reports … /api/v1/reports/daily-sales … Show More` 가 보였다 — **타이밍이 아니라 접힘**이었다. Scalar 는 항목이 많으면 `Show More` 뒤로 접고, 접힌 동안 경로는 나오지만 **요약문은 DOM 에 없다**. 기다려서 풀리는 문제가 아니라 폴링만으로는 못 고친다 | **Fixed** | 기대 문자열이 안 보이면 보이는 `Show More` 를 눌러 펼친 뒤 다시 보도록 헬퍼를 고쳤다. 단정은 그대로. **5연속 통과** 확인 |
| L-013 | MED | 2026-08-20 | `docs_page` 픽스처가 `networkidle` 만 기다리고 **그리기 완료는 기다리지 않는다.** docstring 은 "Scalar 가 그려질 때까지 기다린 페이지" 라고 약속하는데 코드가 지키지 않았다. 게이트 명령(`-o addopts=`)으로 돌릴 때 빈 화면(body 102자)을 읽어 `test_scalar_page_renders` 가 실패했다 | **Fixed** | 픽스처가 본문 길이 1,000자에 도달할 때까지 폴링하도록 했다(20초 상한). 기다리기만 하고 단정하지 않는다 — 끝내 안 그려지면 테스트가 실패시킬 일이다. 게이트 동일 명령 3연속 + 전체 게이트 2연속 통과 |

## 참고 — L-007 상세

| 문서가 가르치는 것 | 코드 등장 | 실물 |
|---|---|---|
| `get_session()` | 0회 | `get_routed_db_session()` |
| `get_read_session()` | 0회 | `get_read_only_db_session()` (기능에서 43회 사용) |
| `get_write_session()` | 0회 | `get_writer_db_session()` (기능에서 40회 사용) |

출현 문서: `03-core-components-and-features.md` · `04-request-workflow.md` ·
`06-data-and-transaction-workflow.md`
