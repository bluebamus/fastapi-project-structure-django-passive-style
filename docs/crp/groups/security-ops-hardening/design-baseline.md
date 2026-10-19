# Design Baseline — security-ops-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다. 다른 그룹의 ID 는
> `admin-login ADR-009` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

> 핵심 갈림길(보존 기본값·`.env` 설정, 토큰 15분 유지, 관리 세션 Redis 이전 보류)은 감독자가 사용자에게 확인했다 — REQ-001 해석 참고.

## 1. 목적 / 배경

감독자 확인 결과 엔진 생성 지점 어디에도 `hide_parameters` 가 없어, 고유 제약 위반 하나로 INSERT 의 값이 예외 문자열에 실려
traceback·`logger.exception` 출력으로 나갔다(로그 비밀값 가리기는 DSN·`password=`·Bearer·JWT 패턴만 가린다 — 이메일·해시는 가리지 않는다).
접속 로그에는 보존 기간이 없었고(service-hardening R-007·log-redaction-fixes R-001 의 재평가 조건), 관리 로그인 폼에는 CSRF 토큰이,
관리 목록에는 시각 컬럼 필터가 없었다(admin-login R-002·R-006).

## 2. 요구사항

| ID | 날짜 | 원문 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "보안결함 진행해줘. 접속 로그 보존 기간은 기본 1년으로 설정하고 이는 설정값으로 설정이 가능하도록 만들어줘. .env에 설정이 되도록 해줘. 15분 유지한다. ... 관리 화면 로그인폼에 csrf 토큰 작업을 진행해줘. 관리 화면 목록에 created_at 날자 필터 작업해줘." | ① DB 오류 로그의 바인드 값을 숨긴다(`hide_parameters`). ② `ACCESS_LOG_RETENTION_DAYS`(기본 365, 0=삭제 안 함, 음수 거부)를 `.env` 로 설정하고 매일 자동 삭제한다. ③ access 토큰 15분과 권한 회수 지연은 유지한다(ADR-006). ④ `/admin/login` 에 CSRF 토큰. ⑤ 관리 목록에 `created_at` 날짜 필터 | Active |

## 3. 설계 결정 (ADR)

### ADR-001 엔진 옵션 정본 `ENGINE_SAFETY_OPTIONS`
- `app/core/db/session.py` 에 `ENGINE_SAFETY_OPTIONS: Final = {"hide_parameters": True}` 하나를 두고 writer·reader·background 엔진과
  `migrations/env.py` 의 `engine_from_config` 가 `**ENGINE_SAFETY_OPTIONS` 로 펼친다. 옵션이 늘어도 한 곳만 고친다.
- 계약 테스트가 `app`·`migrations`·`scripts`·`config.py` 의 `create_async_engine`/`create_engine`/`engine_from_config` 호출을 AST 로 훑어
  펼침이 빠진 지점을 찾는다 — 새 엔진이 옵션을 빠뜨리면 테스트가 떨어진다. 테스트 코드의 엔진은 대상 밖이다.
- SQL 문은 남는다(진단용). 값 대신 `[SQL parameters hidden due to hide_parameters=True]` 가 붙는다.

### ADR-002 보존 삭제 — 리포지토리는 쿼리, 서비스는 정책
- `UserAccessLogRepository.delete_created_before(cutoff, limit)`: 오래된 순으로 id 를 `LIMIT` 개 고르고 그 id 로 `DELETE`. 커밋하지 않는다.
  MySQL 은 같은 테이블의 `IN (SELECT … LIMIT)` 을 거부하고(ER_NOT_SUPPORTED_YET), SQLite 기본 빌드는 `DELETE … LIMIT` 을 받지 않는다 —
  두 구문으로 나누면 두 방언에서 같은 쿼리다. `created_at` 인덱스(`ix_user_access_logs_created_at`)를 탄다.
- `UserAccessLogService.purge_expired(*, now=None, batch_size=5_000)`: 기준 `now - retention_days`, 배치마다 `commit()`, 지운 수가
  배치보다 작으면 멈춘다. `retention_days` 는 생성자 주입(provider `build_user_access_log_service` 가 설정에서 넣는다), 기준 시각은 인자 주입.
  `retention_days <= 0` 이면 DB 에 가지 않는다.
- 설정 `ACCESS_LOG_RETENTION_DAYS: int = Field(365, ge=0)` 는 접속 로그 설정 묶음(`MiddlewareSettings`)에 둔다.

