# 아키텍처

이 문서는 현재 코드가 어떻게 조립되고 요청을 처리하는지 설명한다. 근거가 되는 파일 경로를 함께 적는다.

## 1. 디렉터리 구조

```
main.py                     app = create_app() + 로컬 uvicorn 실행
config.py                   INSTALLED_APPS + Pydantic Settings + 기동 시 설정 검증
alembic.ini, migrations/    Alembic (env.py, versions/0001_baseline_schema.py)
app/
  core/
    bootstrap.py            create_app() — 조립 순서의 정본
    resources.py            lifespan 자원(테이블 생성·Redis·엔진) 생성·해제
    apps/                   App Registry (config.py·registry.py) + FastAPI/SQLAdmin 결선(wiring.py)
    db/                     엔진·세션(session.py), 읽기/쓰기 라우터(router.py), DB 예외 변환(errors.py)
    models/                 Base·공통 Mixin(models_base.py), UTCDateTime(types.py)
    repositories/           BaseRepository(ORM) · RawRepositoryBase(Raw SQL)
    services/               BaseService
    security/               비밀번호·토큰·refresh 저장·레이트 리밋·접근 수준·관리 화면 인증
    middlewares/            CORS, 접속 로그(UserInfoMiddleware), 클라이언트 IP, 백그라운드 태스크
    exception.py            AppException 계층 + ErrorResponse
    redis.py                Redis 주입·ping·버전 확인
  features/<name>/          기능 앱 (home·blog·reply·sns·user·auth·catalog·reports)
  celery/                   중앙 Celery 앱, 워커 자원 수명, async 브리지
  utils/logs/               로깅 구성·필터·포매터·회전 핸들러·비밀값 가리기
  templates/admin/sqladmin/ 관리 화면 템플릿 덮어쓰기(로그인·base·날짜 필터)
scripts/                    new_app · create_superuser · review_gate · bandit_gate · openapi_revert_check
tests/                      기능을 가로지르는 테스트와 공용 헬퍼
```

기능 앱 하나의 표준 구조:

```
app/features/<name>/
  __init__.py               가벼운 package marker (Router·Model 을 import 하지 않는다)
  apps.py                   AppConfig subclass — INSTALLED_APPS 에 이 클래스 경로를 적는다
  api/routers/router.py     <name>_router — v1 하위 라우터를 prefix 와 함께 묶는다
  api/routers/v1/<name>.py  path operation (View)
  dependencies/             Service 조립(세션 선택)
  services/ repositories/ schemas/ models/
  admin.py                  admin_views (모델이 있는 앱)
  tasks.py                  Celery 태스크 (선택)
  exceptions.py             기능 예외
  tests/
```

## 2. App Registry — 수동 설치

`config.INSTALLED_APPS` 가 설치 앱의 유일한 목록이고 **순서가 계약**이다. 항목은 config class 경로
(`app.features.blog.apps.BlogConfig`) 또는 package 경로다. 환경 변수로 덮어쓰지 않는다.

`Apps.populate()`(`app/core/apps/registry.py`)는 Django 와 같은 3단계로 진행한다.

1. 각 항목의 `AppConfig` 를 만든다(root package import, 기본 config 선택).
2. 각 앱의 `models` module 을 import 한다 → `Base.metadata` 가 채워진다.
3. 각 앱의 `ready()` 를 부른다(예: home 이 접속 로그 sink 를 등록).

각 단계는 전체 앱에 대해 끝난 뒤 다음으로 넘어간다. 같은 목록으로 다시 부르면 아무 일도 하지 않고,
다른 목록이나 재진입은 거부한다. 선택 module(`models`·`admin`·`tasks`·router)이 **없는 것**은 정상이고,
있는데 그 안에서 import 가 실패하면 기동이 실패한다.

결선(`app/core/apps/wiring.py`)은 `AppConfig` 의 컨벤션을 따른다.

