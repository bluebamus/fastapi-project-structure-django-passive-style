# Design Baseline — followups-2026-11 (기준 설계 문서)

> 이 그룹의 요구사항·설계 결정의 단일 기준. append-only.

## 0. 질의 수준 (Autonomy Level)
- [ ] **적극(Thorough)**
- [ ] **보통(Balanced)**
- [x] **간략(Lean)** — 지시서로 범위가 닫혀 있어 질문 없이 진행.

선택: **간략** · 선택일: 2026-11-12

## 1. 목적 / 배경
2026-11-11 정리로 compose 와 MySQL 통합 테스트가 사라져 실제 MySQL 자동 검증이 0건이 됐다. compose 없이 CI 서비스
컨테이너로 MySQL 에서만 드러나는 동작을 최소로 검증하고, 테스트 모듈 간 import 를 정리한다.

## 2. 요구사항 레지스터

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-11-12 | CI 전용 MySQL 최소 검증 | `tests/mysql` (평소 미수집), `MYSQL_TEST_URL` 없으면 실패, CI `mysql:8.4` 잡 + skip 0 판정, 문서 한 줄 | Active | INV-1·2, F-002, ADR-001·002 |
| REQ-002 | 2026-11-12 | 테스트 모듈 간 import 정리 | `test_disabled`→`test_deployment_safety`, `test_replica_fallback`→`test_router` 를 공용 헬퍼로 | Active | INV-3, F-001 |

## 3. 설계 결정 기록 (ADR)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-11-12 | 수집 제외는 `norecursedirs` 에 `tests/mysql` 추가(기본값 유지) | skip·deselect 는 게이트가 실패로 봄. 경로를 직접 주면 수집됨 | Accepted | |
| ADR-002 | 2026-11-12 | 변수 누락 판정은 session 픽스처의 `pytest.fail` | 수집(`--collect-only`)은 변수 없이 되고, 실행은 연결 전에 실패 | Accepted | |
| ADR-003 | 2026-11-12 | 라우팅 검증의 reader 는 같은 서버의 SELECT 전용 사용자 | 별도 replica 없이 "쓰기가 reader 로 가면 1142" 로 라우팅을 증명 | Accepted | |

## 4. 불가침 제약
- C-1: 로컬에서 MySQL 에 접속하지 않는다(로컬 게이트에 MySQL 단계 없음).
- C-2: skip·xfail 0 판정은 MySQL 잡에도 건다.

## 5. 변경 이력
- v1.0 (2026-11-12): 최초 작성.
