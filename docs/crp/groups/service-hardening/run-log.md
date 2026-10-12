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

### Round 5 — 2026-10-12 (base SHA: `5dbcdc3`) · 단계 E
- **트리거:** REQ-001 단계 E (제안 8, Redis 필수) — ADR-011·ADR-012, 새 ADR-028
- **검수 범위:** F-018 · F-019 + F-015 CI 판정 반영
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■ (단계 E 한정)
- **변경:**
  - E1: `app/core/redis.py` — `get_redis(request) -> Redis`(lifespan 이 둔 `app.state.redis`, 없으면 `ServiceUnavailableException` 503),
    `ping_redis(client, timeout)`. `app/core/bootstrap.py` `/ready` 가 `Depends(get_redis)` 로 client 를 받아 `ping_writer_db()`·`ping_redis(…, 2초)` 를
    `asyncio.gather(return_exceptions=True)` 로 동시에 보내고, 실패마다 `[Readiness] <DB|Redis> 준비 확인 실패: <예외 타입>` WARNING 후 원문 없는 503.
    OpenAPI 설명·503 응답 설명·`tags_metadata` Health 표 갱신. `compose.test.yaml` 의 `redis-test` 는 이미 있어 바꾸지 않았다.
  - E2: `AppConfig.tasks_module = "tasks"` + `tasks_module_path()`(`importlib.util.find_spec`, import 안 함 — 순환 import 방지, ADR-028 ②),
    `Apps.task_modules()`(설치 순서, `check_apps_ready`). `app/celery/app.py` `discover_task_modules(installed_apps)` 가 새 `Apps()` 를
    `run_ready=False` 로 채워 include 를 만든다. 태스크를 `app/features/home/tasks.py` 로 옮기고(이름 `home.aggregate_access_stats` 유지)
    본문은 `background_session()` + home provider `build_user_access_log_service(session)`. HTTP provider `get_access_log_service` 도 같은 함수를 부른다.
    `app/celery/tasks.py` 삭제. `populate(run_ready=False)` docstring 에 워커 용도 추가.
  - 테스트 조정(이유 기록): `tests/core/test_runtime_lifecycle.py` 의 `/ready` 2건은 lifespan 없이 앱을 만들어 `app.state.redis` 가 없다 —
    가짜 정상 Redis 를 넣었다(DB 실패 테스트가 Redis 부재 503 으로 헛통과하지 않게). `tests/core/test_celery_app.py` 의 `"app.celery.tasks" in include`
    단언은 반대(없어야 한다)로 바꿨다. `app/features/home/tests/test_home_tasks.py` 는 새 module 경로로.
  - 문서: README(기술 스택 Redis·트리·`/ready` 표 2곳), ARCHITECTURE §2.2(`tasks_module` 행·Tasks 실패 행)·§2.3·§2.7(태스크도 빠진다)·§3.4(`get_redis`)·§3.5(`/ready`)·§9(Celery),
    DEVELOPMENT §2.6(`tasks.py` 선택 행·이름 표)·§3(태스크·Redis 주입), `server-lifecycle-guide.html`·`feature-development-guide.html`(코드 근거 링크 포함),
    `scripts/new_app.py` docstring(선택 `tasks.py` 는 만들지 않는다).
- **새 테스트와 fail-on-revert(대상 파일을 작업 폴더 밖에 복사해 두고 수정 전 내용 또는 변이를 넣어 실행 후 복원):**
  - `tests/core/test_redis_readiness.py` 9건 — `bootstrap.py` 를 main 으로 → 200(Redis ping 0회)·Redis 실패 503·Redis timeout 503·둘 다 실패 로그·client 없음 503
    5건 실패. DB 실패 503 은 기존 동작 유지라 통과(의도). `get_redis` 3건은 새 module.
  - `tests/core/apps/test_task_modules.py` 8건 + fixture `tests/core/apps/_fixtures/alpha/tasks.py`(import 되면 이벤트 기록) — `config.py`·`registry.py` 를
    main 으로 → 8건 실패(같은 판에 `test_celery_app.py` 5건도 실패). `find_spec` 을 `import_optional` 로 바꾸는 변이 → 순환 위험 단언 2건 실패.
  - `tests/core/test_celery_app.py` — `app/celery/app.py`·`tasks.py` 를 main 으로 → include 2건 실패, `test_celery_does_not_depend_on_features` 실패.
    `test_including_the_task_modules_registers_the_tasks` 는 옛 중앙 태스크도 등록하므로 통과(이름 유지 확인용).
  - `app/features/home/tests/test_home_tasks.py::test_task_builds_the_service_through_the_provider` — 태스크가 `UserAccessLogService(session)` 을
    직접 만드는 변이에서 실패. provider 재사용 2건(HTTP provider·조립 결과)
