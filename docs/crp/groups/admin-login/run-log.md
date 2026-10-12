# Run Log — admin-login (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-12 (base SHA: `f6e5f13`) · 계획
- **트리거:** 사용자 요청 REQ-001(배포 전 할 일 문서화 + Bootstrap 로그인 + `/admin` 로그인)
- **검수 범위:** `/admin` 조립 지점(`app/core/apps/wiring.py`·`app/core/bootstrap.py`), 설정, 문서, sqladmin 0.32 소스
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 3 · LOW 1 → ledger F-001 ~ F-005
- **수렴 판정:** `NOT CONVERGED` (Open Fix 5)

### Round 1 — 2026-10-12 · 관리 로그인 · Bootstrap 화면 · 배포 전 할 일
- **트리거:** REQ-001 — ADR-001~ADR-004 · ADR-007 · ADR-008
- **변경:**
  - `app/core/security/admin_auth.py`(신규) — `AdminAuthBackend`·`AdminSessionCookie`·`AdminLoginLimits`. `app/core/security/admin_credentials.py`(신규) — `AdminCredentials` 계약·등록 훅.
  - `app/features/auth/admin_credentials.py`(신규) — `UserAdminCredentials`·`default_admin_credentials`. `app/features/auth/apps.py` — `ready()` 등록.
    `app/features/auth/services/auth_service.py` — `verify_credentials` 추출(`AuthService.authenticate` 가 위임, 동작 동일).
  - `app/core/apps/wiring.py` — `create_admin` 이 백엔드를 조립·주입(`authentication_backend`·`templates_dir`), 자격 확인 미등록·쿠키 이름 충돌 시 `ImproperlyConfigured`.
  - `app/templates/admin/sqladmin/login.html`(신규) — Bootstrap 5.3.8, SRI `sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB`
    (jsDelivr 파일과 npm tarball 의 같은 파일을 내려받아 계산, 두 파일 바이트 일치).
  - `config.py` — `ADMIN_UNAUTHENTICATED_ACK`·`_guard_unauthenticated_admin` 제거, `TRUSTED_PROXY_HOPS`·`SessionSettings` 주석. `app/core/bootstrap.py` — 무인증 WARNING 제거.
  - 의존성 `itsdangerous>=2.2.0`(`uv add`, 락 갱신, `uv lock --check` 통과).
  - 배포 전 할 일 5항목 — README·`.env.example`·ARCHITECTURE·DEVELOPMENT·HTML 안내서·리비전 `e5a7c2d9f310` docstring 맨 위·`ClientIPResolver`·`create_superuser` docstring.
- **수렴 판정:** F-001~F-005 Fixed

### Round 2 — 2026-10-12 · ADMIN_DISABLED · 세션 범위 · 가이드 · 목록 500
- **트리거:** REQ-002(추가 요청 A~E) · REQ-003(감독자 추가 확인) — ADR-005 · ADR-006 · ADR-009
- **변경:**
  - `config.py` — `ADMIN` → `ADMIN_DISABLED`(기본 false), `REMOVED_SETTINGS`·`validate_removed_settings()`(import 시점, ENV=test 제외, 대소문자 무시, 환경 변수 + `.env`).
    `app/core/bootstrap.py` — `create_app(admin_disabled=…)`, 비활성 로그 `관리 화면 비활성화 (ADMIN_DISABLED=true)`(경로 없음).
  - 세션 범위 확인(ADR-006): 메인 앱 `user_middleware` 에 `SessionMiddleware` 없음, SQLAdmin 하위 앱에 1개, `get_current_principal` 은 Bearer 만,
    `SESSION_SECRET_KEY` 소비처는 `wiring.create_admin`(서명)과 `config` 검증뿐 — 감독자 사전 확인과 일치.
  - `app/features/*/admin.py` 7개 — `column_filters` 를 `BooleanFilter`·`OperationColumnFilter` 로(시각 필터 제외), docstring 의 `ADMIN` 서술.
    **결함 재현:** 수정 전 실제 기동 스모크에서 로그인 후 7개 목록이 모두 500(`AttributeError ... 'parameter_name'`).
  - `docs/guides/admin-auth-guide.html`(신규) — 12절, Mermaid 도식 7개(구성도·주입 그래프·기동 결정 흐름·로그인 시퀀스·요청별 판정·로그아웃·계정 수명주기).
    기존 안내서와 같은 스타일·고정 버전 Mermaid CDN·`data-source` 코드 근거. 로컬 Chromium 으로 열어 7/7 렌더·콘솔 오류 0 확인.
    `tests/test_docs_references.py` 의 `HTML_GUIDES`·`DOC_INDEX_ORDER` 에 등록, README 문서 표·ARCHITECTURE §8 에서 링크.
  - 모든 문서·주석·생성 템플릿(`scripts/new_app.py`)의 `ADMIN` 서술 갱신, service-hardening R-001 해소·ADR-020/C-13/INV-12 대체 표시.