### ADR-003 beat 일정은 기능의 `tasks.py` 가 등록한다
- `app/features/home/tasks.py` 가 `celery_app.add_periodic_task(crontab(hour=3, minute=30), purge_expired_access_logs.s(), name=...)` 로 등록한다.
  beat 는 `Beat.init_loader()` → `loader.init_worker()` 로 워커와 같은 `include`(INSTALLED_APPS 의 태스크 module)를 import 한 뒤
  일정을 읽으므로, 중앙 `app/celery/app.py` 는 기능을 import 하지 않는다(service-hardening ADR-012·C-14 의 자동 발견과 같은 방식).
  앱을 `INSTALLED_APPS` 에서 빼면 태스크와 일정이 함께 빠진다.
- 시각은 Celery `timezone`(= `TIME_ZONE`) 기준이다. beat 는 한 개만 띄운다(여러 개면 중복 실행 — 삭제는 멱등이라 해는 없다).

### ADR-004 로그인 CSRF — synchronizer token
- `AdminLoginCsrf`(`app/core/security/admin_auth.py`): 세션 키 `csrf_token`, `token_for(request)` 는 없으면 `secrets.token_urlsafe(32)` 를
  만들어 세션에 두고 돌려준다, `is_valid(request, submitted)` 는 `hmac.compare_digest` 로 비교(어느 쪽이든 없으면 거부).
- 로그인 GET 은 sqladmin 0.32 `Admin.login` 이 컨텍스트 없이 `sqladmin/login.html` 을 그린다(코드 확인). 그래서 백엔드의 `templates`
  setter 가 템플릿 전역 함수 `csrf_token` 을 건다 — 조립 지점(`create_admin`)이 `backend.templates = admin.templates` 를 넣는 순간 함께
  걸리므로 빠뜨릴 수 없다. 템플릿 렌더가 응답 시작 전이라 세션 변경이 쿠키로 나간다.
- `login()` 은 폼을 읽은 직후, **레이트 리밋보다 먼저** 토큰을 본다 — 위조 요청이 피해자의 시도 한도를 깎지 못한다. 실패는 403 으로 로그인
  화면("요청이 만료되었습니다. 다시 시도하세요.")을 다시 그린다. 세션은 그대로라 같은 토큰으로 재시도할 수 있다.
- 성공 시 기존 `session.clear()` 가 토큰도 지운다 — 다음 로그인 화면에서 새 토큰(회전).

### ADR-005 날짜 필터 `LocalDateFilter`
- 위치 `app/core/admin_filters.py`. sqladmin 을 import 하지 않고 연산 필터 프로토콜(`has_operator`·`template`·`title`·`parameter_name`·
  `get_operation_options_for_model`·`lookups`·`get_filtered_query`)을 이름으로 맞춘다(sqladmin 0.32 `ModelView.list` 의 분기 확인) —
  `ADMIN_DISABLED=true` 의 sqladmin 미로드(admin-login SEC-01)를 지킨다.
- 입력 `YYYY-MM-DD`(`strptime`, `TIME_ZONE` 의 날짜), 연산 `on`(같은 날 `[D, D+1)`)·`from`(이후 포함 `>= D`)·`before`(이전 미포함 `< D`).
  경계는 `TimezoneSettings.local_midnight_utc()` 로 aware UTC 순간이 되어 `UTCDateTime` 이 받는다. 형식 오류·모르는 연산은 필터 없이 원 쿼리 + WARNING.
- 템플릿 `sqladmin/filters/local_date_filter.html`: 쿼리 형식은 sqladmin 연산 필터와 같고, 입력은 `<input type="date">`, 빠른 선택(오늘·최근 7일·최근 30일)을 같은 클래스의 `quick_ranges()` 가 준다.
- `created_at` 이 있는 모든 ModelView(home·blog·reply·sns·user·catalog·reports)의 `column_filters` 끝에 단다.

### ADR-006 access 토큰 15분과 권한 회수 지연은 유지 (사용자 결정, 2026-10-19)
- 사용자 원문 "15분 유지한다". service-hardening R-002(access 즉시 폐기 불가)·R-014(강등 뒤 access 만료까지 이전 권한)를 **사용자 결정으로 수용**한다.
- 관리 세션의 Redis 이전(admin-login R-001)은 이번 범위 밖 — 사용자 결정 대기(R-003).

## 4. 불가침 제약

- C-1: 마이그레이션 변경 없음.
- C-2: 기존 로그인 흐름(302·400·429·세션 고정 방지·매 요청 DB 확인)의 동작은 토큰이 맞을 때 그대로다.
- C-3: `app/celery` 는 기능을 import 하지 않는다.
- C-4: `ADMIN_DISABLED=true` 에서 sqladmin 을 로드하지 않는다.
- C-5: 접속 로그 원문 저장(`session_id`·Referer·XFF)은 그대로 둔다(log-redaction-fixes ADR-002).
