# Run Log — log-redaction-fixes (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-13 (base SHA: `b39478c`) · 계획 · 재현
- **트리거:** 사용자 요청 REQ-001
- **재현:**
  - 비밀값: `build_dictconfig()` 를 적용하고 `logging.getLogger("app.core.bootstrap").exception(..., stack_info=True)` 로
    `ValueError("connect mysql+asyncmy://u:secret42@h/db password=secret42")` → `RuntimeError("Authorization: Bearer …") from e` 를 남기면
    출력에 `secret42` 와 Bearer 토큰이 그대로 있었다. 저장소에는 로그 메시지용 마스킹 클래스가 없었다.
  - 405: `TestClient(create_app()).delete("/health")` → 405, `Allow` 헤더 없음, 본문 `{"error_code":"HTTP_405","message":"Method Not Allowed","detail":null}`.
- **핸들러 경로:** 앱은 root 에만 핸들러(console, staging/production+`LOG_FILE_ENABLED` 면 file·error_file). `setup_uvicorn_logging()` 은 `uvicorn.*` 에
  자기 핸들러(propagate=False)·`TzFormatter`. `uvicorn main:app` CLI 는 uvicorn 의 `LOGGING_CONFIG`·`DefaultFormatter`. Celery 워커는 root 핸들러를 교체한다.
  sqlalchemy 등 외부 로거는 root 로 전파(`SqlNoiseFilter` 가 WARNING 미만 차단). DEBUG 500 응답에 `str(exc)` 를 싣는 경로는 없다(`bootstrap.py` 일반 핸들러).
- **신규 finding:** CRIT 0 · HIGH 1 · MED 2 · LOW 0 → ledger F-001 ~ F-003
- **수렴 판정:** `NOT CONVERGED` (Open Fix 3)

