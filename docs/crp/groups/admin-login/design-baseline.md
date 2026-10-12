# Design Baseline — admin-login (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.
>
> 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다. 다른 그룹의 ID 를 가리킬 때는
> `service-hardening ADR-020` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-12 · 변경 이력: (없음)

> 핵심 갈림길은 사용자가 요청에서 정했다 — `/admin` 에 로그인을 붙이고(Bootstrap 화면 + `create_superuser`),
> 관리 화면을 끄는 설정은 기존 `ADMIN` 을 **`ADMIN_DISABLED`(true=끔)로 교체**한다(REQ-002 사용자 결정).

## 1. 목적 / 배경

`/admin`(SQLAdmin)은 service-hardening 까지 **인증 없는 관리 화면**이었다(service-hardening ADR-020 — 영구 비목표,
배포 환경은 `ADMIN_UNAUTHENTICATED_ACK` 승인 + 기동 WARNING). 사용자가 배포를 앞두고 관리 화면에 로그인을 붙이고,
배포 전에 해야 할 일을 모든 문서·주석에서 일관되게 보이게 하고, 관리 화면을 완전히 끌 수 있는 설정과 별도 인증
가이드를 요구했다.

방식은 이 저장소가 이미 쓰는 것을 따른다. SQLAdmin 조립은 `config.INSTALLED_APPS` + App Registry
(`app/core/apps/wiring.py` 의 `create_admin`, `app/core/bootstrap.py`)이고, 협력 객체는 생성자로 주입한다.
core 는 features 를 import 하지 않으므로 기능이 core 에 자신을 연결할 때는 `AppConfig.ready()` 의 등록 훅을 쓴다
(접속 로그 sink 와 같은 방식).

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "배포 전에 해야 할 일 에 대해 관련한 모든 문서와 주석에 업데이트를 수행해줘. bootstrap 기반으로 로그인 화면을 만들고 scripts/create_superuser.py로 생성자를 임의로 만들어 /admin에 로그인을 붙여 테스트를 수행해줘. 이후 로그인 페이지 구현 및 연동은 그대로 유지해줘." | ① 배포 전 할 일 4가지(`TRUSTED_PROXY_HOPS`·KST→UTC 리비전·첫 관리자·/admin 로그인)를 README·`.env.example`·설정 주석·가이드·리비전·`ClientIPResolver`·`create_superuser` docstring 에 일관되게 ② `/admin` 슈퍼유저 세션 로그인(SQLAdmin `AuthenticationBackend`, 생성자 주입, 레이트 리밋, 매 요청 DB 확인) ③ Bootstrap 로그인 화면(템플릿 덮어쓰기, SRI) ④ 무인증 승인 플래그 제거 ⑤ 단위·통합·mysql·browser 테스트, fail-on-revert ⑥ 로그인 화면·연동은 이후에도 유지 | Active | ADR-001~ADR-004 · ADR-007 · ADR-008 · C-1~C-6 · F-001~F-005 |
| REQ-002 | 2026-10-12 | "이 작업과 관련하여 차후 설계 및 동작을 이해할 수 있게 별도의 admin 인증 가이드 문서를 만들어줘. 세션과 관련한 인증이 admin에만 적용되고 다른 api 인증 및 별도 작업에는 사용하지 않는것인지 확인하고 맞다면 … 상세한 설명을 정리해줘. 필요한 모든 도식화를 … admin 페이지 자체를 사용하지 않는 설정이 존재해야 한다. 이 설정이 true이면, admin 페이지에 대한 링크 자체가 존재하지 않아야 한다." + 사용자 결정: `ADMIN` → `ADMIN_DISABLED` 교체 + "관련하여 모든 문서도 내용을 업데이트 하여 반영해줘" | ① `ADMIN_DISABLED`(기본 false) — true 면 마운트·sqladmin import·세션 미들웨어·백엔드 없음, 응답·헤더·로그에 경로 없음, 예전 `ADMIN` 잔존 시 기동 실패 ② 세션 범위 확인(세션은 /admin 전용)과 테스트 ③ `docs/guides/admin-auth-guide.html`(구성도·흐름도·시퀀스·쿠키·위협 모델·운영) ④ 모든 문서 반영 | Active | ADR-005 · ADR-006 · C-2 · C-3 · F-006 |
| REQ-003 | 2026-10-12 | (감독자 추가 확인) "sqladmin 0.32 와 ModelView 의 `column_filters` 에 모델 컬럼을 그대로 넘긴 정의가 맞지 않아 로그인 후 `/admin/<view>/list` 가 500 … 이 저장소에서도 확인하고, 같다면 `sqladmin.filters` 클래스로 고친다 … 모든 ModelView 의 list(필터 1건 포함)·상세 200 테스트" | 모든 `column_filters` 를 `sqladmin.filters` 객체로, 등록된 모든 뷰의 목록·필터·상세 200 테스트, 스모크·browser 에서도 목록 확인 | Active | ADR-009 · F-007 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | `/admin` 은 **활성 슈퍼유저 세션 로그인**이 필요하다. `AdminAuthBackend(sqladmin.authentication.AuthenticationBackend)` 하나가 login(폼 → 레이트 리밋 → 자격 확인 → `session.clear()` 후 사용자 id 만 저장)·authenticate(매 요청 DB 로 활성·슈퍼유저 확인, 아니면 세션 비움)·logout(세션 비움)을 맡는다. 실패 사유는 구분하지 않고(400), 한도 초과는 로그인 화면을 429 + `Retry-After` 로 다시 그린다. 세션 쿠키 `admin_session`·path `/admin`·SameSite=Strict·HttpOnly·Max-Age 8시간·Secure(ENV staging/production)·서명 키 `SESSION_SECRET_KEY` | 관리 화면은 브라우저 화면이라 서명 세션 쿠키가 표준이다. 권한을 쿠키에 담지 않고 매 요청 DB 로 보면 강등·비활성화가 즉시 반영된다(비용은 관리 요청마다 PK 조회 1회). 부모 생성자는 쿠키 옵션을 고를 수 없어 `self.middlewares` 를 직접 구성한다 | Accepted | service-hardening ADR-020 |
| ADR-002 | 2026-10-12 | 백엔드는 core(`app/core/security/admin_auth.py`)에 두고 사용자 조회는 **주입**받는다 — 계약 `AdminCredentials`(`verify`·`is_admin`)와 등록 훅(`app/core/security/admin_credentials.py`)을 core 에 두고, auth 앱이 `AuthConfig.ready()` 에서 `UserAdminCredentials`(`background_session` + core `PasswordHasher`) **팩토리**를 등록한다. 비밀번호 확인·bcrypt→Argon2 재해시는 API 로그인과 같은 `verify_credentials`(auth_service 모듈 함수로 추출, `AuthService.authenticate` 가 위임). 레이트 리미터는 `lambda: RateLimiter(app.state.redis)` provider, IP 는 `ClientIPResolver(TRUSTED_PROXY_HOPS)`, 한도는 `AUTH_LOGIN_*` 재사용·키 접두사 `admin-login:` 분리. 조립은 기존 SQLAdmin 조립 지점 `create_admin()` 이 하고, 팩토리가 없으면 `ImproperlyConfigured`. 로그인 화면 템플릿 객체는 `Admin` 생성 뒤 `backend.templates` 로 사후 주입 | core→features 금지(service-hardening C-4). 등록 훅은 접속 로그 sink 와 같은 문서화된 방식이다. 팩토리로 등록해야 `ready()` 가 도는 Alembic·Celery·CLI 에서 Argon2 더미 해시를 만들지 않고, `ADMIN_DISABLED=true` 에서 sqladmin 을 import 하지 않는다(SEC-01). Redis 클라이언트는 lifespan 이 만들기 때문에 조립 시점에는 없다. 인증 없는 관리 화면을 조용히 여는 것보다 기동 실패가 낫다 | Accepted | |
| ADR-003 | 2026-10-12 | 로그인 화면은 `app/templates/admin/sqladmin/login.html` 이 sqladmin 기본 템플릿을 덮어쓴다(`Admin(templates_dir=…)`, sqladmin 0.32 의 `ChoiceLoader` 가 `FileSystemLoader(templates_dir)` 를 패키지 템플릿보다 먼저 본다 — 코드로 확인). 독립 문서(base 미확장)·`lang="ko"`·viewport·Bootstrap **5.3.8** CSS(jsDelivr, `integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"` + `crossorigin="anonymous"`)·JS 없음·`admin.title`·`for`/`id` 레이블·`autocomplete="username"`/`"current-password"`·`required`·`autofocus`·`alert alert-danger`(자동 이스케이프)·`action=url_for('admin:login')` POST | 저장소에 템플릿 위치 관례가 없어 명세 기본값(`app/templates/admin/`)을 따른다. SRI 해시는 jsDelivr 파일과 npm 레지스트리 tarball 의 같은 파일을 내려받아 sha384 로 계산하고 두 파일이 바이트까지 같음을 확인했다. JS 를 싣지 않아 로그인 화면의 외부 스크립트 공격면이 없다 | Accepted | |
| ADR-004 | 2026-10-12 | 무인증 승인 플래그 `ADMIN_UNAUTHENTICATED_ACK` 와 배포 환경의 관리 화면 거부 규칙(`AppSettings._guard_unauthenticated_admin`)·기동 WARNING 을 제거한다. `.env`·환경에 남아 있어도 설정 클래스의 `extra="ignore"` 로 기동은 깨지지 않는다 | 로그인이 붙었으므로 "인증 없는 화면을 연다" 는 승인의 대상이 사라졌다. 남은 플래그는 뜻 없는 설정이고, 거부 규칙은 정상 배포를 막는다 | Accepted | service-hardening ADR-020, orm-raw-repository ADR-007 의 배포 환경 승인 규칙 |
| ADR-005 | 2026-10-12 | 관리 화면 스위치를 `ADMIN`(true=켬)에서 **`ADMIN_DISABLED: bool = False`**(true=끔)로 교체한다. true 면 `create_admin()` 을 부르지 않아 마운트·sqladmin import·세션 미들웨어·인증 백엔드가 모두 없고, 기동 로그는 `관리 화면 비활성화 (ADMIN_DISABLED=true)`(경로 없음). 예전 `ADMIN` 이 환경 변수나 `.env` 에 남아 있으면(대소문자 무시) `config.validate_removed_settings()` 가 import 시점에 기동을 멈춘다(ENV=test 제외 — `validate_env_source` 와 같은 기준). `create_app(admin_disabled=…)` 로 인자 이름도 맞춘다 | 사용자 결정. 뜻이 뒤집힌 이름 변경을 `extra="ignore"` 가 조용히 삼키면 `ADMIN=false` 로 끄던 배포가 **켜진 채로** 뜬다 — 그래서 이 이름만은 감지한다. 끈 관리 화면은 "막힌" 것이 아니라 "없는" 것이어야 위치가 드러나지 않는다 | Accepted | |
| ADR-006 | 2026-10-12 | 세션 인증은 **/admin 전용**이다(확인 결과): 메인 앱에는 `SessionMiddleware` 가 없고 SQLAdmin 하위 앱에만 있다, API 인증(`get_current_principal`)은 Bearer 만 읽는다, `SESSION_COOKIE_NAME` 은 접속 로그 기록용일 뿐이다, `SESSION_SECRET_KEY` 의 소비처는 관리 세션 서명과 설정 검증뿐이다. 관리 쿠키 이름이 `SESSION_COOKIE_NAME` 과 같으면 기동을 멈춘다 | 감독자 사전 확인과 코드가 일치했다. API 에 세션을 섞으면 쿠키 기반 CSRF 면이 API 로 넓어지고 토큰 폐기 모델과 섞인다. 이름이 같으면 접속 로그가 관리자 세션 쿠키 원문을 `session_id` 로 저장한다 | Accepted | |
| ADR-007 | 2026-10-12 | 의존성 `itsdangerous>=2.2.0` 을 추가한다(`uv add itsdangerous`, 락 갱신) | starlette `SessionMiddleware` 가 itsdangerous 로 쿠키를 서명한다. sqladmin 0.32 는 이것을 의존성으로 선언하지 않아, 없으면 인증 백엔드 생성이 `ImportError` 로 죽는다 | Accepted | |
| ADR-008 | 2026-10-12 | "배포 전에 해야 할 일" 은 같은 5항목(① `TRUSTED_PROXY_HOPS` ② KST→UTC 리비전 `e5a7c2d9f310` 의 `LEGACY_OFFSET`·백업 ③ `scripts/create_superuser.py` 첫 관리자 ④ /admin 슈퍼유저 로그인·`SESSION_SECRET_KEY` ⑤ 안 쓰면 `ADMIN_DISABLED=true`)으로 README 「운영 배포 체크리스트」·`.env.example` 머리말·ARCHITECTURE §11.1·관리 화면 인증 가이드·설정 주석·리비전 docstring 맨 위·`ClientIPResolver`·`create_superuser` docstring 에 싣는다 | 운영자가 어느 문서에서 시작해도 같은 목록을 보게 한다 | Accepted | |
| ADR-009 | 2026-10-12 | `column_filters` 는 `sqladmin.filters` 객체로 준다 — 불리언은 `BooleanFilter`, 문자열·정수는 `OperationColumnFilter`. 시각 컬럼(`UTCDateTime`)은 필터에서 뺀다 | sqladmin 0.32 의 목록 처리가 `filter_.parameter_name` 을 읽어, 컬럼을 그대로 넘기면 로그인 후 목록이 500 이다(이 저장소에서 재현). `OperationColumnFilter` 는 TypeDecorator 를 날짜로 인식하지 못해 시각 필터 값을 문자열로 바인딩한다(`UTCDateTime` 이 naive·비datetime 을 거부 → 500). 정렬은 그대로 된다 | Accepted | |