| 대상 | 기본값 | 결과 |
|---|---|---|
| `router_module` / `router_attribute` | `api.routers.router` / `<label>_router` | `router_prefix`(기본 `/api`) 아래에 include. 같은 method+path 가 겹치면 기동 실패 |
| `models_module` | `models` | metadata 수집 — 런타임 `create_all` 과 Alembic 이 같은 집합을 본다 |
| `admin_module` | `admin` 의 `admin_views` | SQLAdmin 뷰 등록(`INSTALLED_APPS` 순서) |
| `tasks_module` | `tasks` | Celery 워커 `include` |

목록에서 앱을 빼면 디렉터리가 남아 있어도 라우트·테이블·관리 뷰·태스크가 모두 빠진다.

## 3. 조립과 수명주기

`create_app()`(`app/core/bootstrap.py`)의 순서:

1. 설치 앱 목록 결정(`INSTALLED_APPS` 또는 인자)
2. registry population
3. FastAPI 생성(+ lifespan). `openapi_url` 은 `DEBUG=true` 일 때만 연다
4. CORS · 접속 로그 미들웨어 · 예외 핸들러
5. registry 기반 Router 설치
6. `/health`·`/ready`·`/docs`(Scalar, `DEBUG=true` 일 때)
7. `ADMIN_DISABLED=false` 면 SQLAdmin 을 `/admin` 에 마운트 — sqladmin 은 이때만 import 된다
8. `AccessPolicyGuard().verify(app)` — 접근 수준을 선언하지 않은 API 라우트가 있으면 기동을 멈춘다

lifespan 의 자원은 `manage_application_resources`(`app/core/resources.py`) 한 곳이 만든다.

- 기동: `DEBUG=true` 이고 설치 앱이 소유한 테이블이 있으면 그 테이블만 `create_all`(없으면 DB 에 접속하지 않는다),
  Redis 연결 → `ping` → 버전 확인(7.0 미만이면 기동 실패, `INFO` 가 막힌 서버는 경고 후 계속).
- 종료(역순 보장): 진행 중인 백그라운드 태스크 drain → Redis 닫기 → writer·reader·background 엔진 dispose.
  각 단계는 시간 예산 안에서 돌고, 하나가 실패해도 나머지는 실행한다. 기동 중간 실패도 같은 정리 경로를 탄다.

## 4. 계층

```
Router(View) ── Depends ──> Service ──> Repository ──> AsyncSession ──> DB
```

- **View**: 요청 검증, 접근 수준 선언, 응답 DTO(`response_model`). 쓰기 핸들러는 응답 DTO 를 만든 **뒤**
  `await service.commit()` 을 한 번 부른다 — 커밋 주체는 View 본문 하나다.
- **Dependency**(`dependencies/`): Service 를 세션과 묶는다. 조회용은 `get_read_only_db_session`,
  쓰기용은 `get_writer_db_session` 을 받는다.
- **Service**(`BaseService` 상속): 업무 규칙. 커밋하지 않는다(`commit()` 위임만 제공).
- **Repository**: DB 접근. 커밋하지 않는다.
  - `BaseRepository`(`app/core/repositories/repository_base.py`): ORM. 공개 메서드는
    `create`·`get_by_id`·`get_one`·`get_all`·`count`·`exists`·`update`·`delete` 8개.
    `get_all` 기본 정렬은 `created_at DESC, PK DESC`. 값이 그대로인 `update` 도 행을 돌려준다.
  - `RawRepositoryBase`(`app/core/repositories/raw_repository_base.py`): Raw SQL. `fetch_one`·`fetch_all`·`fetch_scalar`·`execute`.
    `query_name` 은 코드 상수(`feature.use_case` 형식)여야 하고, SQL 은 bind parameter 로만 값을 받는다.
    결과는 `RowMapping` 이며 Service 가 Pydantic DTO 로 검증한다.
- `catalog`(ORM)와 `reports`(Raw)는 디렉터리·Dependency·Service 구조가 같고 Repository 만 다르다.

