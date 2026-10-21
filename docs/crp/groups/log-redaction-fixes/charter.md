# Charter — log-redaction-fixes  (Charter v0.1 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다. 비면 코드 금지.
> 변경 시 버전·날짜를 올린다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001·REQ-002)·불가침 제약(C-1~C-5)과 모순될 수
> 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory) — 검수 대상 *전부*

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 로그 가리기 | `app/utils/logs/redaction.py` (신규), `app/utils/logs/setup.py` | 소스 | `SecretRedactor`·`install_record_redaction`, `configure_logging()` 에서 설치 |
| 예외 핸들러 | `app/core/bootstrap.py` | 소스 | `StarletteHTTPException` 핸들러 `headers=exc.headers` |
| Redis | `app/core/redis.py`, `app/core/resources.py`, `app/core/security/{rate_limit,refresh_store}.py`(docstring) | 소스 | `REDIS_MIN_VERSION`·`ensure_redis_version`·`UnsupportedRedisVersion`, lifespan 호출 |
| 커버리지 | `pyproject.toml`, `.github/workflows/ci.yml`(주석), `scripts/review_gate.py`(단계 설명) | 설정 | `fail_under = 0` |
| 테스트 | `tests/utils/test_log_redaction.py`·`tests/core/test_exception_headers.py`·`tests/core/test_redis_version.py` (신규), `tests/core/test_bootstrap.py`(가짜 Redis 에 `info`), `tests/scripts/test_gates.py` | 테스트 | 단계별 단위·계약 |
| 문서 | `README.md`, `.env.example`, `compose.test.yaml`(주석), `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/workflows/server-lifecycle.html`, `docs/crp/groups/{log-redaction-fixes,orm-raw-repository,service-hardening}/` | 문서 | 가리기·헤더·Redis 7.0·커버리지 0 |

- 착수 기준선 커밋: `b39478c` (main)
- 마이그레이션: 변경 없음
- 접속 로그 코드(`app/core/middlewares/user_info_middleware.py`·`app/features/home/**`)는 **범위 밖**(ADR-002 — 결정으로 유지)

## 2. 계약 (Contract)

### 2-1. 지원 구성 (Supported configs)
- Python >=3.13 · Redis **7.0 이상**(INFO 를 막은 관리형 Redis 는 확인 생략 + WARNING) · uvicorn 직접 실행(`setup_uvicorn_logging()`)과 CLI(`uvicorn main:app`) · Celery 워커
- 가리기는 `app.utils.logs` 를 import 해 `configure_logging()` 이 불린 프로세스에서 동작한다(API·Celery·Alembic 모두 해당)

### 2-2. 위협 모델 (Threat model)
- 방어한다: 로그 파일·콘솔·수집기로 나간 traceback·메시지에서 DSN 비밀번호·키=값 비밀·Bearer·JWT 유출, 405/401/429 의미 헤더 손실, 7.0 미만 Redis 로 인한 레이트 리밋 500
- 방어하지 않는다: 형식 없는 자유 텍스트 비밀값(R-002), `configure_logging()` 이전에 만들어진 레코드·`exc_info` 를 직접 읽는 외부 핸들러(R-003), INFO 를 막은 Redis 의 실제 버전(R-004), 접속 로그 DB 행의 원문(R-001)

### 2-3. 불변식 (Invariants)
- INV-1: 각 핸들러 경로(앱 console·file·error_file, uvicorn 직접 실행·CLI, Celery 포매터, 외부 로거)에서 비밀값 없음 + `***` 있음 + 예외 타입·체인·파일·줄·`stack_info` 남음 (C-1)
- INV-2: 405 응답의 `Allow` 는 실제 허용 메서드와 같고, `HTTPException(headers=…)` 의 헤더가 응답에 실리며, 본문 봉투는 그대로다 (C-3)
- INV-3: `REDIS_MIN_VERSION` = 소스가 쓰는 명령의 요구 버전 최댓값, 미만이면 기동 거부·이상이면 통과·INFO 불가면 경고 후 계속 (C-4)
- INV-4: `fail_under` 는 pyproject 에 한 번, 값 0, CI·게이트 명령줄에 `--cov-fail-under` 없음, CI 는 `--cov=app --cov-report=term-missing` (C-5)

### 2-4. 비목표 (Non-goals)
- 접속 로그 저장 필드 축소·해시·보존 기간(ADR-002)
- 구조화(JSON) 로그·외부 수집기 연동, 로거별 마스킹 정책
- Redis 서버 기능 탐지(명령별 probe) — 버전 비교만 한다
- 이 목록의 시나리오에서의 실패는 "결함"이 아니다

## 3. 인수 기준 (Acceptance Criteria) — GATE 3 체크리스트
- [x] 전 테스트 실제 실행·통과 — `.env` 없는 저장소 밖 사본에서 `pytest -m "not mysql and not browser"` skip·xfail·xpass 0
- [x] `mysql`·`browser` 마커 테스트는 로컬에서 `--collect-only` 로 수집 확인, 실행은 CI
- [x] `ruff check`·`ruff format --check`·mypy(순수 Python 빌드 1.20.2) 클린
- [x] 새 동작마다 단위 테스트와 fail-on-revert 결과가 run-log 에 있다
- [x] `ENV=test uv run python -m scripts.review_gate --fast` 통과
- [x] 문서 정합 테스트(`tests/test_docs_*.py`) 통과

## 4. 변경 이력
- v0.1 (2026-10-13): 최초 작성. Round 1~2 로 인수 기준을 모두 닫았다.