- **검사:** ruff check 통과 · ruff format --check 342 파일 · mypy 208 파일 이슈 0(순수 Python 빌드 1.20.2) ·
  `pytest -m "not mysql and not browser"` **829 passed · 31 deselected · skip 0** · `--cov=app` **95.41%** ·
  `-m "mysql or browser" --collect-only` 31건 · bandit MEDIUM 이상 0(241 파일) · OpenAPI revert check 20/20 감지 ·
  `scripts.review_gate --fast`: ruff·bandit·pip-audit·pytest·OpenAPI 통과, mypy 는 로컬 `.pyd` 차단(위 순수 빌드로 대체)
- **F-015 판정:** CI run 38210910082 의 mysql job **24 passed**(ORM 스모크 5건·시각 정책 포함, skip·xfail 0) → Fixed
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 E `CONVERGED` (F-018·F-019 Fixed, F-015 Fixed). 그룹 전체는 `NOT CONVERGED` (Open Fix 6: F-020~F-025)
- **잔여 위험 변화:** R-011(태스크 module 내부 import 오류는 워커 기동 시 드러남) 등록

### Round 6 — 2026-10-12 (base SHA: `f40333f`) · 단계 F1
- **트리거:** REQ-001 단계 F1 (제안 9 前半, 인증 코어) — ADR-013~ADR-016, 새 ADR-029
- **검수 범위:** F-020 · F-021
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■ (단계 F1 한정)
- **변경:**
  - 의존성: `uv add "pwdlib[argon2]"`(pwdlib 0.3.1·argon2-cffi 25.1.0), `uv add --dev fakeredis`(2.39.0). `bcrypt` 는 기존 해시 검증에 남긴다.
  - core security(`app/core/security/`): `PasswordHasher`(pwdlib `PasswordHash((Argon2Hasher(),))`, `verify_and_update(password, stored)` — `$2*` 는 72바이트 절단 bcrypt 검증 후
    Argon2 새 해시, `None` 은 Argon2 더미 검증 후 실패, 알 수 없는 형식은 실패), `TokenService`(PyJWT, claims `sub·type·iat·nbf·exp·jti(uuid4 hex)·iss·aud` + access `username` /
    refresh `fam`, decode `algorithms=[설정]`·`audience`·`issuer`·`leeway`·`options.require`, `type` 과 `fam` 문자열 검사, 실패는 `InvalidTokenException` 하나, 발급은 `IssuedToken(token, jti, expires_in)`),
    `RefreshTokenStore(redis, ttl_seconds)`(`register` MULTI SET EX + SADD + EXPIRE, `consume` GETDEL, `revoke_family`, `is_family_revoked`, `revoke_user`),
    `RateLimiter(redis)`(`hit` MULTI INCR + EXPIRE NX + TTL → `RateLimitResult(allowed, retry_after)`, `reset`).
  - `app/core/exception.py`: `InvalidTokenException`(auth 에서 이동, 코드·메시지 유지), `TooManyRequestsException`(429, `Retry-After`), `AppException.headers` — `bootstrap.py` 핸들러가 싣는다.
  - `config.py` `JWTSettings`: `JWT_ISSUER`·`JWT_AUDIENCE`·`JWT_LEEWAY_SECONDS`, `JWT_ALGORITHM: Literal["HS256","HS384","HS512"]`, `ACCESS_TOKEN_EXPIRE_MINUTES` 기본 15, 레이트 리밋 정수 5종(ADR-029 ③).
  - auth: `AuthService(session, password_hasher, token_service, refresh_store)` — `register`·`authenticate`(재해시 flush)·`issue_tokens`(새 family)·`rotate`·`logout`.
    provider·레이트 리밋 의존성·`get_current_user`(TokenService + 읽기 전용 `UserRepository`)는 `auth_dependencies.py`. 라우터: register(`dependencies=[Depends(register_rate_limit)]`),
    login(`Depends(login_rate_limit)` → 커밋 → ip+username 초기화), refresh(회전), logout(204), me. `TokenResponse` 에 `expires_in`.
  - 제거: `app/utils/authenticator/`(소비처 0), `tests/utils/test_auth.py`(→ `tests/core/security/`).
  - 테스트 조정(이유 기록): `tests/test_route_inventory.py` 에 `/api/v1/auth/logout` 추가(공개 API 추가, 기존 경로 불변). `tests/test_read_path_no_commit.py` 의 "DB 변경 없음" 목록에서
    login 을 빼고(재해시 커밋) logout 을 넣었다(Redis 만 바꾼다). `tests/test_validate_before_commit.py`·`app/features/auth/tests/test_transaction_boundary.py` 의 클라이언트에
    fakeredis `get_redis` override 를 더했다(register·login 이 레이트 리밋으로 Redis 를 쓴다). 검사 규칙은 약화하지 않았다.
  - 문서: README(특징·기술 스택·구조·API 표 23 경로/38 오퍼레이션·curl·인증 흐름·환경 변수), ARCHITECTURE §1.3·§7(부품 표·흐름·설정 표), DEVELOPMENT(fakeredis 주입·테스트 표·해시 문구),
    `.env.example`(새 키·HS384/512 키 길이 주의·프록시 홉), `server-lifecycle-guide.html` 설정 부록(JWTSettings 13개), `feature-development-guide.html`(코드 근거 링크·fakeredis), OpenAPI Auth 태그 설명.
