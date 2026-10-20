# Run Log — logging-overhaul (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `bb33c22`) · 현재 로그 흐름 조사
- **트리거:** 사용자 요청 REQ-001
- **앱:** 첫 `get_logger()` → `configure_logging()` → `install_record_redaction()`(LogRecord factory) + `dictConfig(build_dictconfig())`.
  root 에 console(`LOG_CONSOLE_ENABLED`)·staging/production 이면 `RotatingFileHandler` 2개(`{date}_app.log`·`{date}_error.log` — 이름의 날짜가
  **기동 날짜로 고정**돼 자정에 넘어가지 않고, 크기 회전 + `LOG_BACKUP_COUNT` 개수). 필터 `sql_noise`·`context`(헤더 = 소스 경로, 저장소 밖은 `ext`).
  `loggers` 키 없음(ADR-019). 레벨은 root 하나(`LOG_LEVEL`)·console(`LOG_CONSOLE_LEVEL`)·file(`LOG_FILE_LEVEL`).
- **`python main.py`:** `uvicorn.run(log_config=setup_uvicorn_logging())` — 별도 dictConfig(uvicorn 로거 3개에 자기 핸들러, `propagate=False`,
  default 포매터는 `LOG_CONSOLE_FORMAT`, access 는 `[app=uvicorn] {message}` 고정). uvicorn 줄은 **파일에 가지 않았다**.
- **`uvicorn main:app`·`fastapi dev`:** uvicorn `LOGGING_CONFIG`(자체 형식, stderr/stdout) — 앱 설정과 무관(config-cleanup ADR-012·R-004).
- **Celery:** `setup_logging` 수신자 → `configure_logging(force=True)`, `--loglevel` → root 레벨, `--logfile` 무시. 워커도 웹과 같은 파일 이름.
- **설정:** `LogSettings` — 포맷 validator 는 샘플 렌더만(필수 필드 검사 없음). 가리기 DSN 규칙은 비밀번호만(계정명 노출), 설정 비밀값 원문 일치 없음.
- **재사용:** `TzFormatter`·`ContextFilter`·`_app_from_path`·`SqlNoiseFilter`·`SecretRedactor`·`install_record_redaction`·`setup_logging` 수신자·
  `REMOVED_KEYS` 계약 — 모두 그대로 두고 빈 곳만 채웠다. 새 파일은 `handlers.py`(회전 핸들러) 하나.
- **수렴 판정:** `NOT CONVERGED` (구현 전)

### Round 1 — 2026-10-19 · 구현 (브랜치 `feat/logging-overhaul`)
- **커밋:** `764f084`(L1~L7) · `c68e246`(F-001) · `28ca635`(F-002) · `a90f8da`(문서) · `0b12028`(F-004) · `235b83a`(format) · 이 run-log.
- **TDD:** 새 테스트를 먼저 쓰고 실패를 확인했다 — `test_log_overhaul.py` 31건 중 28건 실패(나머지 3건은 이미 맞던 규칙: 우리 코드 경로의 헤더
  일부·계정명 없는 Redis URL·URL 아닌 문자열), 설정 테스트 12건 실패. 구현 뒤 의도된 동작 변경으로 옛 테스트 17건을 고쳤다
  (uvicorn 전용 포매터·핸들러 단언, `_app.log` 이름, `RotatingFileHandler`·`backupCount`, `loggers` 없음 단언, DSN `u:***@` 기대값,
  `test_uvicorn_config_isolates_three_loggers` → `test_uvicorn_config_is_the_app_config`, 필수 필드 없는 `test_valid_custom_format_loads` 포맷).
