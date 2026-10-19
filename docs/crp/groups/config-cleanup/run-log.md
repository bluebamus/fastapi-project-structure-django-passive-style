# Run Log — config-cleanup (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `6aae442`) · 참조 조사
- **트리거:** 사용자 요청 REQ-001
- **조사:** `git grep -i -E "smtp|session_expire|upload"`(uv.lock 제외) — 참조는 `config.py`·`.env.example`·`README.md`(0단계 표·자주 막히는 지점)·
  `docs/guides/ARCHITECTURE.md`(§3.2 표 2곳·검증 표 2곳·§11.3)·`admin-auth-guide.html`(만료 표)·`server-lifecycle-guide.html`(클래스 표·검증 문단 2곳·부록)·
  `tests/core/test_deployment_safety.py`·`tests/core/test_security_hardening.py`·과거 CRP 그룹 문서(이력, 고치지 않음). app·scripts·migrations·CI·compose 에는 없었다.
- **소비처 확인:** AST 로 운영 코드의 속성 접근을 모으면 세 묶음 필드는 `SMTPSettings` 자체 validator(`self.SMTP_TLS`·`self.SMTP_SSL`)와
  배포 안전 검사(`smtp_settings.SMTP_PASSWORD`) 말고는 읽히지 않았다. 그 밖의 미사용 필드는 `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`.
- **python-multipart:** `OAuth2PasswordRequestForm`(API 로그인)·`admin_auth.py` 의 `request.form()`(관리 로그인·CSRF)·sqladmin 폼이 쓴다 → 유지(ADR-004).
- **신규 finding:** LOW 3 → ledger F-001~F-003
- **수렴 판정:** `NOT CONVERGED` (Open Fix 2)

