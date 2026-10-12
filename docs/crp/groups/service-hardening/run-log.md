# Run Log — service-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-12 (base SHA: `f7d6dcc`) · 계획
- **트리거:** 사용자 요청 REQ-001(제안 1~9, Redis 필수, 로그인 고도화)
- **검수 범위:** 2026-10-07 전체 검수 보고서의 미착수 지적(R-01~R-10, R-15~R-21, 관련 Low) + 제안 1
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 □ 4 □ 5 □ (계획 단계 — 코드 변경 없음)
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 16 · LOW 8
- **신규 Fix(계약 위반):** 25 건 → ledger F-001 ~ F-025
- **수렴 판정:** `NOT CONVERGED` (Open Fix 25)
- **잔여 위험 변화:** R-001 ~ R-006 등록
- **기준선:** `pytest -m "not mysql and not browser"` 713 passed · 22 deselected · skip 0

### Round 1 — 2026-10-12 (base SHA: `a7ab7ca`) · 단계 A
- **트리거:** REQ-001 단계 A (제안 1·2·3) — ADR-001~ADR-004
- **검수 범위:** F-001 ~ F-004 (`a7ab7ca` 이후 단계 A 커밋)
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■ (단계 A 한정)
- **변경:**
  - A1: `.github/workflows/ci.yml` gate·mysql job 의 `uv sync --locked`, 주석을 사실대로. `DEVELOPMENT.md` CI 표.
    `scripts/review_gate.py` 는 작업 트리를 `rglob` 으로 훑지 않으므로 `git ls-files` 전환 대상이 없다.
  - A2: `config.py` — `MYSQL_URL`·`MYSQL_WRITER_URL`·`MYSQL_REPLICA_URLS`·`ALEMBIC_URL` 이 `URL` 을 돌려준다.
    `format_host` → `bare_host`(대괄호 벗기기, 렌더링은 `URL` 이 한다), `split_host_port` 는 맨 호스트를 돌려준다.
    `mask_dsn` 삭제 → `describe_routing` 이 `render_as_string(hide_password=True)`. `REDIS_URL` 비밀번호 `quote(safe="")`.
    `migrations/env.py` 가 `%` → `%%`. `session.py` 의 replica 엔진 인자 타입. `ARCHITECTURE.md` §10·라우팅 절.
  - A3: `router.py` `_is_locking_select()` — `_is_write`·`_statement_is_readable` 이 잠금 읽기를 쓰기로 본다.
    `repository_base.get_all` 기본 정렬(`created_at DESC, PK DESC`), 공개 메서드 8개 유지.
    `user_access_log_repository` 4개 쿼리에 `id desc` 보조 키. catalog `active_only=false` 의 OpenAPI 설명과
    `ARCHITECTURE.md`·`DEVELOPMENT.md`·`feature-development-guide.html` 의 "정렬 없음" 서술 정정.
- **새 테스트와 fail-on-revert(수정 전 코드에서 실행):**
  - `test_security_hardening.py::test_ci_installs_dependencies_with_locked` — 실패 확인
  - `test_dsn.py` 9건 — 6건 실패 확인(writer·replica 왕복, ALEMBIC 2건, Alembic `%` 이스케이프, Redis 특수문자).
    마스킹·평문 Redis·무비밀번호 Redis 3건은 기존 동작을 고정하는 가드라 수정 전에도 통과한다.
    `%` 이스케이프는 `env.py` 한 줄만 되돌려 다시 실패함을 확인했다(복사본으로 복원).
  - `test_read_only_guard.py::test_locking_select_is_blocked[router_off/router_on]` — 둘 다 실패 확인
  - `test_db_router.py::test_locking_select_is_served_by_writer` — 실패 확인(`['reader']`)
  - `test_repository_base.py` 정렬 2건 — 둘 다 실패 확인(삽입 순서로 나왔다)
  - `home/tests/test_access_log_service.py::test_time_ordered_queries_break_ties_by_id` — 실패 확인
  - 기존 `test_db_router.py` 의 DSN 문자열 비교 7곳을 `make_url` 의미 비교·`.host` 비교로 바꿨다
