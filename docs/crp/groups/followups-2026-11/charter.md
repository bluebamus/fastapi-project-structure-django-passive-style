# Charter — followups-2026-11  (Charter v1.0 / 2026-11-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다. 비면 코드 금지.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| MySQL 전용 검증 | `tests/mysql/` | 테스트 | 평소 수집 제외(`norecursedirs`), CI `mysql` 잡 전용 |
| 수집 설정 | `pyproject.toml` (`norecursedirs`) | 설정 | |
| CI | `.github/workflows/ci.yml` (`mysql` 잡) | 설정 | `mysql:8.4` digest 고정 |
| 공용 테스트 헬퍼 | `tests/config_values.py`, `tests/core/db/routing_probe.py` | 테스트 | 테스트 모듈 간 import 제거 |
| 문서 | `README.md`, `docs/DEVELOPMENT.md` | 문서 | "MySQL 테스트는 CI 전용" |

- 새 테스트 파일: `tests/mysql/` 6개(테스트 9건). 기본 수집 개수는 변하지 않는다(1186).

## 2. 계약 (Contract)
### 2-1. 지원 구성
- `MYSQL_TEST_URL`(서버 URL, DB 이름 없이)로만 접속한다. 기본 접속 대상 없음.
### 2-2. 위협 모델
- 방어한다: 남의 MySQL 에 실수로 붙는 것(변수 없으면 연결 없이 실패), 테스트 간 데이터 섞임(테스트마다 DB·사용자 생성/삭제).
- 방어하지 않는다: `MYSQL_TEST_URL` 에 남의 서버를 직접 준 경우.
### 2-3. 불변식
- INV-1: 평소 `pytest`·게이트는 `tests/mysql` 을 수집하지 않는다(skip·deselect 아님).
- INV-2: `MYSQL_TEST_URL` 이 없으면 skip 이 아니라 실패한다.
- INV-3: 테스트 모듈이 다른 테스트 모듈을 import 하지 않는다.
### 2-4. 비목표
- 로컬 게이트(`scripts/review_gate.py`)에서 MySQL 실행, compose 복원, 복제 지연·장애 전환 검증.

## 3. 인수 기준
- [x] 전체 pytest 실패 0·skip 0, 수집 개수 불변
- [x] `pytest tests/mysql --collect-only` 9건 수집
- [x] `MYSQL_TEST_URL` 없이 `pytest tests/mysql` → 연결 없이 9 errors(설정 누락 메시지)
- [x] ruff·mypy·bandit gate·pip-audit·openapi_revert_check 통과
- [ ] CI `mysql` 잡 첫 실행 통과(push 금지 — 사용자 push 후 확인)

## 4. 변경 이력
- v1.0 (2026-11-12): 최초 작성.
