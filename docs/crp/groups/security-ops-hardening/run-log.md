# Run Log — security-ops-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이
> 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `d217bf2`) · 계획 · 조사
- **트리거:** 사용자 요청 REQ-001
- **조사:** `create_async_engine`/`create_engine`/`engine_from_config` grep — `app/core/db/session.py` 3곳(writer·`_create_read_engine`·background),
  `migrations/env.py` 1곳, 어디에도 `hide_parameters` 없음. sqladmin 0.32 소스: `Admin.login` 의 GET 은 `TemplateResponse(request, "sqladmin/login.html")`
  (컨텍스트 없음), `ModelView.list` 는 `has_operator` 필터에 `get_filtered_query(stmt, op, value, model)` 를 부른다, `OperationColumnFilter._is_date_type`
  은 `UTCDateTime`(TypeDecorator)을 날짜로 보지 않는다. Celery `Beat.init_loader()` 가 `loader.init_worker()` 로 include 를 import 한 뒤 일정을 읽는다.
- **신규 finding:** CRIT 0 · HIGH 1 · MED 2 · LOW 1 → ledger F-001 ~ F-004
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-19 · 구현 · 검증
- **변경:** 엔진 옵션 정본, 접속 로그 보존(설정·배치 삭제·태스크·beat 일정), 로그인 CSRF, 날짜 필터·관리 뷰 7개, 테스트 헬퍼 `tests/admin_login.py`, 문서.
- **fail-on-revert(대상 파일을 작업 폴더 밖에 복사 → 변이 → 지정 테스트 → 복원, 17개 변이 모두 감지):**
  - F-001: 정본 `{}` → 4 실패 · `migrations/env.py` 펼침 제거 → AST 생성 지점 검사 실패
  - F-002: 경계 `<`→`<=` 1 · 배치 커밋 제거 3 · 배치 반복 제거 2 · 보존 0 검사 제거 1 · `ge=0` 제거 1 · provider 누락 1 · beat 등록 제거 1
  - F-003: 파일 되돌림 → 수집 오류 · 검사 생략 7 · 레이트 리밋을 CSRF 앞에 4 · `==` 비교 1 · hidden 입력 제거 → 로그인 흐름 6 + 관리 페이지 3 errors
  - F-004: 관리 뷰 되돌림 2 · `on` 끝 경계 포함 1 · UTC 변환 없음 3 · 형식 오류 처리 제거 6
- **검사(`.env` 없는 저장소 밖 사본):** `scripts/review_gate.py --fast` 7단계 전체 통과(ruff format·check, mypy, bandit, pip-audit, pytest, OpenAPI fail-on-revert) ·
  `pytest -m "not mysql and not browser" -rsxX --cov=app` **1141 passed · 35 deselected · skip 0 · xfail 0 · coverage 97%** ·
  `-m "mysql or browser"` 수집 35건(로컬은 수집만 — 새 `test_mysql_access_log_retention.py` 포함). 작업 트리: mypy(규칙 파일 방법) 220 파일 이상 없음.
  실제 기동 스모크는 하지 않았다 — 런타임 DB 가 MySQL 전용이라(로컬 MySQL 접속 금지) `create_app()` 실조립 + SQLite + fakeredis 의 HTTP 테스트
  (`tests/core/test_admin_pages.py`·`test_admin_login_flow.py`)로 관리 로그인(CSRF 포함)·목록 날짜 필터를 확인했다. MySQL·browser 실행은 CI 몫.
- **신규 finding:** 0
- **수렴 판정:** `CONVERGED` (Open Fix 0)