- **검사:** ruff check 통과 · ruff format --check 327 파일 · mypy 204 파일 이슈 0
  (로컬 정책이 컴파일된 mypy `.pyd` 를 차단해 같은 버전 1.20.2 의 순수 Python 빌드로 실행) ·
  `pytest -m "not mysql and not browser"` **729 passed · 22 deselected · skip 0** · `--cov=app` **94.01%** ·
  bandit MEDIUM 이상 0(236 파일) · pip-audit 0건 · OpenAPI revert check 20/20 감지 ·
  alembic 단일 head·SQLite `upgrade head` + `alembic check` 통과 · `mysql`/`browser` 22건 수집 확인(실행은 CI)
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 A `CONVERGED` (F-001~F-004 Fixed). 그룹 전체는 `NOT CONVERGED` (Open Fix 21)
- **잔여 위험 변화:** 없음 (R-004 는 이번 라운드 결정의 한계로 Round 0 에 이미 등록)

### Round 2 — 2026-10-12 (base SHA: `c49f24c`) · 단계 B
- **트리거:** REQ-001 단계 B (제안 4·5) — ADR-005~ADR-008, 신규 ADR-023~ADR-025
- **검수 범위:** F-005 ~ F-013 (`c49f24c` 이후 단계 B 커밋)
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■ (단계 B 한정)
- **변경:**
  - B1: `app/core/middlewares/client_ip.py` `ClientIPResolver`(신뢰 홉 수, `ipaddress` 검증, 짧은 체인·잘못된 값은 직접 피어).
    `config.MiddlewareSettings.TRUSTED_PROXY_HOPS`(기본 0, `ge=0`). `UserInfoMiddleware.__init__(app, ip_resolver)` —
    `setup_user_info_middleware()` 가 설정으로 한 번 만들어 주입한다. 기본값이 기존 동작(XFF 맨 왼쪽 신뢰)을 바꾼다 → ADR-023.
  - B2: `dispatch` 가 `call_next` 를 try 로 감싸 예외 시 500 으로 기록 후 재전파(`_record`). `_mask_query_string` 이
    `ACCESS_LOG_SENSITIVE_QUERY_KEYS`(대소문자 무시) 값을 `***` 로. 세션 쿠키는 `session_settings.SESSION_COOKIE_NAME`.
  - B3: home `user_access_log_service.truncate_to_columns` — `UserAccessLog.__table__` 의 `String(n)` 길이(Text 제외)로 자른다.
    core 는 모델을 모른다(계층 규칙 유지).
  - B4: `app/core/schemas.py` `PatchSchema`(`model_fields_set` 의 None 을 `nullable_fields` 밖이면 422). blog·catalog·reply·sns·user
    Update 스키마가 상속(`nullable_fields`: author / description / author / author / 없음). OpenAPI 스키마 출력은 바뀌지 않는다.
  - B5: `app/core/db/errors.py` — 1062/UNIQUE·PRIMARYKEY → 409, 1048·1364/NOTNULL → 422, 1452/FOREIGNKEY → 422, 1451 → 409, 그 외 500.
    SQLite 는 `sqlite_errorname` 으로 가른다(메시지 비파싱). 4xx 변환은 WARNING → ADR-024.
  - B6: `report_service.MIN_DATE/MAX_DATE`(1970-01-01..9998-12-31) — 넘으면 `InvalidDateRangeException`(422). 366일 상한은 기존.
  - B7: catalog `active_only` total = `count(is_active=True)`. `resources._prepare_database(resources, registry)` 가
    `app.state.app_registry` 로 `owned_tables(registry)`·`create_db_tables(registry=..., populate=False)`. `Apps.populate()` 가 다른
    목록이면 `ImproperlyConfigured`. `AppException` 핸들러 4xx WARNING(detail 제외)/5xx ERROR → ADR-025.
  - 문서: `.env.example`(새 키 2개, 세션 쿠키 소비처), `config.SessionSettings` docstring, `ARCHITECTURE.md`(설정 소비처 표, §6 접속 로그
    IP·마스킹·자르기, registry 멱등 규칙, lifespan DDL registry, 예외 로그 수준, §4.7 오류 변환 표, §11.3 알려진 제한),
    `DEVELOPMENT.md`(reports 기간, PATCH null 규칙), `server-lifecycle-guide.html`(설정 부록·소비처 표·_prepare_database),
    `README.md`(reports 기간), `app/core/tags_metadata.py`(Home 태그 설명 — OpenAPI 태그 설명 문구만 바뀜, 스냅샷 기준선 없음).