- **새 테스트와 fail-on-revert(대상 파일을 작업 폴더 밖에 복사해 두고 변이를 넣어 실행 후 복원 — 28종 모두 감지):**
  - `tests/core/security/test_password_hasher.py` 7건(파라미터 포함 9) — 72바이트 절단 제거·레거시 재해시 미반환·더미 검증 제거 변이에서 실패.
  - `tests/core/security/test_token_service.py` 17건(파라미터 포함 26) — require 옵션 제거(7건 실패)·type 검사 제거·issuer 제거·audience 제거·알고리즘 목록 확장·nbf 미발급·`fam` 문자열 검사 제거 변이에서 실패.
  - `tests/core/security/test_refresh_token_store.py` 6건 — GETDEL→GET·사용자 family 집합 TTL 제거·`revoke_user` 미구현 변이에서 실패.
  - `tests/core/security/test_rate_limiter.py` 7건 — EXPIRE NX 제거(창이 미끄러짐)·EXPIRE 자체 제거 변이에서 실패.
  - `app/features/auth/tests/test_endpoint.py` 27건 — 재사용 시 family 폐기 제거·폐기 family 검사 제거·비활성 사용자 family 폐기 제거·logout family 폐기 제거·재해시 저장 제거·
    login 커밋 제거·성공 시 카운터 초기화 제거·username 소문자 접기 제거·ip 한도 제거·register 레이트 리밋 제거·핸들러 headers 미전달·`/me` 비활성 검사 제거 변이에서 각각 실패.
    처음 돌린 변이 중 4종(비활성 family 폐기·logout family 폐기·aud/iss 동시 제거·`/me` 비활성)이 통과해 테스트를 보강했다 — Redis 의 폐기 표시를 직접 확인하고, aud/iss 를
    따로 변이하고, `/me` 비활성 401 테스트를 더했다. 보강 뒤 다시 돌려 모두 감지.
