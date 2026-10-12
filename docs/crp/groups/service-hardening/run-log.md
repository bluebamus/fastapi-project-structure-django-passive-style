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

### Round 3 — 2026-10-12 (base SHA: `2dd6706`) · 단계 C
- **트리거:** REQ-001 단계 C (제안 6) — ADR-009, 신규 ADR-026
- **검수 범위:** F-014 ~ F-016 (`2dd6706` 이후 단계 C 커밋)
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 □ (F-015 는 CI mysql job 판정 대기)
- **변경:**
  - C1: `tests/session_overrides.py` `sqlite_session_overrides(app, *, on_session=None)` — writer 는 `using_writer`, read-only 는
    `mark_read_only` 를 거친 세션을 yield(운영 `get_writer_db_session`·`get_read_only_db_session` 과 같은 표시). 전환한 파일:
    `app/features/{auth,blog,catalog,reply,reports,sns,user}/tests/test_endpoint.py`, `app/features/{auth,blog,catalog}/tests/test_transaction_boundary.py`,
    `tests/test_validate_before_commit.py`. 커밋 집계는 `on_session` 훅으로 옮겼다. `test_validate_before_commit` 의 `except: rollback`
    은 운영 의존성처럼 세션 `__aexit__` 에 맡겼다. 전환 후 기존 테스트 121건이 모두 통과 — 읽기 전용 경로의 숨은 쓰기는 없었다.
  - C2: `tests/integration/test_mysql_orm_smoke.py`(`mysql` 마커) — catalog `CatalogService` CRUD, 같은 `created_at` 5행의 2개씩 offset
    페이지(비중복·DB 의 `id DESC` 순서와 일치·재질의 동일), `UserRepository.create` "Kim" → "kim" 이 1062 → `DuplicateException`(409)
    (컬럼 콜레이션 `utf8mb4_unicode_ci` 와 `get_by_username("KIM")` 도 단언), `ProductRepository.update(id, {"name": None})` 가 1048 →
    `ValidationException`(422)·값 보존, `UserAccessLogService.create_access_log` 가 긴 값(5000자 경로·500자 OS 등)을 컬럼 길이로 잘라 저장.
    strict 모드(`STRICT_TRANS_TABLES`)를 전제로 단언한다.
  - C3: `tests/core/test_migration_chain.py` 가 `config.db_settings` 를 호출 시점에 patch. 루트 `conftest.py` 에 `restore_config`
    (모듈 dict 스냅샷 복원) — `test_security_hardening.py` 의 reload 3곳과 `test_deployment_safety.py::load_config` 가 공용으로 쓴다
    (reload 로 "복구" 하던 코드는 지웠다).
  - 문서: `docs/guides/DEVELOPMENT.md` §6.2(세션 오버라이드 헬퍼·`restore_config`·호출 시점 patch),
    `docs/guides/feature-development-guide.html`(endpoint 테스트 문단).
- **새 테스트와 fail-on-revert(대상 파일을 작업 폴더 밖에 복사해 두고 수정 전 내용을 넣어 실행 후 복원):**
  - `tests/test_session_overrides.py::test_read_only_override_rejects_a_sneaky_write`·`test_writer_override_is_pinned_to_the_writer` —
    헬퍼에서 `mark_read_only`·`using_writer` 를 빼면 둘 다 실패 확인(DID NOT RAISE / pinned False)
  - `test_session_dependencies_are_overridden_only_through_the_helper` — `app/features/user/tests/test_endpoint.py` 를 전환 전(main)
    내용으로 되돌리면 실패 확인. `test_detector_sees_the_helper_itself` 는 탐지기 자체 검사(헬퍼의 두 줄을 찾는다)
  - `tests/core/test_migration_chain.py::test_upgrade_follows_the_patch_after_a_config_reload` — `_upgrade_to_head` 를 import 시점
    객체 patch 로 되돌리면 실패 확인. reload 된 설정에는 `tmp_path` 의 미끼 SQLite URL 을 심어 되돌린 코드도 실제 DB 에 닿지 않는다
  - `tests/integration/test_mysql_orm_smoke.py` 5건 — MySQL 이 없어 로컬 실행 불가(docker 금지). 수집 확인 + 방언 무관한 3건
    (CRUD·정렬·NOT NULL 흐름)과 자르기 1건을 SQLite 세션으로 별도 실행해 API 사용 오류가 없음을 확인(그 과정에서 rollback 뒤 만료된
    인스턴스 접근을 고쳤다). 콜레이션·strict 단언은 CI 에서만 판정된다
