# Charter — service-hardening  (Charter v0.2 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다. 비면 코드 금지.
> 변경 시 버전·날짜를 올린다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-15)과 모순될 수
> 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory) — 검수 대상 *전부*

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| CI | `.github/workflows/ci.yml` | 설정 | 단계 A1 — `uv sync --locked` |
| 설정 | `config.py`, `.env.example` | 소스·설정 | A2 DSN, B1·B2 접속 로그 설정, D 시간대, F1 JWT·레이트 리밋 설정 |
| 마이그레이션 | `migrations/env.py`, `migrations/versions/` | 소스 | A2 URL 전달, D UTC 변환 리비전, F2 `is_superuser`·`author_id` 리비전 |
| DB 세션·라우팅 | `app/core/db/{session,router,errors}.py` | 소스 | A3 잠금 읽기, B5 오류 코드 변환 |
| 모델 기반·시각 타입 | `app/core/models/{models_base,types}.py` | 소스 | D1 `UTCDateTime`·`utc_now` 기본값 |
| Repository 기반 | `app/core/repositories/repository_base.py` | 소스 | A3 기본 정렬 (공개 메서드 8개 유지) |
| 자원 수명주기 | `app/core/resources.py`, `app/core/bootstrap.py` | 소스 | E1 `get_redis`·`/ready`, B7 registry |
| 앱 registry | `app/core/apps/{config,registry,wiring}.py` | 소스 | E2 `AppConfig.tasks_module` |
| 미들웨어 | `app/core/middlewares/` | 소스 | B1 `ClientIPResolver`, B2 접속 로그 |
| core 보안 | `app/core/security/` (신규) | 소스 | F1 `TokenService`·`RefreshTokenStore`·`RateLimiter`, F2 `Principal`·`OwnershipPolicy` |
| Celery | `app/celery/` | 소스 | D `enable_utc`, E2 include 를 `INSTALLED_APPS` 에서 |
| 기능 | `app/features/{auth,user,blog,sns,reply,catalog,reports,home}/` | 소스·테스트 | B·F2 정책 적용, E2 기능별 `tasks` |
| 운영 스크립트 | `scripts/create_superuser.py` (신규) | 소스 | F2 |
| 테스트 | `tests/`, `app/features/*/tests/` | 테스트 | 단계별 단위 테스트, `mysql` 마커 스모크 |
| 문서 | `README.md`, `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/*.html` | 문서 | 각 단계에서 바뀐 계약을 반영 |

- 착수 기준선 커밋: `f7d6dcc` · 추적 `.py` 중 테스트 외 **209** · 테스트 **122**
  (`git ls-files '*.py'` 에서 `tests/` 와 `*/tests/` 를 나눠 셌다)
- 기준선 상태: `pytest -m "not mysql and not browser"` **713 passed · 22 deselected · skip 0**

## 2. 계약 (Contract)

### 2-1. 지원 구성 (Supported configs)
- Python >=3.13 · SQLAlchemy async · SQLite(단위) / MySQL 8.4(통합, `mysql` 마커 — CI 가 돌린다)
- Redis 는 필수다(ADR-011). 단위 테스트는 fakeredis 로 실물 클래스를 시험한다
- 앱 합류는 `config.INSTALLED_APPS` + `apps.py` AppConfig 경로만 지원한다(태스크 포함)
- 신뢰 프록시 홉 수(`TRUSTED_PROXY_HOPS`)는 배포가 정하는 사실로만 받는다

### 2-2. 위협 모델 (Threat model)
- 방어한다:
  - **크리덴셜 스터핑** — 로그인·가입 레이트 리밋(ip+username, ip), 비밀번호 Argon2
  - **refresh 토큰 탈취** — 회전 + 재사용 탐지 시 family 폐기, logout 폐기, 비활성화·삭제 시 사용자 전체 폐기
  - **IDOR** — 쓰기는 소유자 또는 슈퍼유저만, 작성자는 서버가 principal 로 채운다
  - **헤더 위조** — `X-Forwarded-For`/`X-Real-IP` 는 신뢰 홉 수 안에서만, `ipaddress` 검증
  - **로그 유출** — 비밀번호·토큰·민감 query 값·DSN 비밀번호·DB 원문이 로그·접속 로그·응답에 남지 않는다
  - 토큰 혼동 — `iss`/`aud`/필수 claim/`type` 검사, 허용 알고리즘 고정
- 방어하지 않는다:
  - 비목표(§2-4)에 적힌 것 전부, access 토큰의 만료 전 즉시 폐기(짧은 만료로 대신)
  - 분산 환경의 정밀 레이트 리밋(고정 창 경계의 순간 2배 허용은 수용)
  - 신뢰 홉 수를 잘못 설정한 배포(설정 오류는 배포 책임)

