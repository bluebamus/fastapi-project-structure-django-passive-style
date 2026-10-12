# Charter — admin-login  (Charter v0.1 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다. 비면 코드 금지.
> 변경 시 버전·날짜를 올린다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001~REQ-003)·불가침 제약(C-1~C-6)과 모순될 수
> 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory) — 검수 대상 *전부*

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 설정 | `config.py`, `.env.example`, `pyproject.toml`·`uv.lock` | 소스·설정 | `ADMIN_DISABLED`·`validate_removed_settings`, 승인 플래그 제거, `itsdangerous` |
| 관리 로그인 | `app/core/security/admin_auth.py`·`admin_credentials.py` (신규) | 소스 | `AdminAuthBackend`·쿠키·한도·자격 확인 훅 |
| 조립 | `app/core/apps/wiring.py`, `app/core/bootstrap.py` | 소스 | `create_admin` 백엔드 주입, `admin_disabled` 분기 |
| 자격 확인 | `app/features/auth/admin_credentials.py` (신규), `app/features/auth/apps.py`, `app/features/auth/services/auth_service.py` | 소스 | `UserAdminCredentials`, `ready()` 등록, `verify_credentials` 추출 |
| 로그인 화면 | `app/templates/admin/sqladmin/login.html` (신규) | 템플릿 | Bootstrap 5.3.8 + SRI |
| 관리 뷰 | `app/features/*/admin.py` | 소스 | `column_filters` → `sqladmin.filters`, docstring |
| 주석·docstring | `app/core/middlewares/client_ip.py`, `scripts/create_superuser.py`, `scripts/new_app.py`, `migrations/versions/e5a7c2d9f310_*.py` | 소스 | 배포 전 할 일, 생성 템플릿 |
| 테스트 | `tests/core/security/test_admin_auth.py`, `app/features/auth/tests/test_admin_credentials.py`, `tests/core/test_admin_{login_flow,disabled,pages,wiring}.py`, `tests/browser/test_admin_login.py`, `tests/integration/test_mysql_admin_login.py`, 기존 설정·문서 테스트 | 테스트 | 단계별 단위·통합·mysql·browser |
| 문서 | `README.md`, `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/*.html`(신규 `admin-auth-guide.html` 포함), `docs/crp/groups/{admin-login,service-hardening}/` | 문서 | 배포 전 할 일·관리 로그인·`ADMIN_DISABLED`·세션 범위 |

- 착수 기준선 커밋: `f6e5f13` (main)
- 마이그레이션: 변경 없음(리비전 docstring 만 수정 — 단일 head `a3c9e8f1b274`, `alembic check` 무드리프트)

## 2. 계약 (Contract)

### 2-1. 지원 구성 (Supported configs)
- Python >=3.13 · SQLAdmin 0.32 · starlette `SessionMiddleware` + itsdangerous · Redis 필수(레이트 리밋)
- 관리 화면 조립은 `config.INSTALLED_APPS` + App Registry(`create_admin`)만 지원한다. 자격 확인은 설치 앱의 `ready()` 등록으로만 들어온다
- 로그인 화면은 jsDelivr CDN 의 Bootstrap CSS 를 쓴다(SRI 고정)

### 2-2. 위협 모델 (Threat model)
- 방어한다: 무인증 관리 화면 접근, 세션 고정, CSRF(SameSite=Strict), 계정 열거(사유 미구분·더미 해시), 무차별 대입(레이트 리밋),
  쿠키 위조(HMAC 서명)·탈취(HttpOnly·Secure·8시간), 강등 후 잔존 권한(매 요청 DB), 관리 화면 노출(`ADMIN_DISABLED`), 로그 유출
- 방어하지 않는다: 서버 측 세션 폐기(로그아웃 전 복사한 쿠키 — R-001), 로그인 CSRF 토큰(R-002), 관리 화면 안 세분 권한(R-003),
  키 유출 자체(`SESSION_SECRET_KEY` 는 배포 비밀 관리 책임)

### 2-3. 불변식 (Invariants)
- INV-1: core 는 features 를 import 하지 않는다 (C-1)
- INV-2: 메인 앱에 `SessionMiddleware` 가 없고 API 는 `admin_session` 으로 인증되지 않는다 (C-2)
- INV-3: `ADMIN_DISABLED=true` 면 관리 계층이 로드되지 않고 응답·헤더·로그에 경로가 없다 (C-3)
- INV-4: 관리 권한은 매 요청 DB 로 확인하고 세션에는 id 만 있다 (C-4)
- INV-5: 비밀번호·해시는 로그에 없다 (C-5)
- INV-6: 로그인 화면은 독립 문서·JS 없음·SRI·자동 이스케이프 (C-6)
- INV-7: 등록된 모든 관리 뷰의 목록·필터·상세가 슈퍼유저에게 200 이다 (ADR-009)

### 2-4. 비목표 (Non-goals)
- 서버 측 세션 저장소(Redis 세션)·강제 로그아웃 목록, 로그인 폼 CSRF 토큰, 2FA, 관리 화면 안의 역할 기반 권한
- 시각 컬럼 필터(UTCDateTime 용 필터 클래스)
- 이 목록의 시나리오에서의 실패는 "결함"이 아니다

## 3. 인수 기준 (Acceptance Criteria) — GATE 3 체크리스트
- [x] 전 테스트 실제 실행·통과 — `.env` 없는 클론에서 `pytest -m "not mysql and not browser"` skip·xfail·xpass 0, 커버리지 `fail_under`(pyproject) 충족
- [x] `mysql`·`browser` 마커 테스트는 로컬에서 `--collect-only` 로 수집 확인, 실행은 CI
- [x] `ruff check`·`ruff format --check`·mypy(순수 Python 빌드 1.20.2) 클린
- [x] 새 동작마다 단위 테스트와 fail-on-revert 결과가 run-log 에 있다
- [x] `ENV=test uv run python -m scripts.review_gate --fast` 통과
- [x] 실제 기동 스모크(uvicorn + SQLite 파일 DB + fakeredis TCP, 저장소 밖 임시 경로) — create_superuser → 로그인 → `/admin/` 200 → 모든 목록 200 → 로그아웃
- [x] 문서 정합 테스트(`tests/test_docs_*.py`) 통과, 새 가이드 등록

## 4. 변경 이력
- v0.1 (2026-10-12): 최초 작성. Round 1~2 로 인수 기준을 모두 닫았다.