- **새 테스트:**
  - `tests/core/security/test_admin_auth.py`(15) — 성공·400 동일 본문·비관리자·429+Retry-After·ip 한도·키 접두사 분리·성공 시 카운터 초기화·로그 비밀번호 없음·세션 고정 방지·강등 거부·로그아웃·비문자열 id·다른 키 서명·쿠키 속성(Secure 2종)
  - `app/features/auth/tests/test_admin_credentials.py`(5) — 활성 슈퍼유저만, 틀린 비밀번호·없는 사용자·비슈퍼유저·비활성 None, `is_admin` DB 추종(강등 즉시), bcrypt 재해시 커밋, 기본 조립
  - `tests/core/test_admin_login_flow.py`(8) — `create_superuser.main(--password-stdin)` → 302 → 400 → 302 → 200 → 로그아웃 302, 일반 사용자 실패, DB 비활성화 즉시 차단, Bootstrap 화면(링크·SRI·필드·레이블·JS 없음), 오류 이스케이프, 세션 범위 3종
  - `tests/core/test_admin_disabled.py`(13) — 아무것도 조립 안 됨, `/admin` 경로 5종 404, 알려진 경로 13종 응답·헤더에 `/admin` 없음, 로그에 경로 없음, 예전 `ADMIN` 환경(대소문자)·`.env`·import 시점 실패, 비슷한 이름 통과
  - `tests/core/test_admin_pages.py`(1) — 슈퍼유저로 등록된 7개 뷰 전부 목록·필터 1건·상세 200
  - `tests/core/test_admin_wiring.py`(+5) — 백엔드 조립, ENV 별 쿠키 옵션(4), 자격 확인 미등록, 쿠키 이름 충돌, 템플릿 덮어쓰기 순서
  - `tests/core/test_security_hardening.py`·`tests/core/test_deployment_safety.py` — 승인 플래그 제거 회귀(배포 환경 허용·잔존 무시·코드/운영 문서에 이름 없음·배포 기동 시 백엔드 부착)
  - `tests/integration/test_mysql_admin_login.py`(`mysql`) — `python -m scripts.create_superuser --password-stdin` 서브프로세스(임의 사용자명) → 같은 흐름. 로컬 수집만, 실행은 CI
  - `tests/browser/test_admin_login.py`(`browser`) — Chromium 으로 로그인 화면 입력(틀린 → alert, 맞는 → `/admin/`), Bootstrap CSS 적용(SRI 통과 신호), 쿠키 속성, 모든 뷰 목록 200, 로그아웃. 로컬 수집만, 실행은 CI
- **fail-on-revert(저장소 밖 클론에서 변이를 넣고 실행 후 저장소 원본으로 복원 — 32종 모두 감지):**
  세션 clear 제거 · authenticate DB 확인 생략 · logout 미비움 · SameSite lax · path `/` · 쿠키 이름 · max_age · 레이트 리밋 무력화 · 키 접두사 공유 ·
  성공 시 카운터 초기화 제거 · 실패 로그에 비밀번호 · 사용자명 길이 제한 제거 · Secure 고정 False · 자격 확인 미등록 가드 제거 · 쿠키 이름 충돌 가드 제거 ·
  `templates_dir` 미주입 · 비슈퍼유저 허용 · `is_admin` 의 `is_active` 무시 · 재해시 커밋 제거 · `ADMIN_DISABLED` 무시 · 비활성 로그에 경로 · `validate_removed_settings` 호출 제거 ·
  대소문자 구분 · `.env` 검사 제거 · 메인 앱에 `SessionMiddleware` · 템플릿 integrity 제거 · autocomplete 제거 · `error|safe` · 레이블 연결 제거 · 승인 플래그 필드 부활 ·
  user·blog 필터를 컬럼 그대로. `test_admin_pages` 는 수정 전 `admin.py` 에서 실패함도 직접 확인했다(`AttributeError ... 'parameter_name'`).
- **검사 (`.env` 없는 클론 — 로컬 `.env` 를 읽지 않게):** ruff check 통과 · ruff format --check 366 파일 · mypy 217 파일 이슈 0(순수 Python 빌드 1.20.2) ·
  `pytest -m "not mysql and not browser" --cov=app` **1052 passed · 34 deselected · skip 0** · coverage **96.37%** · `-m "mysql or browser" --collect-only` 34건 ·
  `ENV=test scripts.review_gate --fast` 7단계 모두 OK(pip-audit 포함) · `uv lock --check` 통과 · 마이그레이션 변경 없음(리비전 docstring 만)
- **실제 기동 스모크(저장소 밖 임시 경로 — uvicorn 127.0.0.1 빈 포트, SQLite 파일 DB, fakeredis TCP, 설정은 환경 변수만, `.env` 없는 클론에서 실행):**
  `/health` 200 · `create_superuser --password-stdin` 0 · `/admin/` 302(→ `/admin/login`) · `/admin/login` 200 · 틀린 비밀번호 400 · 맞는 비밀번호 302(→ `/admin/`) ·
  `/admin/` 200 · 7개 뷰 목록 200 · `/admin/user/list?is_active=true` 200 · 관리 쿠키로 `/api/v1/auth/me` 401 · 쿠키 path `/admin`·HttpOnly·Secure 없음(ENV=development) ·
  로그아웃 302 · 로그아웃 뒤 `/admin/` 302
- **낡은 서술 grep:** `git grep -n -E "인증 없|ADMIN=|ADMIN_ALLOW_UNAUTHENTICATED|ADMIN_UNAUTHENTICATED_ACK|unauthenticated"`(review·이전 그룹 CRP·specs 제외) —
  남은 줄은 모두 예외: Redis "인증 없이 접속"(관리 화면 무관), `/health` 주석, 예전 이름 이전 안내(config 메시지·`.env.example`·README·가이드), 제거 회귀 테스트, 이 그룹 CRP 기록
- **신규 finding:** HIGH 1(F-007, REQ-003) · MED 1(F-006)
- **수렴 판정:** **그룹 `CONVERGED`** — Open Fix 0, F-001~F-007 Fixed, 수용 항목은 residual-risk R-001~R-007

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 3 | 1 | 5 | NOT CONVERGED (계획) |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 5: F-001~F-005) | 단계 CONVERGED |
| 2 | 0 | 1 | 1 | 0 | 2 (Fixed 2: F-006·F-007) | **그룹 CONVERGED** (Open 0) |