### Round 1 — 2026-10-19 · 삭제 · 만료 정본 · 계약 테스트
- **변경:** `config.py`(클래스 2개·팩토리 2개·전역 인스턴스 2개·`SESSION_EXPIRE_SECONDS` 삭제, 배포 안전 검사의 SMTP 항목 삭제, docstring), `.env.example`,
  `tests/core/test_deployment_safety.py`(비밀번호 키 2종으로, `test_empty_optional_passwords_are_allowed` → `test_empty_redis_password_is_allowed`),
  `tests/core/test_security_hardening.py`, `tests/core/test_settings_contract.py`(3절), README(만료 표·업그레이드 노트·0단계 표·자주 막히는 지점),
  ARCHITECTURE(§3.2·§7·§11.1 #13·§11.3·§12), admin-auth-guide(만료 표·운영 표), server-lifecycle-guide(클래스 표·검증 문단·부록).
- **새 테스트와 fail-on-revert** (`config.py` 를 저장소 밖 임시 경로에 복사해 두고 바꿔 실행 → 복사본으로 복원, `cmp` 로 확인):

  | 테스트 | main 의 `config.py` | `SESSION_EXPIRE_SECONDS` 한 필드만 되살림 |
  |---|---|---|
  | `test_every_setting_field_is_read_by_source_code` | 실패 | 실패 |
  | `test_removed_keys_left_in_environment_are_ignored[SessionSettings]` | 실패 | 실패 |
  | `test_removed_keys_left_in_environment_are_ignored[SMTPSettings]`·`[UploadSettings]` | 실패(클래스가 있어 수집됨) | — |
  | (기존) `test_every_config_field_is_documented_in_env_example` | 실패 | 실패 |

- **정리(ponytail):** 계약 테스트의 검사 파일 목록을 기존 `_python_sources()` 재사용으로 줄이고, 전역 인스턴스 부재만 보던 중복 테스트를 지웠다
  (같은 되돌림을 읽힘 계약이 이미 잡는다). 정리 뒤 fail-on-revert 를 다시 돌려 위 표와 같은 결과를 확인했다.
- **검사:** `.env` 없는 저장소 밖 클론에서 `pytest -m "not mysql and not browser"` 1230 passed · 36 deselected · skip/xfail/xpass 0.
  `-m "mysql or browser" --collect-only` 36 수집(실행 안 함). `ruff check`·`ruff format --check`(383 파일) 클린. mypy 1.20.2(순수 Python 빌드) 222 파일 문제 없음.
  `ENV=test uv run python -m scripts.review_gate --fast`(클론) 7단계 전체 통과(pip-audit 포함). 마이그레이션 변경 없음.
- **신규 finding:** 0
- **수렴 판정:** `CONVERGED` (Open Fix 0, F-003 은 R-001 로 수용)

### Round 2 — 2026-10-19 (base SHA: `80d56a9`, 브랜치 `chore/config-cleanup-2`) · API_VERSION 삭제 · 로그 설정 연결
- **트리거:** 사용자 결정 REQ-002 ("API_VERSION 삭제, 로그 설정은 실제로 연결")
- **현재 흐름 조사(변경 전):**
  - 포맷 문자열은 `app/utils/logs/config.py` 의 `LOG_FORMAT` 상수 하나에 하드코딩. `build_dictconfig()` 의 `app` 포매터(console·file·error_file 공용)와
    `setup.py` 의 `setup_uvicorn_logging()` `default` 포매터가 이것을 쓰고, uvicorn `access` 포매터는 함수 안의 고정 문자열.
  - 날짜 형식은 `TzFormatter.formatTime` 안의 `"%Y-%m-%d %H:%M:%S"` 하드코딩(+ development 면 `.밀리초`). 어느 dictConfig 도 `datefmt` 를 넘기지 않았다.
  - 콘솔 핸들러는 `build_dictconfig()` 가 항상 만들고, `setup_uvicorn_logging()` 도 `default`·`access` StreamHandler 를 항상 만들었다.
  - 앱 경로: 첫 `get_logger()` → `configure_logging()` → `dictConfig(build_dictconfig())`(root 에만 핸들러). `python main.py` 는 `uvicorn.run(log_config=setup_uvicorn_logging())`.
  - uvicorn CLI(`uvicorn main:app`·`fastapi dev`)는 uvicorn 자체 `LOGGING_CONFIG` — 앱은 포매터를 소유하지 않는다(가리기만 LogRecord factory 로 적용).
  - Celery 워커: `setup_logging` 수신자가 없어 `worker_hijack_root_logger` 로 root 핸들러를 Celery 포매터로 갈아끼웠다 — 앱 구성(콘솔·파일·포맷)이 워커에서 무시.
  - `LogSettings` 의 기본값 `[{asctime}] {levelname:8} [{name}:...]` 은 실제 출력 형식과도 달랐다(문서상 기본값과 실제가 어긋남).
- **변경:**
  - `config.py`: `ApiSettings`·`get_api_settings`·`api_settings` 삭제. `DEFAULT_LOG_FORMAT`(기존 하드코딩 형식)을 두 포맷 필드의 기본값으로,
    포맷 field_validator(샘플 레코드 렌더, ADR-010)·날짜 형식 빈 값 거부, docstring·필드 설명.
  - `app/utils/logs/config.py`: `LOG_FORMAT = DEFAULT_LOG_FORMAT`, `console_enabled()`·`formatter_spec()`, console 조건부, 파일 핸들러는 `file` 포매터(`LOG_FILE_FORMAT`),
    출력 0개면 `NullHandler`.
  - `app/utils/logs/setup.py`: 모두 꺼짐 stderr 경고 한 줄, `setup_uvicorn_logging()` 이 `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`·`console_enabled()` 를 따름(끄면 propagate).
  - `app/utils/logs/formatters.py`: `datefmt` 가 있어도 development 밀리초 유지(ADR-011).
  - `app/celery/app.py`: `setup_logging` 수신자 `use_app_logging`(ADR-009).
  - `.env.example`(API 절 삭제, 로그 키 주석·예시), ARCHITECTURE(§3.2·§5·§11.3·§12), DEVELOPMENT §2.7, feature-development-guide, server-lifecycle-guide(클래스 표·로깅 문단·부록).
  - 테스트: `tests/utils/test_log_settings.py`(신규), `tests/utils/conftest.py`(`restore_logging` fixture 를 `test_log_redaction.py` 에서 옮김),
    `test_log_redaction.py`(앱 핸들러 가리기 테스트를 사용자 포맷으로도 실행), `test_settings_contract.py`(`UNREAD_ALLOWED` 삭제, `REMOVED_KEYS` 에 `API_VERSION`).
- **TDD:** 새 테스트를 먼저 쓰고 구현 전 실행 — 17건 실패(모두 기능 부재로: 기본값 불일치·포맷 미적용·검증 없음·콘솔 스위치 무시·Celery 수신자 없음·계약 테스트 미사용 5건·`ApiSettings` 잔존).
- **fail-on-revert** (대상 파일을 저장소 밖 임시 경로에 복사 → 수정 전 내용으로 바꿔 실행 → 복사본으로 복원, `cmp` 로 확인):

  | 되돌린 것 | 실패한 테스트 |
  |---|---|
  | `app/utils/logs/{config,setup,formatters}.py`·`app/celery/app.py` 를 main 으로(설정은 새 것) | `test_console_format_and_date_format_shape_app_output`·`test_file_format_is_written_to_file`·`test_uvicorn_direct_run_follows_console_format_and_date`·`test_celery_worker_uses_app_logging`·`test_console_disabled_removes_only_console_handlers`·`test_all_outputs_off_warns_once_on_stderr`·`test_app_handlers_redact_traceback_message_and_stack[user-format]`·`test_every_setting_field_is_read_by_source_code` (8) |
  | `formatters.py` 만 main 으로(날짜 형식이 있으면 밀리초 사라짐) | `test_default_output_line_is_unchanged[development]` |
  | `NullHandler` 분기만 끔 | `test_all_outputs_off_warns_once_on_stderr`(lastResort 가 stderr 로 찍음) |
  | 포맷·날짜 validator 본문만 끔 | `test_invalid_format_is_rejected_at_load` 6건·`test_empty_date_format_is_rejected` |
  | Celery `--loglevel` 적용만 끔 | `test_celery_worker_uses_app_logging` |
  | (TDD 단계) `config.py` 기본값·`ApiSettings` 가 main 그대로 | `test_format_defaults_equal_previous_hardcoded_values`·`test_removed_keys_left_in_environment_are_ignored[ApiSettings]` |

- **검사:** `.env` 없는 저장소 밖 클론에서 `pytest -m "not mysql and not browser"` 1249 passed · 36 deselected · skip/xfail/xpass 0(경고 1 — starlette testclient 의 httpx 폐기 예고, 기존).
  작업 사본도 1249 passed · 36 deselected. `-m "mysql or browser" --collect-only` 36 수집(실행 안 함). `ruff check`·`ruff format --check`(385 파일) 클린.
  mypy 1.20.2(순수 Python 빌드) 222 파일 문제 없음. review_gate 단계 중 bandit(MEDIUM 이상 0건, 257 파일)·OpenAPI fail-on-revert(20건 감지·문제 0) 개별 실행 통과,
  pip-audit(네트워크)·mysql·browser 단계는 실행 안 함. 마이그레이션 변경 없음.
- **신규 finding:** LOW 2 → ledger F-004·F-005(Fixed). 수용 R-004(ADR-012).
- **수렴 판정:** `CONVERGED` (Open Fix 0, R-001 해소)

### Round 2b — 2026-10-19 · 감독자 추가 확인: `python main.py` 의 uvicorn access 줄
- **재현:** `configure_logging()` → `dictConfig(setup_uvicorn_logging())` → `uvicorn.access` 에 uvicorn 과 같은 5-튜플 레코드
  (`'%s - "%s %s HTTP/%s" %d'`)를 흘림 → `--- Logging error --- ValueError: Formatting field not found in record: 'client_addr'`, 출력 줄 없음.
  원인: `{client_addr}`·`{request_line}`·`{status_code}` 는 uvicorn `AccessFormatter.formatMessage` 가 레코드 복사본에 넣는 필드인데 우리는 `TzFormatter` 를 썼다.
  main(`80d56a9`)의 `setup.py` 도 같은 fmt — 이번 브랜치가 만든 결함이 아니다. 기존 `test_uvicorn_config_isolates_three_loggers` 는 fmt 에 `request_line` 문자열이 있는지만 봐 결함을 고정했다.
- **TDD:** `test_uvicorn_direct_run_access_line_renders` 를 먼저 써 실패 확인(stderr 에 logging 오류) → access fmt 를 `[{asctime} {tzname}] {levelname:5} [app=uvicorn] {message}` 로 바꿔 통과.
  줄: `[YYYY/MM/DD HH:MM:SS UTC] INFO  [app=uvicorn] 1.2.3.4:5 - "GET /x?password=*** HTTP/1.1" 200` — 마스킹·UTC·`LOG_DATE_FORMAT` 유지. 상태 문구(`OK`)는 없다.
- **fail-on-revert:** `setup.py` 를 직전 커밋으로 되돌리면 `test_uvicorn_direct_run_access_line_renders`·`test_uvicorn_config_isolates_three_loggers` 2건 실패 → 복원(`cmp` 확인).
- **신규 finding:** MED 1 → ledger F-006(Fixed)

### Round 3 — 2026-10-19 (base SHA: `2d478ea`, 브랜치 `fix/redaction-keeps-args`) · 가리기 뒤 접속 줄 소실
- **재현(실제 레코드, 두 경로 × 7 경로값):** `configure_logging()` 뒤 uvicorn `LOGGING_CONFIG`(CLI)와 `setup_uvicorn_logging()`(`python main.py`)에
  `'%s - "%s %s HTTP/%s" %d'` 5-튜플을 흘렸다. 비밀값 없음·`?password=secret42&page=2`·`?token=abc.def`·`?access_token=<JWT>` 는 두 경로 모두 줄이 남고 값이 가려졌다
  (인자별 가리기가 args 모양을 지킨다 — 이 저장소는 LogRecord factory 방식). `?password=`·`?token=`(빈 값)·`/bearer` 는 CLI 에서 `--- Logging error --- Arguments: None` 으로
  **줄이 사라졌고**, `python main.py` 는 오류 없이 `"GET /x?password= ***"` 처럼 HTTP 버전을 가렸다.
- **원인:** `SecretRedactor._redact_message` 는 인자별로 가린 결과가 여전히 규칙에 걸리면 렌더 문자열로 접는다(`args=None`). 위 세 경우는 키가 경로 인자 끝에 있고 규칙이 템플릿의 ` HTTP/` + 버전 인자를 "값" 으로 잡는다.
- **TDD:** `test_uvicorn_access_line_survives_redaction`(2 경로 × 6 경우)를 먼저 써 6건 실패 확인 → 접기 전에 문자열 인자 하나씩 `***` 로 바꿔 보고 깨끗해지는 첫 모양으로 고정. 
  인자 하나로 안 되면(진짜로 여러 곳에 걸친 비밀값) 예전처럼 접는다. `password=%s` 처럼 키가 템플릿·값이 인자인 기존 경우는 그 인자가 가려진다(기존 테스트 통과).
- **fail-on-revert:** `redaction.py` 를 main 으로 되돌리면 새 테스트 6건 실패 → 복원(`cmp` 확인).
- **검사:** `.env` 없는 저장소 밖 클론 결과는 아래 Round 3 검사 줄. 작업 사본 1262 passed · 36 deselected. mypy 222 파일·ruff·bandit(0건) 통과.
- **신규 finding:** MED 1 → ledger F-007(Fixed)