PATCH 스키마는 `PatchSchema`(`app/core/schemas.py`)를 상속한다 — NOT NULL 컬럼에 명시적 `null` 을 보내면 422 다.

## 5. DB 세션과 읽기/쓰기 라우팅

엔진(`app/core/db/session.py`):

| 엔진 | 용도 |
|---|---|
| `engine` (writer) | 요청 처리, primary |
| `read_engines` | replica — `DB_REPLICATION_ENABLED=true` 일 때만 |
| `background_engine` | 접속 로그 저장·Celery 등 요청 밖 작업. 풀을 분리해 API 풀을 고갈시키지 않는다 |

모든 엔진은 `hide_parameters=True` 다(오류 메시지에 bind 값이 실리지 않는다). 풀 크기는 `DB_POOL_*`·`DB_BACKGROUND_*` 이고,
`DB_MAX_SERVER_CONNECTIONS` 를 주면 프로세스 수(`DB_WORKER_PROCESSES`)를 곱한 총 연결 수가 넘을 때 기동을 막는다.

세션 의존성:

| 의존성 | 동작 |
|---|---|
| `get_read_only_db_session` | 쓰기 금지 표시. ORM flush·Core DML·잠금 읽기·의도 태그 없는 `text()` 는 실행 전에 `ReadOnlyRoutingError`. 라우터와 무관하게 항상 동작 |
| `get_writer_db_session` | 첫 구문부터 primary 고정 |
| `get_routed_db_session` | 구문 성격으로 엔진 자동 선택 — 특수 경로 전용 |
| `get_background_session` / `background_session()` | background 엔진 |

라우터(`app/core/db/router.py`, `DB_ROUTER_ENABLED=true`):

- ORM flush·Core DML·`with_for_update()` → writer, 그 밖의 SELECT → reader(세션마다 라운드로빈, 세션 안에서는 고정).
- 쓰기가 일어난 세션의 이후 SELECT 는 writer 로 고정(`DB_READ_STICKY_AFTER_WRITE`, 기본 켜짐).
- Raw `text()` 는 SQL 을 파싱하지 않는다. `read_intent()`·`write_intent()` 로 의도를 붙이고, 태그가 없으면 쓰기로 본다.
- 읽기 전용 세션이 replica 에 **연결하지 못하면** primary 로 한 번 재시도한다. 쿼리 오류는 재시도하지 않는다.
- 복제만 켜고 라우터를 끄거나, 복제를 켰는데 replica 호스트가 없으면 기동 실패. replica 자격증명이 없으면 primary 값을 쓴다.

DB 예외는 `convert_db_error`(`app/core/db/errors.py`)가 응답용 예외로 바꾼다 — 중복 키 409, 클라이언트가 고칠 수 있는
무결성 위반(NOT NULL 등) 422, 그 밖은 500. 원본 예외는 `__cause__` 로 잇지 않고 로그에는 타입·드라이버 코드만 남긴다.

시각은 `UTCDateTime`(`app/core/models/types.py`)으로 저장한다 — aware 값을 naive UTC 로 저장하고(MySQL `DATETIME(6)`),
읽을 때 UTC 를 붙인다. naive 값은 저장을 거부한다. 지역 시각(`TIME_ZONE`, 기본 `Asia/Seoul`)은 리포트의 영업일 경계와
관리 화면 날짜 필터에서만 계산한다.

## 6. 인증·권한

API 인증은 OAuth2 password flow + JWT 다(`app/features/auth`, 부품은 `app/core/security/`).

- `PasswordHasher`: Argon2(pwdlib). 이전 bcrypt 해시는 검증 후 Argon2 로 다시 저장한다. 사용자가 없어도 같은 검증 비용을 치른다.
- `TokenService`: claims `sub, type, iat, nbf, exp, jti, iss, aud` + access 는 `username`·`su`(슈퍼유저 bool), refresh 는 `fam`.
  설정 알고리즘(HS256/384/512) 하나만 받고, type 이 다르거나 서명·만료·발급자·대상이 어긋나면 401.
