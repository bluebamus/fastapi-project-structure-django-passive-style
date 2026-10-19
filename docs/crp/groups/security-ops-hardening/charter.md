# Charter — security-ops-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 REQ-001·C-1~C-5 와 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 엔진 옵션 정본 | `app/core/db/session.py`, `migrations/env.py` | 소스 | `ENGINE_SAFETY_OPTIONS = {"hide_parameters": True}` 를 writer·reader·background·Alembic 엔진에 |
| 접속 로그 보존 | `config.py`(`MiddlewareSettings.ACCESS_LOG_RETENTION_DAYS`), `.env.example`, `app/features/home/{repositories/user_access_log_repository.py,services/user_access_log_service.py,dependencies/access_log_dependencies.py,tasks.py}` | 소스 | 배치 삭제·beat 일정 |
| 로그인 CSRF | `app/core/security/admin_auth.py`(`AdminLoginCsrf`), `app/templates/admin/sqladmin/login.html` | 소스 | synchronizer token |
| 날짜 필터 | `app/core/admin_filters.py`(신규), `app/templates/admin/sqladmin/filters/local_date_filter.html`(신규), `app/features/{home,blog,reply,sns,user,catalog,reports}/admin.py` | 소스 | `LocalDateFilter` |
| 테스트 | `tests/core/test_engine_hide_parameters.py`(신규), `app/features/home/tests/test_access_log_retention.py`(신규), `tests/integration/test_mysql_access_log_retention.py`(신규), `tests/core/test_admin_date_filter.py`(신규), `tests/admin_login.py`(신규), `tests/core/security/test_admin_auth.py`, `tests/core/test_admin_login_flow.py`, `tests/core/test_admin_pages.py`, `tests/integration/test_mysql_admin_login.py`, `tests/browser/test_admin_login.py` | 테스트 | |
| 문서 | `README.md`, `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/{admin-auth-guide,server-lifecycle-guide}.html`, 이전 그룹 residual-risk(덧붙임) | 문서 | |

- 착수 기준선 커밋: `d217bf2` (main)
- 마이그레이션: 변경 없음(스키마 변경 없음 — `ix_user_access_logs_created_at` 이 이미 있다)
- 의존성: 추가 없음

## 2. 계약

### 2-1. 위협 모델
- 방어한다: DB 오류 메시지·traceback·로그에 바인드 값(이메일·비밀번호 해시·토큰)이 실리는 것, 접속 로그(개인정보)가 무기한 쌓이는 것,
  다른 사이트가 `/admin/login` 에 폼을 보내 로그인시키거나 시도 한도를 소모시키는 것(로그인 CSRF), 관리 목록의 날짜 필터 입력으로 500 이 나는 것.
- 방어하지 않는다: 로그인 이후 sqladmin 이 그리는 생성·수정·삭제 폼과 GET 로그아웃의 CSRF(`SameSite=Strict`·`Path=/admin` 이 1차 방어, R-001),
  관리 세션의 서버 측 폐기(Redis 이전은 사용자 결정 대기, R-003), access 토큰 만료 전 권한 회수(사용자 결정으로 수용, ADR-006).

### 2-2. 불변식
- INV-1: 애플리케이션이 만드는 모든 SQLAlchemy 엔진은 `hide_parameters=True` 다(생성 지점 AST 검사 + 엔진 객체 검사).
- INV-2: 보존 삭제는 `created_at < now(UTC) - N일` 인 행만 지우고, 배치(최대 5,000행)마다 커밋한다. N=0 이면 DB 에 가지 않는다.
- INV-3: `/admin/login` POST 는 CSRF 토큰이 맞을 때만 레이트 리밋·자격 확인으로 간다. 맞지 않으면 403 이고 카운터·자격 확인은 건드리지 않는다.
- INV-4: `created_at` 이 있는 모든 관리 뷰의 목록은 날짜 필터 연산 3종과 잘못된 입력에 200 이다.

### 2-3. 비목표
- 관리 화면 세션의 Redis 이전, 로그인 이후 관리 폼의 CSRF 토큰, access 토큰 수명 변경, 접속 로그 저장 필드 변경(log-redaction-fixes ADR-002 유지).

## 3. 합격 기준
- 단계별 단위 테스트 통과 + fail-on-revert(대상 파일을 작업 폴더 밖에 복사 → 변이 → 지정 테스트 실패 확인 → 복원).
- 기존 로그인 통합·browser(수집)·mysql(수집) 테스트가 CSRF 토큰을 실어 통과. browser 대기는 `load` — `networkidle` 금지.
- ruff check·format, mypy, 인프라 제외 pytest(`.env` 없는 저장소 밖 사본) skip·xfail 0, `scripts/review_gate.py` 의 네트워크 없는 단계.
