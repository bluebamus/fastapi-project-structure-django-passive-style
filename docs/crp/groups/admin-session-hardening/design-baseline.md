# Design Baseline — admin-session-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다. 다른 그룹의 ID 는
> `security-ops-hardening ADR-004` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

> 핵심 갈림길(Redis 이전 방식 = "방법 2: Redis 서버 세션", 405 현행 유지)은 사용자가 요청에서 정했다.

## 1. 목적 / 배경

관리 세션은 Starlette `SessionMiddleware`(itsdangerous 서명 쿠키)였다 — 내용 전체가 쿠키에 있어 로그아웃해도 복사해 둔 쿠키가
8시간 유효했고, 강등·비활성화는 매 요청 DB 확인으로만 막혔다(admin-login R-001·security-ops-hardening R-003). 로그인 이후 sqladmin
폼·삭제·로그아웃(GET)에는 CSRF 토큰이 없었고(security-ops-hardening R-001), 날짜 필터는 한 필터로 기간을 지정할 수 없었다(R-005).

## 2. 요구사항

| ID | 날짜 | 원문 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "관리 화면에 로그인한 뒤 쓰는 생성·수정·삭제 폼과, GET 방식 로그아웃 링크의 CSRF 토큰 / 관리 세션을 Redis로 옮기는 작업 / 필터 하나로 시작일~종료일 범위를 한 번에 지정하는 기능 — 이 작업들을 진행해줘. redis는 방법 2로 진행해줘. 405 문제는 현행 유지한다." | ① 관리 세션을 Redis 서버 세션으로(쿠키에는 세션 ID 만, 즉시 폐기). ② 로그인 이후 상태를 바꾸는 모든 관리 요청과 로그아웃에 CSRF 토큰, 로그아웃은 POST. ③ `LocalDateFilter` 에 기간 연산. ④ 405 `Allow` 불완전은 현행 유지(ADR-006) | Active |
| REQ-002 | 2026-10-19 | (감독자 추가 지시) "관리 화면(UserAdmin)에서 사용자를 직접 수정(is_active=False·is_superuser 해제·비밀번호 변경)하거나 삭제했을 때도 그 사용자의 관리 세션을 즉시 전부 폐기하라 … 변경 전후를 비교해 … 일반 수정은 폐기 안 함. 자기 자신을 강등하면 현재 세션도 끊긴다 — 그대로 둔다." | `UserAdmin` 훅이 변경 전후를 비교해 서비스 계층과 같은 폐기 함수를 부른다(ADR-005 → 시점·집합은 ADR-008) | Active |
| REQ-003 | 2026-10-19 | (감독자 정정 지시) "관리 화면 사용자 변경 시 폐기는 after_* 가 아니라 커밋 전 훅 on_model_change / on_model_delete 에서 하라 — Redis 폐기가 실패하면 예외로 커밋 자체를 막아 … 같은 조건에서 API refresh 토큰도 폐기하라 — 기존 refresh 저장소의 revoke_user 를 재사용 … API 경로와 관리 화면 경로가 같은 폐기 집합을 갖게 한다." | 폐기 시점을 커밋 전으로, 폐기 집합을 refresh family + 관리 세션으로 통일(ADR-008) | Active |

## 3. 설계 결정 (ADR)

### ADR-001 관리 세션 = Redis 서버 세션 (방법 2)
- 두 클래스(`app/core/security/admin_session.py`): `AdminSessionStore`(저장·조회·삭제·사용자별 전체 폐기 — 미들웨어·폐기 훅·스크립트·테스트가 함께 쓴다)와
  ASGI `RedisSessionMiddleware`(`scope["session"]` 에 dict 를 넣는다 — `request.session` 인터페이스 그대로라 `AdminAuthBackend` 의 login/authenticate/logout 은
  거의 그대로다). `AuthenticationBackend.middlewares` 의 Starlette `SessionMiddleware` 를 이것으로 바꿨다(부모 생성자는 부르지 않는다).
- 세션 ID `secrets.token_urlsafe(32)`. Redis 키 `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}` — 키가 새도 쿠키를 만들 수 없다.
  `SESSION_SECRET_KEY` 를 바꾸면 모든 관리 세션이 무효다. 값은 JSON `{"data", "user_id", "created_at"}`.