- `RefreshTokenStore`(Redis): refresh 는 1회만 소비한다. 이미 쓴 토큰을 다시 내면 그 family 전체를 폐기한다(재사용 탐지).
  로그아웃은 자기 family 만 폐기한다.
- `RateLimiter`(Redis 고정 창): 로그인은 사용자명별(`AUTH_LOGIN_MAX_ATTEMPTS`)·IP별(`AUTH_LOGIN_IP_MAX_ATTEMPTS`),
  가입은 IP별(`AUTH_REGISTER_*`). 초과 시 429 + `Retry-After`. 성공한 로그인은 사용자명 카운터를 지운다.
- 사용자 비활성화·강등·삭제·비밀번호 변경은 그 사용자의 refresh family 와 관리 세션을 폐기한다
  (`app/core/security/revocation.py` 가 무엇을 지울지 한 곳에서 판정). 폐기는 커밋 전이라 Redis 실패 시 변경도 저장되지 않는다.
- 모든 401 응답에는 `WWW-Authenticate: Bearer` 가 붙는다.

권한(`app/core/security/access.py`): 모든 API 뷰는 접근 수준을 **하나** 선언한다.

| 선언 | 의미 |
|---|---|
| `dependencies=[Public]` | 인증 없는 조회(GET 등) |
| `dependencies=[PublicWrite]` | 인증 없는 쓰기(로그인·가입) |
| `dependencies=[LoginRequired]` 또는 인자 `CurrentPrincipal` | 로그인 필요 |
| `dependencies=[SuperuserRequired]` 또는 인자 `SuperuserPrincipal` | 슈퍼유저 |

선언이 없거나 둘 이상이면 `AccessPolicyGuard` 가 기동을 멈춘다(기본 거부). `Principal` 은 토큰 claims 만으로 만들고,
작성자 소유권은 `OwnershipPolicy` 가 판정한다 — blog·reply·sns 는 작성자 또는 슈퍼유저만 수정·삭제하고(작성자 없는 행은 슈퍼유저만),
작성자는 요청 본문이 아니라 인증 주체로 채운다. 존재 확인(404)이 권한 확인(403)보다 먼저다. 예외로 user 단건 조회·수정은 권한을 먼저 본다
(없는 ID 도 403 — 다른 사용자 ID 의 존재 여부가 드러나지 않게). `/auth/me` 는 사용자 조회를 primary 에 고정한다.

## 7. 관리 화면 (`/admin`)

SQLAdmin 을 `create_admin`(`app/core/apps/wiring.py`)이 마운트한다. `ADMIN_DISABLED=true` 면 마운트·sqladmin import·세션 미들웨어가
모두 없고 `/admin` 은 404 다. 예전 설정 이름 `ADMIN` 이 환경이나 `.env` 에 남아 있으면 기동을 멈춘다.

- 로그인: `AdminAuthBackend`(`app/core/security/admin_auth.py`) — 활성 슈퍼유저만. 매 요청 DB 로 권한을 다시 확인한다.
  사용자 DB 판정은 auth 앱이 `ready()` 에서 등록한 `UserAdminCredentials` 가 한다(core 는 user 모델을 모른다).
  로그인 레이트 리밋은 API 로그인과 같은 한도, 다른 키를 쓴다.
- 세션: `RedisSessionMiddleware`(`app/core/security/admin_session.py`) — 쿠키 `admin_session` 에는 무작위 ID 만 있고,
  Redis 키는 `SESSION_SECRET_KEY` 로 만든 HMAC 이다. 유휴 만료 `ADMIN_SESSION_IDLE_SECONDS`(기본 30분), 절대 만료
  `ADMIN_SESSION_MAX_AGE_SECONDS`(기본 8시간). 로그인하면 세션 ID 를 새로 발급한다. Redis 장애는 503(fail-closed).
  쿠키는 path `/admin`·HttpOnly·SameSite=Strict, staging/production 에서는 Secure. 이 세션은 API 인증에 쓰이지 않는다.