- **새 테스트와 fail-on-revert(대상 파일을 HEAD 내용으로 바꿔 실행 후 복원):**
  - `tests/core/test_access_log_collection.py` 14건 — 미들웨어를 HEAD 로(생성자에 `ip_resolver` 인자만 허용) 되돌리면
    `test_unhandled_exception_is_recorded_as_500`·`test_sensitive_query_values_are_masked`·`test_session_cookie_name_comes_from_settings`·
    `test_injected_resolver_decides_the_recorded_ip` 4건 실패 확인. `ClientIPResolver` 단위 9건과 재전파 가드 1건은 새 모듈·기존 동작을
    고정하는 테스트라 되돌림 대상이 없다(모듈이 없으면 수집 단계에서 실패).
  - `home/tests/test_access_log_service.py::test_long_strings_are_cut_to_the_column_length` — 실패 확인
  - `tests/core/test_patch_schema.py` 10건 — 스키마 5개를 되돌리면 7건 실패 확인(나머지 3건은 기반 클래스 자체 단위 테스트).
    catalog `test_explicit_null_on_a_not_null_column_is_422` 는 스키마만 되돌려도 B5 변환이 SQLite NOT NULL 을 422 로 답해 통과한다
    (이중 방어). B5 까지 되돌린 HEAD 에서는 409 였다.
  - `tests/core/test_db_error_conversion.py` 새 매핑 13건 — `errors.py` 를 되돌리면 10건 실패 확인(UNIQUE·PRIMARYKEY → 409,
    1213 → 500 3건은 기존 동작 고정). 기존 `test_other_integrity_violation_is_not_a_duplicate`(1452 → 500)·
    `test_dialect_without_error_code_falls_back_to_duplicate`(코드 없음 → 409)는 ADR-024 로 계약이 바뀌어 새 테스트로 대체했다.
  - reports `test_dates_outside_the_supported_range_are_rejected` 2건 — 실패 확인(9999-12-31 은 `OverflowError` → 500)
  - catalog `test_active_only_total_counts_only_active_products` — 실패 확인
  - `test_bootstrap.py::test_lifespan_creates_only_the_injected_registrys_tables` — `resources.py`·`session.py` 를 되돌리면 실패 확인
    (SQLite 파일에 실제 DDL 실행, 전역 registry 의 8개 앱 테이블이 생겼다)
  - `test_registry_lifecycle.py::test_populate_with_a_different_list_is_rejected` 3건 — 실패 확인
  - `test_bootstrap.py::test_client_error_app_exception_is_logged_as_warning_without_detail` — 실패 확인(5xx ERROR 가드는 통과)
  - 기존 `test_bootstrap.py` lifespan 테스트 8건은 새 시그니처(`owned_tables(registry)`, `app.state.app_registry`)에 맞춰 대역만 고쳤다
- **검사:** ruff check 통과 · ruff format --check 331 파일 · mypy 206 파일 이슈 0
  (로컬 정책이 컴파일된 mypy `.pyd` 를 차단해 같은 버전 1.20.2 의 순수 Python 빌드로 실행) ·
  `pytest -m "not mysql and not browser"` **777 passed · 22 deselected · skip 0** · `--cov=app` **94.96%** ·
  bandit MEDIUM 이상 0(238 파일) · OpenAPI revert check 20/20 감지 · `mysql`/`browser` 22건 수집 확인(실행은 CI) ·
  pip-audit 는 네트워크 단계라 생략(의존성 변경 없음)
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 B `CONVERGED` (F-005~F-013 Fixed). 그룹 전체는 `NOT CONVERGED` (Open Fix 12)
- **잔여 위험 변화:** R-007(신뢰 홉 수 설정 의존)·R-008(SQLite FK 방향 미구분) 등록

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 16 | 8 | 25 | NOT CONVERGED (계획) |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 4: F-001~F-004) | 단계 A CONVERGED · 그룹 Open 21 |
| 2 | 0 | 0 | 0 | 0 | 0 (Fixed 9: F-005~F-013) | 단계 B CONVERGED · 그룹 Open 12 |