- **검사:** ruff check 통과 · ruff format --check 334 파일 · mypy 206 파일 이슈 0
  (로컬 정책이 컴파일된 mypy `.pyd` 를 차단해 같은 버전 1.20.2 의 순수 Python 빌드로 실행) ·
  `pytest -m "not mysql and not browser" -p no:randomly --cov=app` **782 passed · 27 deselected · skip 0** · coverage **94.96%** ·
  같은 마커식으로 테스트 파일 68개를 **역순**으로 명시 실행 782 passed(security_hardening → migration_chain 순서 포함) ·
  `-m "mysql or browser" --collect-only` 27건 수집 · bandit MEDIUM 이상 0(238 파일) · OpenAPI revert check 20/20 감지 ·
  `scripts.review_gate --fast`: ruff·bandit·pip-audit·OpenAPI 통과, mypy 는 로컬 `.pyd` 차단(위 순수 빌드로 대체), pytest 단계는
  F-026(커버리지 문구 오인)으로 실패 표시 — 같은 실행의 요약은 782 passed · skip 0
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 1 (F-026, Accept-out-of-scope)
- **수렴 판정:** 단계 C `NOT CONVERGED` 1건 — F-015 가 CI mysql job 그린과 단계 D(시각 왕복)를 기다린다. F-014·F-016 Fixed.
  그룹 전체는 `NOT CONVERGED` (Open Fix 10)
- **잔여 위험 변화:** R-009(review_gate 의 커버리지 문구 오인) 등록