- CSRF: `AdminCsrfMiddleware` — 로그인·생성·수정·삭제·로그아웃 등 상태를 바꾸는 요청은 세션 토큰과 대조하고 다르면 403.
  덮어쓴 `sqladmin/base.html` 이 폼과 `fetch`·XHR 에 토큰을 붙인다. 폼 본문은 상한을 넘으면 413. 로그아웃은 POST 전용이다.
- 뷰: 앱별 `admin.py` 의 `admin_views`. 비밀번호 컬럼은 목록·상세·폼·내보내기에서 제외하고, 접속 로그는 읽기 전용이다.
  `created_at` 이 있는 목록에는 `LocalDateFilter`(`app/core/admin_filters.py`, `TIME_ZONE` 기준 같은 날·이후·이전·기간)가 붙는다.

## 8. 미들웨어와 오류 응답

사용자 미들웨어(바깥 → 안):

1. `answer_unhandled_exception` — 처리기가 없는 예외를 500 으로 끝낸다(기록 1회, 연결 유지). `DEBUG=true` 면 다시 던진다.
2. `UserInfoMiddleware` — 접속 로그. `ACCESS_LOG_ENABLED=true` 이고 제외 경로·확장자가 아닌 요청을 응답 뒤에 background
   세션으로 저장한다(동시 저장 수 상한, 넘으면 버린다). 민감 query 값(`ACCESS_LOG_SENSITIVE_QUERY_KEYS`)은 가리고,
   처리되지 않은 예외로 끝난 요청도 500 으로 기록한다. 클라이언트 IP 는 `ClientIPResolver` 가 `TRUSTED_PROXY_HOPS` 만큼
   `X-Forwarded-For` 의 오른쪽에서 고른다(0 이면 소켓 주소). 보존 기간은 `ACCESS_LOG_RETENTION_DAYS`(기본 365, 0 = 삭제 안 함).
3. CORS(`CustomCORSMiddleware`, `CORS_*`) — `*` origin 과 credentials 동시 허용은 설정 단계에서 거부.

`/admin` 서브 앱에는 별도로 `RedisSessionMiddleware`·`AdminCsrfMiddleware` 가 붙는다(메인 앱에는 세션 미들웨어가 없다).

오류 응답은 모두 `ErrorResponse`(`error_code`·`message`·`detail`) 형식이다(`app/core/exception.py`, 핸들러는 `bootstrap.py`).

| 예외 | 응답 |
|---|---|
| `AppException` 계열 | 예외의 상태 코드·코드, `headers` 유지(예: 429 `Retry-After`). 4xx 는 WARNING, 5xx 는 ERROR 로 기록 |
| `RequestValidationError` | 422 `VALIDATION_ERROR`, detail 은 `field`·`message`·`type`. OpenAPI 의 422 도 같은 모델로 광고한다 |
| Starlette `HTTPException` | `HTTP_<status>`, 헤더 유지(405 `Allow` 등) |
| Redis 연결·타임아웃 오류 | 503 `SERVICE_UNAVAILABLE` |
| 그 밖 | 500, `DEBUG` 에서도 detail 은 비운다. SQLAlchemy 예외는 traceback 없이 타입·코드만 기록 |

`/health` 는 DB 를 보지 않는다. `/ready` 는 writer DB `SELECT 1` 과 Redis `ping` 을 함께 보고 어느 하나라도 실패하면 503(원인은 싣지 않는다).

## 9. 로깅

`app/utils/logs/` — `configure_logging()` 이 `build_dictconfig()` 결과를 root 에 한 번 적용한다. 웹(`python main.py`·`uvicorn main:app`)과
Celery 워커·beat 가 같은 구성을 쓴다.