### Round 1 — 2026-10-13 · 가리기 · 예외 헤더 · Redis 버전 · 엔드포인트 보호 조사
- **트리거:** REQ-001 — ADR-001~ADR-004
- **변경:**
  - `app/utils/logs/redaction.py`(신규) — `SecretRedactor`(규칙 4개), `redactor`, `install_record_redaction()`. `app/utils/logs/setup.py` — `configure_logging()` 이 설치.
  - `app/core/bootstrap.py` — `StarletteHTTPException` 핸들러 `headers=exc.headers`.
  - `app/core/redis.py` — `REDIS_MIN_VERSION=(7, 0)`(명령→버전 표 주석), `UnsupportedRedisVersion`, `ensure_redis_version()`. `app/core/resources.py` — ping 직후 호출.
  - 문서: README(주요 특징·기술 스택·1단계·환경 표·자주 막히는 지점·배포 체크리스트), `.env.example`, ARCHITECTURE(§1.3·§3 흐름도·§3.4·§3.5·§5·§11.1 #6·§12),
    DEVELOPMENT §4, 서버 수명주기 안내서(§6·§10·§12), compose·CI 주석, `rate_limit`·`refresh_store` docstring.
  - 테스트 가짜 Redis(`tests/core/test_bootstrap.py`)에 `info()` — 버전 확인이 생겨 필요해졌다.
- **새 테스트와 fail-on-revert** (대상 파일을 `main` 판으로 바꿔 실행 → 저장소 밖 복사본으로 복원):
  - `tests/utils/test_log_redaction.py` (20) — `setup.py` 되돌림: `test_app_handlers_redact_traceback_message_and_stack`·`test_third_party_logger_through_root_is_redacted`·
    `test_uvicorn_direct_run_handlers_are_redacted`·`test_uvicorn_cli_handlers_we_do_not_own_are_redacted`·`test_uvicorn_access_args_stay_a_tuple`·
    `test_celery_formatter_output_is_redacted` **6 실패**. 규칙 단위 테스트(`test_redaction_rules` 10건·멱등·템플릿/인자 분할·예외 인자·설치 1회)는 클래스를 직접 시험하므로 되돌림과 무관하게 통과한다.
  - `tests/core/test_exception_headers.py` (4) — `bootstrap.py` 되돌림: `test_405_carries_allow_with_the_real_methods`·`test_http_exception_headers_reach_the_response[401]`·`[418]` **3 실패**(404 봉투 테스트는 기존 동작 고정이라 통과).
  - `tests/core/test_redis_version.py` (13) — `resources.py` 되돌림: `test_lifespan_refuses_an_old_redis` 실패. `REDIS_MIN_VERSION` 을 (6, 2) 로 바꾸면
    `test_older_server_stops_startup[6.2.14]`·`test_lifespan_refuses_an_old_redis`·`test_min_version_covers_every_command_the_code_uses` **3 실패**.
- **엔드포인트 보호 현황 조사**(읽기 전용, 코드 무변경 — 2026-10-13, `create_app()` 의 `app.routes` 를 `_IncludedRouter.original_router` 까지 내려가며 순회해 각 라우트의 의존성 트리에서 인증 provider 를 뽑았다):
  - 거는 방식: 전역 인증 미들웨어·기본 거부는 **없다**. core `app/core/security/dependencies.py` 의 provider 를 경로별로 단다 —
    `get_current_principal`(:81, `oauth2_scheme` `auto_error=False` :36 → 토큰 없음 401)·`require_superuser`(:102)·별칭 `CurrentPrincipal`(:112)·`SuperuserPrincipal`(:114),
    작성자 판정은 서비스가 주입받은 `OwnershipPolicy`(`get_ownership_policy` :68). 라우터 단위 `dependencies=[Depends(require_superuser)]` 는
    `app/features/home/api/routers/v1/home.py:29-30`·`app/features/reports/api/routers/v1/sales_reports.py:28-29`, 라우트 단위 `_ADMIN_ONLY` 는
    `app/features/catalog/api/routers/v1/products.py:43`·`app/features/user/api/routers/v1/user.py:45`. `install_routers`(`app/core/apps/wiring.py:72`)는 prefix 만 주고 의존성을 더하지 않는다.
  - 라우트 42개(메서드 기준, `/admin` 마운트 포함): 공개 — `GET /health`·`GET /ready`·`GET /docs`·`GET|HEAD /openapi.json`(둘 다 DEBUG 때만)·`POST /api/v1/auth/{register,login,refresh,logout}`·
    blog·sns·reply·catalog 의 목록·단건 GET(8). 로그인 — `GET /api/v1/auth/me`, blog·sns·reply `POST`(3). 작성자 또는 슈퍼유저 — blog·sns·reply `PATCH`·`DELETE`(6).
    본인 또는 슈퍼유저 — user 단건 `GET`·`PATCH`. 슈퍼유저 — user 목록·생성·삭제, catalog `POST`·`PATCH`·`DELETE`, `GET /api/v1/reports/daily-sales`, home 접속 로그 GET 5종.
    `/admin` 마운트는 SQLAdmin 슈퍼유저 세션 로그인(admin-login ADR-001).
  - 인증 누락을 막는 것: 기본값은 **공개**(막지 않음). 스캐폴드 `scripts/new_app.py:132-143` 이 만드는 `GET /ping` 은 인증 없음. 막는 장치는 테스트 하나 —
    `tests/test_authorization_policy.py::test_policy_table_covers_every_operation`(:121)이 `main.app` 의 OpenAPI 오퍼레이션 집합과 정책 표 `POLICY` 를 비교해
    `INSTALLED_APPS` 에 들어간 새 라우트가 표에 없으면 실패하고, `test_policy_table_matches_openapi_security`(:126)가 표의 등급과 OpenAPI `security` 를 교차 확인하며,
    `test_protected_operation_without_token_is_401`(:161)·`test_admin_operation_rejects_a_normal_user`(:170)가 실제 요청으로 확인한다. 게이트(`review_gate` pytest 단계)·CI 가 이 테스트를 돌린다.
    한계: 새 라우트를 표에 `public` 으로 올리면 통과한다(쓰기 라우트가 공개인지 따로 검사하지 않는다), `include_in_schema=False` 라우트는 OpenAPI 에 없어 표 대조를 빠져나간다.
    안내는 DEVELOPMENT §4.5(:440 "새 오퍼레이션은 정책 표에 등급을 올린다").
  - 인증 없이 열린 쓰기 라우트: `POST /api/v1/auth/register`(가입 레이트 리밋 `register_rate_limit`, `auth.py:55`)·`login`(로그인 레이트 리밋 `login_rate_limit`, `auth.py:80`)·
    `refresh`·`logout`(refresh 토큰을 본문으로 받아 판정). 넷 다 의도된 공개다 — README 「권한 표」(공개 행), `tests/test_authorization_policy.py` POLICY `public`, service-hardening ADR-015·ADR-016.
    그 밖의 쓰기 라우트는 모두 로그인 이상이다.
- **수렴 판정:** F-001~F-003 Fixed

### Round 2 — 2026-10-13 · 커버리지 하한 기본 0
- **트리거:** REQ-002(사용자 추가 요청) — ADR-005
- **변경:** `pyproject.toml` `fail_under = 0`(주석: 기본 0 = 하한 없음, 이 값 하나만 올린다), `tests/scripts/test_gates.py::test_coverage_threshold_has_one_source`
  (pyproject 에 한 번·값 0·CI 와 `scripts/review_gate.py` 에 `--cov-fail-under` 없음·CI `--cov=app --cov-report=term-missing`), CI 주석, 게이트 단계 설명,
  DEVELOPMENT §6.1(올리는 법)·ARCHITECTURE NFR-08·README 테스트 절, orm-raw-repository ADR-038 ② 값 대체 표시.
- **fail-on-revert:** `pyproject.toml` 을 main(85)으로 되돌리면 `test_coverage_threshold_has_one_source` 실패.
- **검사:**
  - `ruff check`·`ruff format --check` 통과, mypy 1.20.2(순수 Python 빌드) 218 파일 이상 없음.
  - `pytest -m "not mysql and not browser"`: 저장소 1089 passed · 34 deselected · skip/xfail 0. `.env` 없는 저장소 밖 사본(작업 트리 내보내기, `uv sync --locked`)에서도
    1089 passed · 34 deselected · skip 0 · coverage 96%.
  - `ENV=test uv run python -m scripts.review_gate --fast` 7단계 통과(run-log 보고 시점 기준, 아래 최종 판정).
  - `mysql`·`browser` 마커는 `--collect-only` 로 수집만 확인(새 마커 테스트 없음). alembic 변경 없음.
  - 문서 정합 테스트가 문서의 백틱 대문자 토큰을 환경변수로 보므로 `GETDEL`·`REDIS_MIN_VERSION` 은 백틱 없이 또는 `redis.REDIS_MIN_VERSION` 으로 적었다.
- **수렴 판정:** `CONVERGED` — Open Fix 0, 수용 항목은 residual-risk R-001~R-006.