- 만료: 절대 `ADMIN_SESSION_MAX_AGE_SECONDS`(기본 28800, `ge=60`, 연장 불가 — 읽을 때 `created_at` 으로도 검사), 미사용 `ADMIN_SESSION_IDLE_SECONDS`
  (기본 1800, `ge=60`, idle ≤ max 아니면 기동 실패). TTL = `min(idle, 절대 만료까지 남은 초)` — 요청마다 다시 건다(내용이 바뀌면 SET, 아니면 EXPIRE).
- 쿠키: `admin_session`, `Path=/admin`, `SameSite=Strict`, HttpOnly, staging/production 에서 Secure, Max-Age = 절대 만료.
  쿠키의 ID 가 Redis 에 없으면(만료·폐기·위조) 빈 세션이고 쿠키를 지운다. 세션이 비면(로그아웃·DB 확인 실패) 키를 지우고 쿠키를 지운다.
- 세션 고정 방지: 로그인 성공 시 백엔드가 `RedisSessionMiddleware.rotate(request.scope)` 로 **명시적으로** 회전을 요청한다(scope 플래그) — 미들웨어가 응답
  직전에 새 ID 를 발급하고 이전 키를 지운다. 사용자 id 변화로 암묵 감지하는 것보다 읽기 쉽고 다른 경로가 우연히 회전시키지 않는다.
- 사용자별 인덱스 `admin:user_sessions:{user_id}`(SET, TTL = 절대 만료, 저장할 때마다 다시 건다). 로그인 시 추가, 로그아웃 시 제거, `revoke_user` 가 집합의 키와
  집합을 함께 지운다.
- Redis 클라이언트는 기존 방식대로 바깥 앱 상태에서 요청 때 꺼낸다(`lambda: default_admin_session_store(app.state.redis)`) — 레이트 리미터와 같다.
- Redis 장애는 fail-closed: 세션을 읽지 못하면 503(앱에 닿지 않는다), 클라이언트가 없으면(lifespan 밖) 같은 503, 응답 직전 저장 실패는 예외 그대로(500).
- `ADMIN_DISABLED=true` 에서는 미들웨어·저장소가 없다 — 사용자 기능의 provider(`get_admin_session_store`)는 관리 화면이 조립되지 않은 앱에서 `None` 을 준다.
- 익명 방문자도 로그인 화면을 열면 CSRF 토큰 때문에 세션이 생긴다(미사용 만료 30분 TTL) — R-003.

### ADR-002 로그인 이후 CSRF — 미들웨어 하나 + 원본을 확장한 base.html
- sqladmin 0.32 를 소스로 조사했다. 상태를 바꾸는 요청: 로그인(POST 폼), 생성·수정(`create.html`·`edit.html` 의 multipart POST 폼), 삭제·일괄 삭제(목록의
  모달 → `main.js` 의 `$.ajax` DELETE `?pks=`), 가져오기(모달 → `fetch` POST FormData, 이 저장소 뷰는 `can_import=False`), 로그아웃(`layout.html` 의 GET 링크).
  사용자 정의 `@action` 은 GET 라우트다(이 저장소는 쓰지 않는다 — R-001). 목록·상세·내보내기·ajax 조회·파일 내려받기는 GET 조회.
- 서버: `AdminCsrfMiddleware`(관리 하위 앱, 세션 미들웨어 안쪽). POST·PUT·PATCH·DELETE 전부(로그인 포함 — 로그인의 검사를 여기로 옮겨 **하나로** 합쳤다)에서
  헤더 `X-CSRF-Token` → 없으면 폼 필드 `csrf_token` 을 세션 토큰과 `hmac.compare_digest` 로 비교한다. 폼은 본문을 한 번 버퍼링해 파싱하고 같은 본문을
  `receive` 로 다시 흘려 준다(그냥 `request.form()` 을 부르면 다운스트림이 본문을 다시 못 읽는다). 헤더 통일은 고르지 않았다 — 일반 폼 제출(생성·수정·로그인,
  로그인 화면은 JS 없음)은 헤더를 실을 수 없다. 헤더가 있으면 본문을 읽지 않는다.
- 실패 응답(백엔드 `csrf_failed` 를 주입): 로그인은 로그인 화면 403(기존과 같다), 로그인한 세션은 관리 화면 `error.html` 403, 로그인 전 요청은 문구만 403
  (관리 메뉴의 모델 이름을 그리지 않는다). 레이트 리밋·자격 확인보다 먼저라 위조 요청이 카운터를 올리지 못한다(security-ops-hardening ADR-004 유지).