- 헤더: `[시각 TZ] LEVEL [app=<앱>] [module:class:func:line] message`. 앱 이름은 소스 경로에서, 외부 라이브러리는 로거 이름에서 정한다.
  `get_logger(__name__)` 또는 `LoggerMixin` 의 `self.log` 를 쓴다.
- 출력: 콘솔(`LOG_CONSOLE_ENABLED`) + staging/production 에서 파일(`LOG_FILE_ENABLED`, `LOG_DIR`). 파일은 프로세스별
  (`app.log`/`error.log`, `celery.log`/`celery-error.log`, `celery-beat.log`/`celery-beat-error.log`)이고 자정(UTC)·크기(`LOG_MAX_SIZE_MB`)로
  회전, `LOG_RETENTION_DAYS` 보다 오래된 파일은 지운다. 개발 환경은 콘솔만, 로컬 시각 + 밀리초.
- 레벨: `LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·`LOG_FILE_LEVEL`, 앱별은 `LOG_APP_LEVELS=blog=DEBUG,sqlalchemy=WARNING` (로거를 등록하지 않고 헤더로 거른다).
- 보안: `SqlNoiseFilter` 가 SQLAlchemy·드라이버의 DEBUG/INFO SQL 로그를 막는다(`LOG_SQL_ECHO_ENABLED=true` 로 개발에서만 연다).
  `SecretRedactor` 가 메시지·인자·traceback·`stack_info` 의 DSN 자격증명, `password=`·`token=` 류 값, Bearer·JWT, 그리고
  `config.LOG_REDACTED_SETTINGS` 에 있는 설정값 원문을 `***` 로 바꾼다 — uvicorn·Celery 핸들러 포함.
- 여러 프로세스가 같은 파일을 회전시키면 안전하지 않다. `uvicorn --workers` 2 이상이나 Celery prefork 는 `LOG_FILE_ENABLED=false` 로 두고 stdout 을 수집한다.

## 10. Celery

`app/celery/app.py` 의 `celery_app` 이 broker·result backend 로 Redis 를 쓴다. 워커 `include` 는 `INSTALLED_APPS` 로 채운 registry 의
`tasks` module 목록이다 — 이 패키지는 기능을 직접 import 하지 않는다. 내부 시각은 UTC, 일정(crontab)은 `TIME_ZONE` 으로 해석한다.

- 태스크 예: `home.aggregate_access_stats`, `home.purge_expired_access_logs`(매일 03:30, `ACCESS_LOG_RETENTION_DAYS` 보다 오래된 접속 로그를 배치로 삭제).
- 워커는 FastAPI lifespan 을 타지 않는다. `run_async`(`app/celery/task.py`)가 워커 프로세스당 이벤트 루프 하나를 재사용하고,
  워커 종료 시 `app/celery/lifecycle.py` 가 그 루프와 엔진을 정리한다(dispose 가 실패해도 루프는 닫는다).
- 세션은 `background_session()` 을 쓴다.

## 11. 설정

`config.py` 의 Settings 클래스들이 프로세스 환경 변수 → 작업 디렉터리의 `.env` → 코드 기본값 순으로 읽는다. 다른 모듈은 환경 변수를
직접 읽지 않는다. import 시점에 다음을 검증하고 실패하면 기동하지 않는다(`ENV=test` 는 제외).

- `.env` 가 없으면 `ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE` 가 환경 변수로 모두 있어야 한다.
- 비밀 키 3종·`MYSQL_PASSWORD`·(값이 있으면) `REDIS_PASSWORD` 가 placeholder(빈 값, `your-` 시작, `change-this` 포함)면 거부.
  비밀 키는 32자 이상, access 와 refresh 키는 서로 달라야 한다.
- staging/production 에서 `DEBUG=true`·`LOG_LEVEL=DEBUG`·`LOG_SQL_ECHO_ENABLED=true` 거부.
- 지운 설정 키는 무시한다(`extra="ignore"`). 단 뜻이 뒤집힌 `ADMIN` 은 기동을 멈춘다.
