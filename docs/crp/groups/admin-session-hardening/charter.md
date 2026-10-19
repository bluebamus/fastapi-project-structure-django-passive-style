# Charter — admin-session-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 REQ-001·REQ-002·C-1~C-6 과 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 관리 세션 | `app/core/security/admin_session.py`(신규 — `AdminSessionStore`·`RedisSessionMiddleware`·`AdminSessionCookie`), `config.py`(`SessionSettings.ADMIN_SESSION_*`), `.env.example` | 소스 | Redis 서버 세션 |
| 관리 인증·CSRF | `app/core/security/admin_auth.py`(`AdminCsrf`·`AdminCsrfMiddleware`·`require_post_logout`), `app/core/apps/wiring.py`(`create_admin`) | 소스 | 로그인 이후 CSRF·POST 로그아웃 |
| 템플릿 | `app/templates/admin/sqladmin/base.html`(신규 — 원본 확장), `app/templates/admin/sqladmin/filters/local_date_filter.html` | 소스 | meta·스크립트, 기간 입력 |
| 즉시 폐기 | `app/core/security/dependencies.py`(`get_admin_session_store`), `app/features/user/{services/user_service.py,dependencies/user_dependencies.py,admin.py}`, `scripts/create_superuser.py` | 소스 | API·관리 화면·비밀번호 변경 |
| 기간 필터 | `app/core/admin_filters.py`(`LocalDateFilter` 연산 `between`) | 소스 | |
| 테스트 | `tests/core/security/test_admin_session.py`(신규), `tests/core/test_admin_csrf.py`(신규), `tests/core/security/test_admin_auth.py`, `tests/admin_login.py`, `tests/core/test_admin_{login_flow,pages,wiring,disabled,date_filter}.py`, `app/features/user/tests/test_endpoint.py`, `tests/scripts/test_create_superuser.py`, `tests/integration/test_mysql_admin_login.py`, `tests/browser/test_admin_login.py` | 테스트 | |
| 문서 | `README.md`, `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/{admin-auth-guide,server-lifecycle-guide}.html`, 이전 그룹 residual-risk(덧붙임), `docs/review/` 2개(로컬 전용, 커밋하지 않음) | 문서 | |

- 착수 기준선 커밋: `a3af9ac` (main)
- 마이그레이션: 변경 없음
- 의존성: 추가 없음 · `itsdangerous` 직접 의존 제거(ADR-007 — 서명 쿠키 세션을 더는 쓰지 않는다)

## 2. 계약

### 2-1. 위협 모델
- 방어한다: 로그아웃 전에 복사해 둔 관리 세션 쿠키의 재사용, 강등·비활성화·삭제·비밀번호 변경 뒤에도 살아 있는 관리 세션, 세션 고정,
  Redis 키 유출로 쿠키를 만드는 것, 로그인 이후 생성·수정·삭제·일괄 삭제·가져오기·로그아웃의 CSRF, `<img src>` 로 강제 로그아웃,
  기간 필터 입력으로 500 이 나는 것.
- 방어하지 않는다: Redis 자체의 탈취(세션 내용·CSRF 토큰을 읽을 수 있다 — 쿠키는 만들 수 없다), sqladmin `@action`(GET) 사용자 정의 작업의
  CSRF(이 저장소는 쓰지 않는다, R-001), 같은 경로를 메서드별 라우트로 나눈 405 의 불완전한 `Allow`(사용자 결정으로 수용, ADR-006).

### 2-2. 불변식
- INV-1: `admin_session` 쿠키 값은 무작위 세션 ID 뿐이다. Redis 키는 `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}` 이고 세션 ID 자체는 Redis 어디에도 없다.
- INV-2: 세션은 절대 만료(생성 시각 + `ADMIN_SESSION_MAX_AGE_SECONDS`)를 넘지 못하고, 미사용 만료(`ADMIN_SESSION_IDLE_SECONDS`)는 요청마다 다시 센다.
- INV-3: 로그아웃·로그인(회전)·비활성화·강등·삭제·비밀번호 변경 뒤에는 그 이전 세션 키가 Redis 에 없다.
- INV-4: `/admin` 아래 POST·PUT·PATCH·DELETE 는 세션 토큰과 같은 토큰(헤더 `X-CSRF-Token` 또는 폼 `csrf_token`)이 있을 때만 sqladmin 에 닿는다. 로그아웃은 POST 전용이다.
- INV-5: Redis 를 쓸 수 없으면 관리 화면은 요청을 통과시키지 않는다(503).
- INV-6: `ADMIN_DISABLED=true` 에서 세션 미들웨어·저장소가 생기지 않고 sqladmin 이 로드되지 않는다.
- INV-7: 기간 필터는 양 끝 포함(`S 0시 <= t < E+1 0시`, 지역 날짜 → UTC)이고, 형식 오류·역순은 필터 미적용 + WARNING 이다.

### 2-3. 비목표
- 관리 화면의 세분 권한, 세션 목록 화면, 405 `Allow` 보정, access 토큰 수명 변경(security-ops-hardening ADR-006 유지).

## 3. 합격 기준
- 단계별 단위 테스트 + fail-on-revert(대상 파일을 작업 폴더 밖에 복사 → 변이 → 지정 테스트 실패 확인 → 복원).
- 기존 로그인 통합·browser(수집)·mysql(수집) 테스트가 토큰·POST 로그아웃으로 통과. browser 는 생성·삭제·로그아웃을 실제 브라우저로(대기는 `load`/`domcontentloaded`).
- ruff check·format, mypy, 인프라 제외 pytest(`.env` 없는 저장소 밖 사본) skip·xfail 0, `scripts/review_gate.py` 의 네트워크 없는 단계.