## 4. 불가침 제약 (Invariants — 위반 시 즉시 Fix)

- C-1: core 는 features 를 import 하지 않는다 — 관리 로그인의 사용자 조회는 `AppConfig.ready()` 가 등록한 자격 확인으로만 한다 (service-hardening C-4 유지) — ADR-002
- C-2: 세션 미들웨어는 SQLAdmin 하위 앱에만 있다. API 인증은 세션을 읽지 않는다 — ADR-006
- C-3: `ADMIN_DISABLED=true` 면 sqladmin·앱 `admin.py`·세션 미들웨어·인증 백엔드가 로드되지 않고, 앱 응답·헤더·기동 로그에 관리 화면 경로가 없다 — ADR-005
- C-4: 관리 권한은 매 요청 DB 로 다시 확인한다. 세션에는 사용자 id 만 담는다 — ADR-001
- C-5: 비밀번호·해시는 로그에 남지 않고 사용자명은 길이를 제한한다 (service-hardening C-12 확장) — ADR-001
- C-6: 로그인 화면 템플릿은 유지 대상이다 — 독립 문서·외부 JS 없음·SRI 고정·자동 이스케이프 — ADR-003

## 5. 변경 이력
- v0.1 (2026-10-12): 최초 작성. REQ-001·REQ-002·REQ-003, ADR-001~ADR-009, C-1~C-6 등재. ADR-001·ADR-004 로 service-hardening ADR-020 을 대체.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
