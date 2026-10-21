# Charter — integration-e2e  (Charter v0.1 / 2026-10-20)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001~REQ-005)·불가침 제약(C-1~C-3)과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| e2e 환경 | `compose.e2e.yaml`, `tests/e2e/mysql/{primary,replica}/*.sh` | 인프라 | primary·GTID replica·Redis 7.4, profile `redis-old`(Redis 6.2) |
| 하네스 | `tests/e2e/conftest.py`, `tests/e2e/ledger.py`, `tests/e2e/openapi_check.py`, 루트 `conftest.py` | 테스트 | 대상 검사·기동·로그 수집·관리 화면 httpx 클라이언트·keep-alive 계측 |
| 스위트 | `tests/e2e/test_l0_harness.py`·`test_l2_api_matrix.py`·`test_l3_scenarios.py`·`test_l4_admin.py`·`test_l5_faults.py`·`test_l6_ops.py`·`test_zz_inventory.py`·`test_zz_secrets.py` | 테스트 | L1 회귀는 기존 스위트 그대로 |
| W0 | `tests/browser/conftest.py`·`tests/browser/test_redis_target.py`·`tests/core/test_dsn.py` | 테스트 | Redis 대상 명시 강제 |
| 결함 수정 | `app/core/security/dependencies.py` 등(ledger 참조) | 소스 | 테스트를 먼저 고정한 뒤 별도 커밋 |
| CI | `.github/workflows/ci.yml` | 설정 | job `e2e`, gate·mysql job 의 `REDIS_HOST`·`REDIS_PORT` |
| 의존성 | `pyproject.toml`·`uv.lock` | 설정 | `pytest-timeout`(dev) |
| 문서 | `README.md`, `docs/guides/DEVELOPMENT.md`, `docs/guides/ARCHITECTURE.md`, 이 그룹 6파일 | 문서 | |

- 착수 기준선 커밋: `eb47b6c` (main)
- 마이그레이션: 변경 없음

## 2. 계약 (Contract)

### 2-1. 불변식
- INV-1: 앱에서 뽑은 operation(38)·관리 뷰(7)·Celery 태스크(2)·beat 일정(1)·Redis 키 리터럴(11)이 모두 실행된 테스트로 채워지거나 사유가 적힌 N/A 다 (`test_zz_inventory.py`)
- INV-2: e2e 의 모든 접속 대상은 127.0.0.1 의 전용 포트다(아니면 하네스가 시작하지 않는다)
- INV-3: 실행이 만든 비밀번호·키·발급 토큰이 어떤 로그에도 원문으로 없다 (`test_zz_secrets.py`)
- INV-4: 브라우저 하네스의 Redis 대상은 명시돼야 한다 (`tests/browser/test_redis_target.py`)

### 2-2. 비목표
- CSRF 본문 버퍼링 상한의 결정·구현(측정만 — 사용자 결정, 계획서 §5-2)
- 405 `Allow` 불완전(메서드 분할 경로) — 현행 유지 결정, 값만 기록

## 3. 인수 기준 (GATE 3)
- [x] `pytest -m e2e` 통과 — 실패·skip·xfail 0, 인벤토리 빈 칸 0, 비밀값 0 (Windows 로컬 + Linux `.env` 없는 클론)
- [x] L1 회귀: `not mysql and not browser`·`mysql`·`browser` 통과, skip 0
- [x] `ruff check`·`ruff format --check`·mypy 클린, `review_gate --fast`
- [x] 결함 수정마다 fail-on-revert 결과가 run-log 에 있다

## 4. 변경 이력
- v0.1 (2026-10-20): 최초 작성.