- **fail-on-revert** (소스 7개를 저장소 밖 임시 경로에 복사 → 변이/되돌림 → 테스트 → 복사본 복원, 바이트 비교로 복원 확인):

  | 되돌림·변이 | 결과 |
  |---|---|
  | 소스 전체를 main 으로(`handlers.py` 삭제) | 수집 오류(새 모듈 없음). stub 핸들러로는 새 테스트 28건 실패(TDD 단계에서 확인) |
  | L1 uvicorn 로거 전파 항목 제거 | 4 실패 — `test_uvicorn_lines_use_project_format[cli]`·`test_secret_values_never_reach_any_output[uvicorn-cli]`·`test_dictconfig_has_no_per_app_loggers`·`test_uvicorn_config_is_the_app_config` |
  | L1 `--no-access-log` 유지 제거 | 1 실패 — `test_uvicorn_cli_no_access_log_is_respected` |
  | L1 Celery `--logfile` 무시 | 1 실패 — `test_celery_logfile_is_respected_with_project_format` |
  | L2 로거 이름 표 끔 | 13 실패 — 헤더 표 9건·uvicorn 형식 2건·Celery 2건 등 |
  | L3 필수 필드 검사 끔 | 2 실패 — `test_format_without_required_fields_is_rejected[…]` |
  | L4 `AppLevelFilter` 통과만 | 1 실패 — `test_app_levels_filter_by_header` |
  | L4 모르는 헤더 경고 끔 | 1 실패 — `test_unknown_header_in_app_levels_warns_once` |
  | L5 워커 파일 = 웹 파일 | 5 실패 — `test_files_are_split_by_process[celery]`·`test_web_and_worker_write_their_own_files`·argv 3건 |
  | L6 크기 분할 끔 / 보관 끔 / `<` → `<=` / 분할 파일 패턴 제외 | 각 1 실패 — `test_size_rollover_splits_within_the_day` / `test_retention_deletes_only_older_files[3]`(3종) |
  | L7 DSN 규칙을 main 것으로 | 5 실패 / 비밀번호 첫 `@` 에서 끊기 2 실패 / 계정명 없는 규칙 제거 4 실패 / 계정명만 규칙 제거 1 실패 |
  | L7 `configure_logging()` 이 원문 목록을 넘기지 않음 | 3 실패 — `test_secret_values_never_reach_any_output[app·uvicorn-cli·celery]` |
  | L7 짧은 값도 원문 일치 | 1 실패 — `test_configured_secret_values_are_masked_anywhere` |
  | L7 목록에서 `REDIS_PASSWORD` 빠짐 | 1 실패 — `test_every_secret_setting_is_redacted_from_logs` |
  | F-001 `entry_process()` 가 celery 를 못 알아봄 | 6 실패 |
  | F-002 beat 를 celery 로 | 2 실패 — `test_entry_process[beat]`·`test_celery_receiver_in_beat_uses_beat_files` |

- **실기동 스모크** (저장소 밖 클론, `.env` 없음, 환경 변수만 — `ENV=staging`·`DEBUG=false`·설정 비밀값 5개, MySQL 은 아무것도 듣지 않는 127.0.0.1:3399,
  Redis 는 같은 프로세스의 fakeredis TCP 127.0.0.1:6395 — 예약 포트·로컬 Redis/MySQL 포트 미사용):
  - `uvicorn main:app`(8765)·`python main.py`(8766) 각각 `/health` 2회·`/ready`(DB 실패 경로)·`/nope?password=…` — stdout·`app.log`·`error.log`
    의 `[` 로 시작하는 줄 전부 프로젝트 형식(형식 불일치 0), stderr 0줄, 헤더 `core`·`uvicorn`, 비밀값 원문 0건, 접속 줄 `"GET /nope?password=*** HTTP/1.1" 404`.
  - `celery -A app.celery.app worker --pool=solo -l INFO --without-mingle --without-gossip --without-heartbeat --logfile …`(fakeredis 에 Lua 가 없어
    mingle·gossip 은 끔) — `celery.accumulate` 성공, `home.aggregate_access_stats` 는 DB 없음으로 실패(오류 경로 확인용). `celery.log`·`celery-error.log`·
    `--logfile` 파일 모두 프로젝트 형식·헤더 `celery`(import 중 줄은 `core`), 비밀값 원문 0건. stdout 의 Celery 시작 배너(`[tasks]` 등)는 로그 레코드가 아니라 print 다.
  - 이 과정에서 F-001(워커 import 중 줄이 `app.log`)을 발견해 고쳤다. 스모크 클라이언트(태스크를 보내는 별도 `python -c`)는 웹 기본값이라 자기 `app.log` 에 1줄을 쓴다 — 정상.
  - `uvicorn --reload` 감시 프로세스: stderr 에 uvicorn 기본 형식 3줄(R-002), 자식 프로세스 stdout 16줄은 프로젝트 형식.
- **검사:** `.env` 없는 저장소 밖 클론에서 `pytest -m "not mysql and not browser"` **1319 passed · 36 deselected · skip/xfail/xpass 0**.
  `-m "mysql or browser" --collect-only` 36 수집(실행 안 함). `ruff check` 클린·`ruff format --check` 387 파일. mypy 1.20.2(순수 Python 빌드) 223 파일 문제 없음.
  `ENV=test uv run python -m scripts.review_gate --fast`(클론) 7단계 전체 통과(pip-audit 포함). 마이그레이션·의존성 변경 없음.
- **신규 finding:** F-001·F-002(MED, 스모크·검토에서), F-003(LOW, 문서), F-004(HIGH, 감독자 추가 확인) — 모두 Fixed
- **수렴 판정:** `CONVERGED` (Open Fix 0, 잔여 위험 R-001~R-006 수용)