- **검사:** ruff check 통과 · ruff format --check 349 파일 · mypy 211 파일 이슈 0(순수 Python 빌드 1.20.2) ·
  `pytest -m "not mysql and not browser"` **887 passed · 31 deselected · skip 0** · `--cov=app` **95.95%** ·
  `-m "mysql or browser" --collect-only` 31건 · bandit MEDIUM 이상 0(244 파일) · OpenAPI revert check 20/20 감지 · `uv lock --check` 통과 ·
  `scripts.review_gate --fast`: ruff·mypy·bandit·pip-audit·pytest·OpenAPI 7단계 모두 OK
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 F1 `CONVERGED` (F-020·F-021 Fixed). 그룹 전체는 `NOT CONVERGED` (Open Fix 4: F-022~F-025)
- **잔여 위험 변화:** R-012(bcrypt 잔존 사용자 타이밍)·R-013(프록시 홉 0 의 ip 한도 공유) 등록

### Round 7 — 2026-10-12 (base SHA: `b3c49eb`) · 단계 F2
- **트리거:** REQ-001 단계 F2 (제안 9 後半, 인가·소유권·운영 도구) — ADR-017~ADR-020, 새 ADR-030
- **검수 범위:** F-022 · F-023 · F-024 · F-025
- **GATE 통과:** 0 ■ 1 ■ 2 ■ 3 ■ 4 ■ 5 ■ (단계 F2 · 그룹 전체)
- **변경:**
  - 리비전 `a3c9e8f1b274`(down `e5a7c2d9f310`): `users.is_superuser` Boolean NOT NULL `server_default=false()`, `blog_posts`·`sns_posts`·`replies.author_id` String(36) NULL + `ix_<table>_author_id`.
    모델은 도메인 컬럼 뒤(`author_id` 는 `author` 다음, `is_superuser` 는 `is_active` 다음)에 두어 `sort_order` 배치(id → 도메인 → created_at → updated_at)를 지킨다.
  - core security: `principal.py`(`Principal` frozen dataclass, `OwnershipPolicy.ensure_can_modify`), `dependencies.py`(`oauth2_scheme` auto_error=False, provider 4종, `get_current_principal`,
    `require_superuser`, `CurrentPrincipal`·`SuperuserPrincipal`, 공용 401·403 OpenAPI 응답), `tokens.py`(`issue_access(sub, username, is_superuser)`, access 필수 claim 에 `su`, 추가 claim 값 타입 표 `username:str·su:bool·fam:str`).
  - auth: provider 를 core 에서 가져와 재사용, `get_current_user` = `get_current_principal` + read-only `UserRepository`, `_issue` 가 `user.is_superuser` 를 싣는다, `AuthenticatedUserResponse.is_superuser`.
  - blog·sns·reply: 서비스 생성자 `(session, ownership)`, `create_*(data, principal)`(author_id·author 서버 채움), `update_*/delete_*(id, data?, principal)` 은 존재 확인 뒤 소유권. Create/Update 스키마에서 `author` 제거,
    응답에 `author_id`. 라우터: POST `CurrentPrincipal`, PATCH·DELETE `CurrentPrincipal` + 401·403 문서화.
  - catalog 쓰기·user 목록/생성/삭제: 라우트 `dependencies=[Depends(require_superuser)]`. reports·home: v1 `APIRouter(dependencies=[Depends(require_superuser)], responses=...)`.
  - user: `UserCreate.password`(8~128)·`is_superuser`, `UserUpdate.is_superuser`·`privileged_fields`, `UserService(session, ownership, password_hasher=None, refresh_store=None)` — 단건 조회·수정은
    `ensure_can_modify(user_id, principal)` 를 **존재 확인 전에**, 일반 사용자의 권한 필드 변경 403, `is_active=false`·`is_superuser=false`·삭제 → `revoke_user`. 쓰기 provider 가 core 해시기·refresh 기록을 주입.
  - 접속 로그 미들웨어: `user_id` 를 `_record`(응답 뒤)에서 `request.state` 로 읽는다.
  - `scripts/create_superuser.py`: `--username`·`--email`·`--password-stdin`·`--set-password`, getpass 두 번, `background_session()` + `UserRepository` + core `PasswordHasher`, 생성 또는 승격, 커밋 1회, 종료 코드 0/1/2.
  - 테스트 조정(이유 기록, 검사 규칙 약화 없음): 기존 엔드포인트 클라이언트(blog·sns·reply·user·catalog·reports·트랜잭션 경계·영업일·`test_validate_before_commit`)에 실토큰 관리자 헤더
    (`tests/auth_headers.py`)를 붙였다 — 정책상 이제 인증이 필요하다. user 엔드포인트·생성 페이로드에 비밀번호를 더했다(F-023). `test_update_noop` 은 슈퍼유저 주체와 `OwnershipPolicy` 로 서비스를 만든다.
    `test_patch_schema` 의 "null author 허용" 단언은 `author` 필드 부재 단언으로 바꿨다(작성자는 서버가 채운다). sns 테스트의 본문 author 단언은 서버 채움 값으로. 컬럼 배치 표에 새 컬럼.
    MySQL 왕복 테스트: 한 단계씩 내리기에 인가 리비전 단계를 앞에 더하고, 기존 행이 `is_superuser=0`·`author_id NULL` 로 올라가고 downgrade 가 행을 지우지 않는지 보는 테스트를 더했다(`mysql` 마커, CI 판정).
  - 문서: README(특징·환경 변수 `TRUSTED_PROXY_HOPS`·API 표 인증 열·인증 흐름·권한 표·첫 관리자 만들기·운영 배포 체크리스트 — "/admin 은 여전히 무인증" 갱신 + **프록시 뒤 `TRUSTED_PROXY_HOPS` 미설정 시 IP 레이트 리밋 공유** 항목(R-013 결정 종결)),
    ARCHITECTURE(§1.3 core 표·§6 접속 로그 user_id·§7 부품 표·조립·/me 흐름·§7.1 인가 신설·§11.1 #10·#11·§11.3 알려진 제한 갱신·§12 변경 이력), DEVELOPMENT(§4.1·§4.2 예시 교체·§4.5 인증·인가 붙이기·§6.4),
    HTML 안내서 2편, OpenAPI 태그 설명(Auth·Home·User·Blog·Reply·SNS·Catalog·Sales Reports), `.env.example`(프록시 홉 주석).
- **새 테스트와 fail-on-revert(대상 파일을 작업 폴더 밖에 복사해 두고 변이를 넣어 실행 후 복원 — 34종 모두 감지):**
  - `tests/test_authorization_policy.py` — 정책 표 ↔ OpenAPI 오퍼레이션·security·401/403 문서화, 보호 오퍼레이션 31개 무토큰 401(`WWW-Authenticate: Bearer`), 관리 오퍼레이션 13개 일반 사용자 403,
    공개 GET 무토큰 통과, 나쁜 토큰 6종 401(만료·위조·`su` 누락·`su` 문자열·refresh 를 access 로·쓰레기), 다른 키로 `su=true` 재서명 401, 접속 로그 user_id(인증 요청은 id, 익명은 None).
    감지 변이: `require_superuser` 무력화, reports·home 라우터 가드 제거, catalog 쓰기 가드 전체·생성만 제거, user 관리 가드 제거, `su` 필수 제거, `su` 타입 검사 제거, principal 의 `su` 무시,
    `request.state.user_id` 미기록, 미들웨어의 응답 뒤 읽기 제거, 무토큰 401 우회.
  - `tests/test_ownership.py` — `OwnershipPolicy` 단위 5건 + blog·sns·reply 공통 7건×3(무토큰 401, author·author_id 서버 채움(본문 위조 무시), 소유자 수정·삭제, 타인 403(행 보존), 슈퍼유저 우회, author_id NULL 행은 슈퍼유저만, 없는 행 404).
    감지 변이: 판정 무력화, NULL 소유자 허용, 슈퍼유저 우회 제거, 세 기능 update·delete 의 판정 호출 제거(6종), 본문 author 사용.
  - `app/features/user/tests/test_endpoint.py` — Argon2 저장, 비밀번호 필수, 슈퍼유저 생성, 본인 조회·수정, 타인 403, **없는 ID 도 403**(판정이 존재 확인보다 먼저), 본인 권한 필드 403, 일반 사용자 목록·생성·삭제 403,
    비활성화·강등·삭제 → family 폐기, 일반 수정은 유지. 감지 변이: 본인 판정 제거(조회·수정), 존재 확인을 판정 앞으로, 권한 필드 검사 제거, revoke 호출 제거(비활성화·강등·삭제 각각), 해시 없이 저장.
  - `app/features/auth/tests/test_endpoint.py` +2 — 관리자 API 비활성화 → 재활성화해도 미소비 refresh 401(`revoke_user` 가 막았음을 분리), 로그인 토큰의 `su`·`/me` 의 `is_superuser`·슈퍼유저 토큰으로 관리 API 200. 감지 변이: `su` 를 항상 False 로 발급.
  - `tests/core/security/test_token_service.py` — `su` 왕복, `su` 비bool 4종 거부, 필수 claim 목록에 `su`.
  - `tests/scripts/test_create_superuser.py` 9건 — 생성(Argon2·검증 통과), 승격(비밀번호 유지), `--set-password` 재해시, getpass 불일치 1·일치 0, 짧은 비밀번호·나쁜 이메일·생성 시 이메일 없음 → 1 + 미기록, 사용자명 없음 → 2.
    감지 변이: 승격 안 함, 승격 시 비밀번호 덮어쓰기, 확인 입력 무시.
- **검사:** ruff check 통과 · ruff format --check 356 파일 · mypy 214 파일 이슈 0(순수 Python 빌드 1.20.2) ·
  `pytest -m "not mysql and not browser"` **996 passed · 32 deselected · skip 0** · `--cov=app` **95.99%** · `-m "mysql or browser" --collect-only` 32건 ·
  `alembic heads` 단일(`a3c9e8f1b274`) · SQLite upgrade head → `alembic check` 무드리프트 → downgrade `e5a7c2d9f310` → 재-upgrade → 무드리프트 · 계층 검사 통과(core→features 0, 기능 간 import 는 auth→user 만) ·
  bandit MEDIUM 이상 0(247 파일) · OpenAPI revert check 20/20 감지 · `uv lock --check` 통과 · `scripts.review_gate --fast` 7단계 모두 OK(pip-audit 포함)
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0
- **수렴 판정:** 단계 F2 `CONVERGED` (F-022~F-025 Fixed). **그룹 전체 `CONVERGED`** — Open Fix 0, ledger 의 모든 Fix 가 Fixed(F-001~F-026), Accept 항목은 residual-risk 에 근거와 함께 있다.
- **잔여 위험 변화:** R-013 결정 종결(배포 체크리스트 항목), R-014(강등 후 access 권한 잔존)·R-015(새 컬럼 물리 순서) 등록

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 16 | 8 | 25 | NOT CONVERGED (계획) |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 4: F-001~F-004) | 단계 A CONVERGED · 그룹 Open 21 |
| 2 | 0 | 0 | 0 | 0 | 0 (Fixed 9: F-005~F-013) | 단계 B CONVERGED · 그룹 Open 12 |
| 3 | 0 | 0 | 0 | 1 | 0 (Fixed 2: F-014·F-016, F-026 Accepted) | 단계 C: F-015 CI 판정 대기 · 그룹 Open 10 |
| 4 | 0 | 0 | 0 | 0 | 0 (Fixed 1: F-017) | 단계 D CONVERGED · F-015 CI 판정 대기 · 그룹 Open 9 |
| 5 | 0 | 0 | 0 | 0 | 0 (Fixed 3: F-015·F-018·F-019) | 단계 E CONVERGED · 그룹 Open 6 |
| 6 | 0 | 0 | 0 | 0 | 0 (Fixed 2: F-020·F-021) | 단계 F1 CONVERGED · 그룹 Open 4 |
| 7 | 0 | 0 | 0 | 0 | 0 (Fixed 4: F-022~F-025) | 단계 F2 CONVERGED · **그룹 CONVERGED** (Open 0) |