- 토큰: 세션에 하나(`AdminCsrf`, 예전 `AdminLoginCsrf`). 로그인 성공 시 세션을 비우고 새로 만든다(회전). 세션에 토큰이 없으면 거부.
- 클라이언트: `app/templates/admin/sqladmin/base.html` 이 `sqladmin_original/base.html`(sqladmin ChoiceLoader 의 원본 접두사)을 **확장**한다 — 복사하지 않는다.
  바꾼 블록은 둘: `head_meta`(+ `<meta name="csrf-token">`), `tail_js`(원본 스크립트 뒤 인라인 스크립트 — 같은 출처 POST 폼 제출에 hidden `csrf_token`,
  같은 출처 XHR·`fetch` 에 `X-CSRF-Token`, 로그아웃 링크 클릭을 토큰 실은 POST 폼 제출로). 원본 대조 테스트(`tests/core/test_admin_csrf.py`)가 원본 블록 이름·로그아웃
  링크·`main.js` 요청 방식·로그아웃 라우트가 바뀌면 실패한다.

### ADR-003 로그아웃은 POST 전용
- sqladmin 0.32 로그아웃 라우트는 GET 만 받는다(`Route("/logout", ..., methods=["GET"])`). `require_post_logout(admin)` 이 조립 때 같은 이름·같은 endpoint 의
  POST 전용 라우트로 바꾼다 — GET 은 405, POST 는 CSRF 미들웨어가 토큰을 본다. 라우트를 못 찾으면 `RuntimeError`(버전 변경 감지).
- 화면의 링크는 스크립트가 POST 폼으로 보낸다. JS 가 꺼져 있으면 405 다(관리 화면은 원래 jQuery 가 필요하다).

### ADR-004 기간 필터 — 한 필터, 값 `S~E`
- `LocalDateFilter` 에 연산 `between`("기간")을 더했다. sqladmin 은 필터 값을 하나만 넘기므로 값은 `YYYY-MM-DD~YYYY-MM-DD`. 양 끝 포함
  `S 0시 <= t < E+1 0시`(지역 날짜, `local_midnight_utc` 로 UTC — DST 날도 그날 오프셋). 한쪽만이면 열린 구간. 역순·형식 오류·구분자 없음·둘 다 빔 → 필터 미적용 + WARNING.
- 템플릿: 날짜 입력 두 개(이름 없음)와 hidden `<이름>` 하나 — 제출 직전 작은 스크립트가 연산이 기간이면 `S~E`, 아니면 시작일을 hidden 에 넣는다.
- 빠른 선택 "최근 7일·30일" 은 `between`(오늘 포함) 으로 표현한다.

### ADR-005 즉시 폐기 — 서비스·관리 화면·스크립트가 같은 `revoke_user` (관리 화면 부분은 ADR-008 로 대체)
- API: `UserService` 가 refresh `revoke_user` 하는 같은 지점(비활성화·강등·삭제)에서 주입받은 `AdminSessionStore.revoke_user` 를 부른다(`_revoke_sessions`).
  provider `get_admin_session_store` 는 관리 화면이 없는 앱에서 `None`.
- 관리 화면(REQ-002): `UserAdmin.on_model_change`(sqladmin 0.32 `_update_async` — 속성 적용 전에 부른다, 소스 확인)가 변경 전 객체와 폼 값을 비교해
  비활성화(`True→False`)·강등(`True→False`)·비밀번호 해시 변경일 때만 요청 상태에 표시하고, `after_model_change`(커밋 뒤)가 표시가 있을 때만 폐기한다.
  `after_model_delete` 는 항상 폐기한다. 이름·이메일 같은 일반 수정은 폐기하지 않는다. 저장소는 세션 미들웨어가 요청 scope 에 둔 것(`store_from_scope`).
  비밀번호는 관리 폼에서 빠져 있다(`form_excluded_columns`) — 비교는 폼이 바뀌어도 맞게 둔다.
- 자기 자신을 강등·비활성화하면 현재 세션도 지워진다 — 다음 요청에서 로그인 화면(의도, 문서화).
- 비밀번호 변경 경로: `scripts/create_superuser.py --set-password` — 커밋 뒤 설정의 Redis 에 붙어 그 사용자의 관리 세션을 지운다. 실패하면 종료 코드 1.
- Redis 오류는 삼키지 않는다(fail-closed 와 같은 정책): 관리 화면 수정·삭제는 커밋 뒤 폐기 실패가 sqladmin 오류 화면으로 드러나고(변경은 이미 커밋됨),
  매 요청 DB 확인(`authenticate`)이 이중 방어로 그 사용자를 막는다(R-005).