### 2-3. 불변식 (Invariants)
- INV-1: CI 의존성 설치는 락 불일치에서 실패한다 (C-15)
- INV-2: 비밀번호 특수문자가 DSN 에서 그대로 왕복하고, 마스킹 결과에 비밀번호가 없다 (C-6)
- INV-3: 잠금 읽기는 writer 로 가고, 읽기 전용 세션에서는 라우터 on/off 와 무관하게 거부된다 (C-7)
- INV-4: `get_all` 과 시간순 목록은 결정적 순서이고 offset 페이지가 겹치지 않는다. `BaseRepository` 공개 메서드는 8개다 (C-8)
- INV-5: DB 시각은 UTC 로 저장되고 naive 값은 거부된다 (C-9)
- INV-6: API 는 Redis 없이 준비 완료(`/ready` 200)가 되지 않는다 (C-10)
- INV-7: 인증은 core `get_current_principal` 주입으로만 걸린다. 기능 간 import 는 문서화된 예외만 (C-4·C-11)
- INV-8: 협력 객체는 생성자로 주입되고 provider 가 조립한다. 핸들러 본문에서 만들지 않는다 (C-3)
- INV-9: 커밋은 쓰기 핸들러가 응답 DTO 검증 후 1회 (C-5)
- INV-10: 민감 값은 로그·접속 로그·응답에 원문으로 남지 않는다 (C-12)
- INV-11: Celery 워커는 `INSTALLED_APPS` 밖의 기능을 import 하지 않는다 (C-14)
- INV-12: SQLAdmin 정책은 바뀌지 않는다 (C-13)

### 2-4. 비목표 (Non-goals)
- SQLAdmin 인증 백엔드(영구 비목표, ADR-020), OAuth 소셜 로그인, 이메일 인증·비밀번호 재설정 메일, 2FA
- access 토큰 즉시 폐기(짧은 만료 + refresh 폐기로 대신), 다중 테넌시, 슈퍼유저/일반 2단계를 넘는 RBAC
- 이 목록의 시나리오에서의 실패는 "결함"이 아니다

## 3. 인수 기준 (Acceptance Criteria) — GATE 3 체크리스트
- [x] 전 테스트 실제 실행·통과 — `pytest -m "not mysql and not browser"` skip·xfail·xpass 0, 커버리지 `fail_under`(pyproject) 충족
- [x] `mysql` 마커 테스트는 로컬에서 `--collect-only` 로 수집 확인, 실행은 CI
- [x] `ruff check`·`ruff format --check`·`python -m mypy .` 클린
- [x] 단계별 단위 테스트(새 동작마다)와 fail-on-revert 결과가 run-log 에 있다:
  - A: CI 계약 테스트, DSN 왕복(비밀번호 `p@ss:w/rd%#?`·IPv6·Alembic `%%`·Redis URL 파싱), 잠금 읽기 라우팅·거부(router on/off), 정렬 결정성·offset 페이지 비중복
  - B: 신뢰 홉 해석·위조 거부, 500 기록, query 마스킹, 컬럼 길이 자르기, null PATCH 422, 오류 코드별 변환, 날짜 상한
  - C: 공용 override 헬퍼의 read-only 세션 flush 거부, MySQL 스모크 수집
  - D: TypeDecorator bind/result/naive 거부, SQLite 마이크로초 보존, 모델 기본값 aware UTC, 응답 오프셋, 리포트 지역→UTC 경계·자정 경계 버킷, 접속 로그 지역 일자, Celery `enable_utc`, Alembic 렌더 훅, MySQL `DATETIME(6)` 왕복·KST→UTC 리비전(`mysql` 마커)
  - E: `/ready` Redis 실패 503, `get_redis`, 태스크 자동 발견 목록, 기능 제거 시 include
  - F1: 해시·레거시 이전, 토큰 claims·거부 사례, 회전·재사용 탐지·logout, 429+Retry-After·창 만료·성공 초기화, 엔드포인트 흐름
  - F2: 401·403·소유자 수정·슈퍼유저 우회·비활성화 후 refresh 실패·접속 로그 user_id·create_superuser
- [x] 불변식 구조 증거: INV-1 → CI 계약 테스트, INV-2 → DSN 왕복 테스트, INV-3 → `test_read_only_guard`·`test_db_router` 잠금 읽기 테스트, INV-4 → `test_repository_base` 정렬 테스트·공개 API 기준선, INV-7 → AST 계층 검사, 나머지 → 해당 단계 테스트
- [x] `ENV=test uv run python -m scripts.review_gate` 의 인프라·네트워크 불필요 단계 통과(생략한 단계는 run-log 에 사실로 적는다)
- [x] 질의 수준(design-baseline §0 = 보통)에 맞게 핵심 갈림길만 사용자 확정

## 4. 변경 이력
- v0.1 (2026-10-12): 최초 작성.
- v0.2 (2026-10-12): 단계 D — 인수 기준 D 항목 구체화. 마이그레이션 head 는 `e5a7c2d9f310`(시각 UTC·`DATETIME(6)`), 인벤토리 `app/core/models/types.py` 추가.
- v0.3 (2026-10-12): 단계 F2 완료로 §3 인수 기준을 모두 닫았다 — 전 단계(A~F2) 테스트·fail-on-revert 기록은 run-log Round 1~7, `review_gate --fast` 7단계 통과(pip-audit 포함), 질의 수준 보통(사용자 확정 갈림길: Redis 필수·UTC 저장·SQLAdmin 정책 유지).
