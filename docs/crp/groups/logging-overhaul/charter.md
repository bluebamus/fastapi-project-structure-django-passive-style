# Charter — logging-overhaul  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-4)과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 설정 | `config.py` | 소스 | `LogSettings`(필수 필드 검사·`LOG_APP_LEVELS`·`LOG_RETENTION_DAYS`, 지운 키 3개), `REQUIRED_LOG_FIELDS`, `LOG_REDACTED_SETTINGS`·`log_secret_values()` |
| 로깅 | `app/utils/logs/{config,setup,filters,redaction,handlers}.py` | 소스 | 구성 하나·uvicorn 전파·프로세스별 파일·`entry_process()`·헤더 표·`AppLevelFilter`·DSN 계정명·원문 가리기·회전 핸들러(신규) |
| Celery | `app/celery/app.py` | 소스 | `setup_logging` 수신자 — `--logfile`·프로세스 종류 |
| 주석 | `app/core/resources.py` | 소스 | ADR-019 설명의 핸들러 이름 |
| 예시 | `.env.example` | 설정 | 로그 절 |
| 테스트 | `tests/utils/test_log_overhaul.py`(신규), `tests/utils/{test_logs,test_log_settings,test_log_redaction,conftest}.py`, `tests/core/test_settings_contract.py` | 테스트 | |
| 문서 | `README.md`(로깅 절 신설·업그레이드 노트), `docs/guides/ARCHITECTURE.md`(§3.2 표·§5·§12), `docs/guides/DEVELOPMENT.md`(§1), `docs/guides/workflows/server-lifecycle.html`(로깅 문단·부록), `docs/crp/groups/logging-overhaul/`, 이전 그룹 residual-risk(덧붙임) | 문서 | |

- 착수 기준선 커밋: `bb33c22` (main) · 브랜치 `feat/logging-overhaul`
- 마이그레이션: 변경 없음 · 의존성: 변경 없음(fakeredis 는 기존 dev 의존성, 스모크에만 사용)

## 2. 계약 (Contract)

### 2-1. 불변식
- INV-1: 앱·`python main.py`·`uvicorn main:app` CLI·Celery 워커의 콘솔·파일 줄이 같은 형식이다 (`test_uvicorn_lines_use_project_format[main.py|cli]`·`test_celery_worker_lines_use_project_format`·`test_celery_logfile_is_respected_with_project_format`)
- INV-2: 저장소 밖 코드의 헤더는 로거 이름 표를 따른다 (`test_external_header_comes_from_logger_name`)
- INV-3: 필수 필드가 빠진 포맷은 기동을 거부한다 (`test_format_without_required_fields_is_rejected`)
- INV-4: 헤더별 레벨이 걸러지고 root 는 최솟값이다 (`test_app_levels_filter_by_header`)
- INV-5: 웹·워커·beat 는 다른 파일에 쓴다 (`test_files_are_split_by_process`·`test_web_and_worker_write_their_own_files`·`test_import_time_lines_of_worker_go_to_worker_files`·`test_celery_receiver_in_beat_uses_beat_files`)
- INV-6: 자정·크기 회전, 보관 경계(정확히 N일 전 유지), `0` 은 삭제 안 함, 분할 파일도 삭제 (`test_midnight_rollover_names_file_by_date`·`test_size_rollover_splits_within_the_day`·`test_retention_deletes_only_older_files`)
- INV-7: 설정 비밀값 원문·DSN 계정명이 앱·uvicorn CLI·Celery·파일 어디에도 없다 (`test_secret_values_never_reach_any_output`·`test_dsn_user_and_password_are_masked`·`test_configured_secret_values_are_masked_anywhere`), 비밀 설정은 목록에 있다 (`test_every_secret_setting_is_redacted_from_logs`)
- INV-8: 지운 키가 환경에 남아도 무시된다 (`test_removed_keys_left_in_environment_are_ignored`)

### 2-2. 비목표
- uvicorn `--reload` 감시 프로세스의 몇 줄(앱을 import 하지 않는다) — R-002
- 다중 프로세스 파일 회전의 자동 감지 — ADR-009, R-001
- 라이브러리 로거 하나하나의 개별 레벨(헤더 단위까지만)

## 3. 인수 기준 (GATE 3)
- [x] `.env` 없는 저장소 밖 클론에서 `pytest -m "not mysql and not browser"` 통과, skip·xfail·xpass 0
- [x] `mysql`·`browser` 마커는 로컬 `--collect-only` 만
- [x] `ruff check`·`ruff format --check`·mypy(1.20.2 순수 Python 빌드) 클린
- [x] 새 테스트의 fail-on-revert 결과가 run-log 에 있다
- [x] 실기동 스모크(uvicorn CLI·`python main.py`·Celery solo 워커) 결과가 run-log 에 있다
- [x] `review_gate` 의 네트워크 없는 단계 결과가 run-log 에 있다

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성.