### Round 4 — 2026-10-12 (base SHA: `302a028`) · 단계 D
- **트리거:** REQ-001 단계 D (제안 7) — ADR-010, 신규 ADR-027
- **검수 범위:** F-017, F-015 의 시각 왕복 부분 (`302a028` 이후 단계 D 커밋)
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 □ (F-015 는 CI mysql job 판정 대기)
- **변경:**
  - D1: `app/core/models/types.py` `UTCDateTime`(impl `DateTime`, MySQL `DATETIME(fsp=6)` 은 `load_dialect_impl`, `cache_ok=True`;
    bind aware → UTC naive, naive → `ValueError`, None 통과; result tzinfo=UTC)와 Alembic 렌더 훅 `render_item`.
    `models_base.py` 의 `type_annotation_map`·`CreatedAtMixin`·`UpdatedAtMixin`(default/onupdate `timezone_settings.utc_now`, `sort_order` 그대로),
    reports `ordered_at` 은 명시 `DateTime(timezone=True)` 를 지워 `Mapped[datetime]` 으로. `config.py` `TimezoneSettings.utc_now()`·`local_midnight_utc()`
    (`now()` 는 로그 파일명 등 표시용으로 유지). `migrations/env.py` 가 온라인·오프라인 모두 `render_item` 을 건다.
  - D2: `migrations/versions/e5a7c2d9f310_store_datetimes_as_utc.py`(down `d1f8c4a70b93`) — MySQL 에서만 14개 시각 컬럼을
    `DATETIME(6) NOT NULL` 로 넓힌 뒤 `CONVERT_TZ(col,'+09:00','+00:00')`, downgrade 는 역변환 후 `DATETIME`. SQLite no-op.
    head 참조: `docs/guides/ARCHITECTURE.md` revision 체인. CI 는 revision 번호를 적지 않아 바꿀 곳이 없다.
  - D3: `ReportService(session, timezone)` — 경계는 `local_midnight_utc(start)`·`local_midnight_utc(end+1)`, 오프셋은 시작일 0시의 값.
    `SalesReportRawRepository.daily_sales(start_at, end_exclusive, utc_offset)` 가 방언으로 SQL 을 고른다(MySQL `CONVERT_TZ`, SQLite
    `DATE(col,'+540 minutes')`), 경계는 `bindparam(type_=UTCDateTime())`, `GROUP BY sales_date`, 각 SQL 에 `ponytail:` 주석.
    접속 로그: `UserAccessLogService.get_logs_by_date_range(date, date)` 가 지역 일자를 UTC 반열린 구간으로 바꾸고, Repository
    `get_by_date_range(start_at, end_exclusive)` 는 `<` 상한. provider 두 곳이 `timezone_settings` 를 넘긴다.
  - D4: `app/celery/app.py` `enable_utc=True`. 응답 스키마 6개(blog·catalog·reply·sns·user·access_log)의 `created_at`/`updated_at`
    설명 "(UTC, 오프셋 포함 ISO 8601)", catalog 목록 예시 `Z`. `tests/test_response_serialization.py` 는 aware UTC → `Z` 를 이미 고정하고
    있어 바꾸지 않았다. 살아 있는 OpenAPI 스냅샷 비교는 없고 orm-raw-repository `baseline/openapi.json` 은 Phase 0 기록이라 두었다.
  - 테스트 조정(이유 기록): `test_mysql_migration_roundtrip.py::test_new_revisions_have_a_working_downgrade` 의 첫 `-1` 이 이제 시각
    revision 이다 — 테이블이 남고 정밀도가 0 으로 돌아오는지 보는 단계를 더했다(검사를 줄이지 않았다). `test_mysql_sales_report.py`·
    `test_raw_dml_workflow.py` 는 새 시그니처(UTC 순간·오프셋)와 Raw 시각 bind 를 `UTCDateTime` 으로. `test_access_log_service.py` 의
    동률 페이지 테스트는 반열린 상한(`same + 1µs`)으로. `test_mysql_orm_smoke.py` docstring 의 "DATETIME 은 초 단위" 서술 정정.
  - 문서: `ARCHITECTURE.md` §4.8(시각 규칙)·§9(Celery)·revision 체인, `DEVELOPMENT.md` §3.5(영업일 경계·방언별 버킷),
    `feature-development-guide.html`(reports 문단), `.env.example` `TIME_ZONE` 설명.