### ADR-006 405 `Allow` 헤더 불완전은 현행 유지 (사용자 결정, 2026-10-19)
- 같은 경로를 메서드별 라우트로 나눈 경우(예: GET 라우트와 POST 라우트가 따로) Starlette 는 처음 부분 일치한 라우트의 메서드로 405 `Allow` 를 만든다 — 실제로 허용되는
  메서드 전부가 아니다. 사용자 원문 "405 문제는 현행 유지한다". 기능·보안 영향이 없고, 고치려면 FastAPI·Starlette 라우터 내부 구조에 의존해야 한다.
  log-redaction-fixes ADR-003(핸들러가 `Allow` 를 버리지 않는다)은 그대로다.

### ADR-007 `itsdangerous` 직접 의존 제거
- 서명 쿠키 세션을 쓰지 않으므로 소비처가 없다(사용처 grep: 소스·스크립트 0, 테스트의 서명 쿠키 조작도 제거). `uv remove itsdangerous` 로 락을 갱신했다.
  sqladmin 은 `itsdangerous` 를 `auth` extra 로만 선언하고 우리는 그 extra 를 쓰지 않는다 — `AuthenticationBackend.__init__`(서명 세션)를 부르지 않는다.

## 4. 불가침 제약

- C-1: 마이그레이션 변경 없음.
- C-2: core 는 features 를 import 하지 않는다 — 폐기 훅은 features 가 core 저장소를 주입받는다.
- C-3: `ADMIN_DISABLED=true` 에서 sqladmin·세션 미들웨어·저장소가 없다.
- C-4: 메인 앱에는 세션 미들웨어가 없다(관리 하위 앱에만).
- C-5: 로그인 흐름(302·400·429·403·매 요청 DB 확인)은 그대로다.
- C-6: 덮어쓰는 sqladmin 템플릿은 최소(`base.html` 하나 추가, 원본 확장) — 원본 대조 테스트로 업그레이드 어긋남을 잡는다.

### ADR-008 폐기는 커밋 전, 집합은 refresh + 관리 세션 하나 (REQ-003, ADR-005 의 관리 화면 부분을 대체)
- `UserSessionRevoker`(`app/core/security/revocation.py`): `revoke(user_id)` = `RefreshTokenStore.revoke_user` + `AdminSessionStore.revoke_user`.
  폐기 로직은 각 저장소에 그대로 있고 이 클래스는 묶기만 한다(중복 구현 없음). API 는 provider `get_user_session_revoker` 로 주입받고
  (`UserService` 생성자는 `revoker` 하나), 관리 화면은 `revoker_from_scope(scope)` — 세션 미들웨어가 scope 에 둔 저장소의 Redis 로
  refresh 저장소(`get_refresh_token_store`)를 만든다. 두 경로의 폐기 집합이 같다.
- 관리 화면은 **커밋 전** 훅에서 폐기한다: `UserAdmin.on_model_change`(변경 전 객체와 폼 값 비교 — 비활성화·슈퍼유저 해제·비밀번호 해시 변경만,
  생성 제외)와 `on_model_delete`(항상). sqladmin 0.32 `_queries._update_async`·`_delete_async` 는 이 훅을 세션 안에서 속성 적용·삭제·커밋 **전에**
  부른다(소스 확인) — 폐기가 실패하면 예외가 커밋을 막는다. 수정은 sqladmin 이 400 오류 화면, 삭제는 목록 `error=` 로 드러나고 DB 는 그대로다
  (테스트 `test_revoke_failure_blocks_the_{edit,delete}_commit`). API 도 같은 순서다(서비스가 폐기한 뒤 핸들러가 커밋).
- 이유: 커밋 뒤 폐기는 Redis 장애 때 "DB 는 비활성화됐는데 세션은 살아 있는" 상태를 남긴다. 커밋 전 폐기의 반대 경우(폐기 뒤 커밋 실패)는
  세션만 지워진 상태 — 다시 로그인하면 되는 안전한 쪽이다. 관리 화면에서 강등해도 API refresh 가 남으면 API 쪽 권한 회수가 늦어진다 —
  같은 집합으로 맞춘다.
- 폐기와 커밋 사이 아주 짧은 틈에 그 사용자가 다시 로그인하면 새 세션이 생길 수 있다 — 커밋 뒤 매 요청 DB 확인(`authenticate`)이 막는다(R-005).