- **새 테스트와 fail-on-revert(대상 파일을 작업 폴더 밖에 복사해 두고 수정 전 내용 또는 변이를 넣어 실행 후 복원):**
  - `tests/core/test_utc_datetime.py` 13건 — naive 검사 제거 → `test_naive_datetime_is_rejected_at_bind`·`test_naive_value_never_reaches_the_database`
    실패, UTC 변환 제거 → `test_aware_kst_is_bound_as_naive_utc`·SQLite 왕복 실패, UTC 부착 제거 → result·SQLite 왕복·모델 기본값 3건 실패,
    fsp 제거 → `test_mysql_column_is_datetime_with_microseconds` 실패, 렌더 훅 무력화 → 렌더 2건 실패, `models_base.py` 를 main 으로 →
    `test_every_model_datetime_column_uses_utc_datetime`·`test_model_default_timestamps_are_aware_utc`·catalog 오프셋 테스트 실패,
    reports `models.py` 를 main 으로 → 컬럼 타입 테스트 실패. `utc_now`·`local_midnight_utc` 2건은 새 메서드라 수정 전 코드에서 AttributeError.
  - `app/features/catalog/tests/test_endpoint.py::test_timestamps_are_utc_with_an_offset` — `models_base.py` main 에서 실패 확인. 기본값만
    `now()`(KST aware)로 바꾸는 변이는 통과한다 — 같은 순간이 저장 경계에서 UTC 로 바뀌므로 결함이 아니다
  - `app/features/reports/tests/test_business_day.py` 7건 — Service 경계를 UTC 0시로 바꾸면 경계 2건(단위·자정 경계) 실패, SQLite 버킷의
    오프셋 이동을 지우면 엔드포인트 2건 실패. `mysql_offset` 4건은 새 함수
  - `app/features/home/tests/test_access_log_service.py::test_date_range_is_read_as_local_days` — Service 를 main 으로 또는 UTC 일자 경계로
    바꾸면 실패
  - `tests/core/test_celery_app.py::test_celery_keeps_internal_times_in_utc` — `app/celery/app.py` main 에서 실패
  - MySQL(`mysql` 마커, CI 판정): `tests/integration/test_mysql_time_policy.py` 3건(전 시각 컬럼 `DATETIME_PRECISION` 6, KST aware →
    UTC 벽시계·마이크로초 왕복, 2026-01-01T15:30Z 주문이 1월 2일 버킷), `test_mysql_migration_roundtrip.py::test_utc_revision_converts_existing_kst_values`
    (이전 head 에서 Raw SQL 로 KST 값을 심고 revision 만 올려 UTC·정밀도 6 확인, downgrade 로 원값·정밀도 0 복귀 — `mysql_empty_schema` 가
    전후로 비워 남는 테이블 0 불변식 유지). 로컬은 `--collect-only` 31건 수집과 `alembic upgrade d1f8c4a70b93:e5a7c2d9f310 --sql`(MySQL
    오프라인 렌더, 접속 없음)로 DDL·UPDATE 문을 확인했다
- **검사:** ruff check 통과 · ruff format --check 338 파일 · mypy 207 파일 이슈 0
  (로컬 정책이 컴파일된 mypy `.pyd` 를 차단해 같은 버전 1.20.2 의 순수 Python 빌드로 실행) ·
  `pytest -m "not mysql and not browser"` **805 passed · 31 deselected · skip 0** · `--cov=app` **95.12%** ·
  `-m "mysql or browser" --collect-only` 31건 · `python -m alembic heads` 단일 head `e5a7c2d9f310` · SQLite `upgrade head` + `alembic check`
  "No new upgrade operations detected" · downgrade `d1f8c4a70b93` → 재-upgrade 통과 · bandit MEDIUM 이상 0(240 파일) ·
  OpenAPI revert check 20/20 감지 · `scripts.review_gate --fast`: ruff·bandit·pip-audit·pytest·OpenAPI 통과, mypy 는 로컬 `.pyd` 차단(위 순수 빌드로 대체)
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 D `CONVERGED` (F-017 Fixed) — MySQL 방언 판정은 F-015 와 함께 CI mysql job. 그룹 전체는 `NOT CONVERGED` (Open Fix 9)
- **잔여 위험 변화:** R-010(고정 오프셋·기존 값 오프셋·`CONVERT_TZ` 범위) 등록

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 16 | 8 | 25 | NOT CONVERGED (계획) |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 4: F-001~F-004) | 단계 A CONVERGED · 그룹 Open 21 |
| 2 | 0 | 0 | 0 | 0 | 0 (Fixed 9: F-005~F-013) | 단계 B CONVERGED · 그룹 Open 12 |
| 3 | 0 | 0 | 0 | 1 | 0 (Fixed 2: F-014·F-016, F-026 Accepted) | 단계 C: F-015 CI 판정 대기 · 그룹 Open 10 |
| 4 | 0 | 0 | 0 | 0 | 0 (Fixed 1: F-017) | 단계 D CONVERGED · F-015 CI 판정 대기 · 그룹 Open 9 |
