# FastAPI Project Structure — Django Passive Style

Django 식 **수동 앱 설치**를 따르는 FastAPI 프로젝트 골격입니다. 설치 앱의 유일한 진실 공급원은
`config.INSTALLED_APPS` 이고, 설치된 앱의 Router·Models·Admin 결선은 App Registry 가 컨벤션대로 처리합니다.
URL 은 라우터 파일 계층이 소유합니다. 디렉터리를 만드는 것만으로는 앱이 설치되지 않습니다.

## 목차

- [주요 특징](#주요-특징)
- [기술 스택](#기술-스택)
- [프로젝트 구조](#프로젝트-구조)
- [빠른 시작](#빠른-시작)
- [앱 설치 — 목록에 한 줄](#앱-설치--목록에-한-줄)
- [ORM / Raw 데이터 접근](#orm--raw-데이터-접근)
- [API](#api)
- [운영 배포 체크리스트](#운영-배포-체크리스트)
- [문서 안내](#문서-안내)

## 주요 특징

- **수동 앱 설치**: `config.INSTALLED_APPS` 에 `AppConfig` 경로를 넣어야 route·모델·Admin·`ready()`·Celery 태스크가 켜진다. Django 의 3단계 app loading(config → models → ready)을 그대로 따른다.
- **계층 분리**: Router → Dependency → Service → Repository → DB. 기능마다 `app/features/<name>/` 에 모은다.
- **명시적 트랜잭션 경계**: 쓰기 핸들러 본문이 응답 전에 `await service.commit()`. 조회는 `get_read_only_db_session`, 쓰기는 `get_writer_db_session`.
- **ORM·Raw SQL 두 Repository 계열**과 나란히 비교할 수 있는 예제 기능 2개.
- **읽기 전용 세션은 쓰기를 거부한다**(항상): `get_read_only_db_session` 으로 받은 세션에서 ORM flush·Core DML·의도 태그가 없는 `text()` 는 실행 전에 `ReadOnlyRoutingError`. 차단은 `Session` 에 전역 등록된 리스너가 하므로 `DB_ROUTER_ENABLED` 설정과 무관하다.
- **Raw SQL 은 명시적 의도 태그 계약**: 구문에 `read_intent()`·`write_intent()` 를 붙여 읽기/쓰기를 선언한다(판정은 `statement_intent()`). SQL 문자열을 파싱하지 않으므로 **태그가 없는 `text()` 는 쓰기로 보고 읽기 전용 세션에서 거부**된다(fail-closed).
- **읽기/쓰기 라우팅**(선택): primary/replica 분리. 끄면 바인딩만 단일 엔진으로 가고 위 두 계약은 그대로다.
- **JWT 인증·인가**: OAuth2 password flow + access/refresh(회전·재사용 탐지·로그아웃), Argon2(pwdlib, 기존 bcrypt 해시는 로그인 시 이전), Redis 레이트 리밋.
  슈퍼유저/일반 2단계 권한과 작성자 소유권(`CurrentPrincipal`·`require_superuser`·`OwnershipPolicy`), 첫 관리자 생성 스크립트.
- **운영 기본기**: `/health`·`/ready` 분리, 불투명한 500(예외 헤더 `Allow`·`WWW-Authenticate` 등은 보존), SQL·비밀값 로그 차단(메시지·traceback·`stack_info` 의
  DSN 비밀번호·`password=`·Bearer·JWT 를 `***` 로 — uvicorn·Celery 핸들러 포함), DB 오류 메시지의 바인드 값 숨김(모든 엔진 `hide_parameters=True`),
  접속 로그 보존 기간(`ACCESS_LOG_RETENTION_DAYS`, 기본 1년 — Celery beat 가 매일 삭제), 종료 시 자원 정리 순서 보장.
- **Scalar** API 문서(`DEBUG=true`), **SQLAdmin** 관리 화면 — 활성 슈퍼유저 로그인(Bootstrap 로그인 화면, Redis 서버 세션 —
  쿠키에는 세션 ID 만, 로그아웃·강등·비활성화·삭제 시 즉시 폐기, 로그인·생성·수정·삭제·로그아웃(POST) 전부 CSRF 토큰, 매 요청 DB 재확인),
  목록의 `created_at` 날짜 필터(`TIME_ZONE` 기준 같은 날·이후·이전·기간).
  관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true` 로 마운트·링크까지 없앤다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Runtime | Python ≥ 3.13 (`.python-version` 3.14 — 로컬·CI 인터프리터), uv |
| Framework | FastAPI 0.141.x |
| ORM / Migration | SQLAlchemy 2.0 async, Alembic |
| Database | MySQL (aiomysql / 마이그레이션은 PyMySQL) |
| Validation / Settings | Pydantic v2, pydantic-settings |
| Redis | **필수, 7.0 이상** — 레이트 리밋이 `EXPIRE … NX`(7.0)를, refresh 회전이 GETDEL(6.2)을 쓴다. startup 연결·버전 검증, `get_redis` 주입, `/ready` 확인, `/admin` 관리 세션, Celery broker·result backend |
| Task Queue | Celery 5 |
| Auth | OAuth2 Password + PyJWT + pwdlib(Argon2) · 기존 bcrypt 해시 검증 · Redis(refresh 회전·레이트 리밋) |
| Admin / Docs | SQLAdmin(슈퍼유저 세션 로그인 — Redis 서버 세션(`RedisSessionMiddleware`, 쿠키에는 세션 ID 만) + CSRF 미들웨어, Bootstrap 5.3 로그인 화면) / Scalar |
| Quality | pytest, Ruff, mypy, Bandit, pip-audit, Playwright |

정확한 버전 범위는 `pyproject.toml` 과 `uv.lock` 이 기준입니다.

## 프로젝트 구조

```
fastapi-project-structure-django-passive-style/
├── main.py                      # app = create_app() + 로컬 uvicorn 실행만
├── config.py                    # INSTALLED_APPS + Pydantic Settings 12종
├── pyproject.toml / uv.lock     # 의존성·도구 설정 ([tool.uv] package = false)
├── alembic.ini
├── compose.test.yaml            # 테스트 전용 MySQL 8.4 (127.0.0.1:3309) · Redis (127.0.0.1:6380)
├── .env.example                 # 설정 키 전체 목록 (자동 fallback 아님)
│
├── app/
│   ├── features/                # 기능 앱 — INSTALLED_APPS 에 있어야 설치된다
│   │   ├── <name>/              # 앱 하나의 표준 구조
│   │   │   ├── __init__.py      # 가벼운 package marker (Router·Model import 금지)
│   │   │   ├── apps.py          # AppConfig subclass — 등록 대상
│   │   │   ├── api/routers/     # router.py(<name>_router) + v1/<name>.py
│   │   │   ├── models/          # SQLAlchemy 모델 (__init__.py 에서 재노출)
│   │   │   ├── schemas/         # Pydantic 요청·응답
│   │   │   ├── services/        # BaseService 상속
│   │   │   ├── repositories/    # BaseRepository 또는 RawRepositoryBase 상속
│   │   │   ├── dependencies/    # Service 구성 (커밋은 핸들러)
│   │   │   ├── admin.py         # ModelView + admin_views (모델이 있으면 필수)
│   │   │   ├── exceptions.py    # 기능 예외
│   │   │   └── tests/
│   │   ├── home/                # 접속 로그 조회·통계, ready() 에서 로그 sink 결선, tasks.py(Celery 예시)
│   │   ├── blog/ reply/ sns/ user/   # 기본 CRUD
│   │   ├── auth/                # 가입·로그인·토큰 (자체 모델 없음, user 의 User 사용)
│   │   ├── catalog/             # ORM 참조 예제 — BaseRepository 로 상품 CRUD
│   │   └── reports/             # Raw SQL 참조 예제 — RawRepositoryBase 로 일별 매출 집계
│   ├── core/                    # 프레임워크 인프라 (기능 구현을 import 하지 않음)
│   │   ├── bootstrap.py         # create_app(), lifespan, 예외 핸들러, /health·/ready·/docs
│   │   ├── resources.py         # Redis 검증·개발용 DDL·종료 순서
│   │   ├── apps/                # AppConfig·Apps registry + wiring.py (FastAPI·SQLAdmin adapter)
│   │   ├── db/                  # session.py(엔진·세션 Dependency) · router.py(읽기/쓰기) · errors.py
│   │   ├── models/              # Base + UUID·시각 Mixin
│   │   ├── repositories/        # ORM: CRUDBase·BaseRepository / Raw: RawCRUDBase·RawRepositoryBase
│   │   ├── services/            # BaseService
│   │   ├── middlewares/         # CORS · UserInfo · AccessLogSink · BackgroundTaskRunner
│   │   ├── security/            # PasswordHasher · TokenService · RefreshTokenStore · RateLimiter
│   │   ├── exception.py         # AppException 계층 + ErrorResponse
│   │   └── tags_metadata.py     # OpenAPI 태그 선언
│   ├── celery/                  # Celery 앱(include 는 INSTALLED_APPS 의 앱별 tasks.py) · run_async 브릿지 · worker 종료 정리
│   └── utils/                   # logs · pagination · validators
│
├── migrations/                  # Alembic — env.py 가 App Registry 로 설치 앱 모델만 수집
├── scripts/                     # new_app(골격 생성) · review_gate · bandit_gate · openapi_revert_check
├── tests/                       # 횡단 테스트: core/(apps/ 포함) · integration/(mysql) · browser/ · scripts/ · utils/
├── .github/workflows/ci.yml     # CI 게이트
├── docs/                        # 아래 "문서 안내"
└── logs/ media/ static/ poc/    # 런타임·예약 디렉터리 (추적하지 않음, logs/ 는 기동 시 자동 생성)
```

기능 테스트는 `app/features/<name>/tests/`, 여러 기능이나 core 계약을 보는 테스트는 최상위 `tests/` 에 둡니다. `pytest` 가 양쪽을 수집합니다.
의존 방향은 `features → core → utils` 입니다. `migrations/env.py` 와 `app/core/db/session.py` 는 디렉터리를 훑지 않고
`populate(INSTALLED_APPS, ...)` 로 App Registry 를 채워 **같은 모델 집합**을 봅니다.

## 빠른 시작

```bash
git clone https://github.com/bluebamus/fastapi-project-structure-django-passive-style.git
cd fastapi-project-structure-django-passive-style
```

이후 모든 명령은 저장소 루트에서 실행합니다.

### 0단계 — `.env` 준비

```bash
uv sync
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # 키마다 한 번씩, 세 번 실행
```

`.env` 에서 아래를 바꿉니다. 바꾸지 않으면 **개발 환경에서도 기동하지 않습니다**(설정 검증). 오류 메시지에
고칠 설정 이름이 나오므로 그대로 따라 고치면 됩니다.

| 설정 | 할 일 |
|---|---|
| `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` | 위 명령으로 만든 값을 **서로 다르게** 넣는다(32자 이상) |
| `MYSQL_PASSWORD` | 2단계에서 띄울 MySQL 의 비밀번호와 같은 값. 비워 두거나 예시 값이면 거부 |

`.env` 가 없으면 기동하지 않습니다. 파일 없이 환경 변수로 주입하는 경우(컨테이너)는 `ENV`·비밀 키 3종·
`MYSQL_HOST/USER/PASSWORD/DATABASE` 가 모두 있어야 합니다. 테스트(`ENV=test`, pytest 가 지정)는 이 검증을 하지 않습니다.

### 1단계 — Redis 만으로 HTTP 배선 확인

앱은 기동할 때 `REDIS_HOST`/`REDIS_PORT` 로 `ping()` 하고, 실패하면 시작하지 않습니다(`DEBUG` 와 무관). 이어서 `INFO server` 의
버전이 **7.0 미만이면 시작하지 않습니다**(INFO 를 막아 둔 관리형 Redis 는 WARNING 만 남기고 계속).
MySQL 없이 배선을 보려면 `DEBUG=false` 로 개발용 테이블 생성을 끕니다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine   # 7.0 이상 (EXPIRE NX)
DEBUG=false uv run uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"1.0.0"}   ← .env.example 의 VERSION
```

PowerShell:

```powershell
$env:DEBUG = "false"
uv run uvicorn main:app --port 8000
Remove-Item Env:DEBUG      # 끝난 뒤 개발 기본값으로 복원
```

| 이 상태에서 | 결과 | 이유 |
|---|---|---|
| `GET /health` | 200 | DB 를 보지 않는다 |
| `GET /ready` | 503 | writer DB 의 SELECT 1 이 실패한다(Redis 는 기동 조건이라 이미 응답한다) |
| 기능 API (`GET /api/v1/blog/posts` 등) | 500 | MySQL 이 필요하다 |
| `/docs`, `/openapi.json` | 404 | `DEBUG=false` 가 문서를 끈다 |

API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL 을 요구합니다 — 첫 실행에서 가장 헷갈리는 지점입니다.

### 2단계 — MySQL 추가

`DEBUG=true`(기본값)면 startup 에서 **설치 앱이 소유한 테이블**을 `create_all` 로 만듭니다. 그래서 설정 없이
`uvicorn main:app` 만 실행하면 MySQL 이 없어 startup 이 실패합니다(`(2003, "Can't connect to MySQL server ...")`).

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD='<.env 의 MYSQL_PASSWORD 와 같은 값>' -e MYSQL_DATABASE=fastapi_db mysql:8.4
uv run uvicorn main:app --reload --port 8000
```

기본값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_DATABASE=fastapi_db`)에 맞춘 로컬 전용 예시입니다.
빈 비밀번호는 개발 환경에서도 설정 검증이 거부하므로 비밀번호를 지정합니다.
MySQL 8.4 의 기본 인증은 의존성의 `cryptography` 가 처리합니다. 문자셋을 직접 만들 때는
`CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;` 를 씁니다.

- API 문서: <http://127.0.0.1:8000/docs> · 관리 화면: <http://127.0.0.1:8000/admin> (먼저 [첫 관리자 만들기](#첫-관리자-만들기)로
  슈퍼유저를 만들고 그 계정으로 로그인) · 헬스체크: `/health`, `/ready`
- 운영처럼 스키마를 Alembic 으로 관리하려면 `uv run alembic upgrade head` 후 `DEBUG=false` 로 실행합니다.

### 환경 변수 — 처음에 알아야 할 것

설정은 프로세스 환경변수 → 작업 디렉터리의 `.env` → 코드 기본값 순으로 읽습니다. `.env.example` 은 복사용 전체 목록이며 자동으로 읽히지 않습니다.

복사하는 방법은 0단계에 있습니다. 비밀번호·비밀키 예시값은 설정 검증이 **잡는** placeholder 입니다 — `ENV=test` 가 아니면
(개발 환경 포함) 그대로 둔 채로는 기동하지 못합니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `TRUSTED_PROXY_HOPS` | `0` | 앞단 신뢰 프록시 단 수. 프록시 뒤 배포면 반드시 설정 — [운영 배포 체크리스트](#운영-배포-체크리스트) |
| `ACCESS_LOG_RETENTION_DAYS` | `365` | 접속 로그 보존 일수. 매일 03:30(`TIME_ZONE`) Celery beat 가 이보다 오래된 행을 5,000행씩 지운다. `0` = 지우지 않음, 음수는 기동 실패. beat 를 띄워야 돈다 — [운영 배포 체크리스트](#운영-배포-체크리스트) |
| `DEBUG` | `true` | true = 개발 테이블 생성 + `/docs` 노출 + DEBUG 로그 / false = 모두 끔(스키마는 Alembic) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | startup `ping()`·버전 확인 대상. 연결 실패나 7.0 미만이면 서버가 뜨지 않는다 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / 빈 값 / `fastapi_db` | primary DB |
| `ADMIN_DISABLED` | `false` | false = `/admin` 마운트(**활성 슈퍼유저 로그인 필요**) / true = 관리 화면 자체가 없다(404, 응답 어디에도 경로·링크 없음, sqladmin 미로드). 예전 `ADMIN` 은 제거됐다 — 남아 있으면 기동 실패 |
| `ENV` | `development` | production/staging 에서 `DEBUG=true` 이거나 `LOG_LEVEL=DEBUG` 면 설정 로드가 실패하고, `/admin` 세션 쿠키에 `Secure` 가 붙는다(HTTPS 전용). 비밀키 검증은 test 외 모든 ENV 에 적용된다(아래) |
| `DB_ROUTER_ENABLED` | `false` | 읽기/쓰기 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` / `SESSION_SECRET_KEY` | `change-this-...` | test 외 모든 ENV(개발 포함)에서 placeholder(빈 값·`your-` 시작·`change-this` 포함)이거나 32자 미만이면 **기동이 실패**하고, access·refresh 키는 서로 달라야 한다. `SESSION_SECRET_KEY` 는 `/admin` 관리 세션 ID 를 Redis 키(`admin:sess:{HMAC}`)로 바꾸는 HMAC 키다(바꾸면 모든 관리 세션이 끊긴다). 생성: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |

> **`/admin` 은 활성 슈퍼유저만 들어갑니다.** 로그인 화면(Bootstrap)에서 `scripts/create_superuser.py` 로 만든 계정으로
> 로그인하면 `admin_session` 쿠키(path `/admin`·SameSite=Strict·HttpOnly)가 발급되고, 권한은 매 요청 DB 로 다시 확인합니다.
> 쿠키에는 무작위 세션 ID 만 있고 내용은 Redis 에 있습니다 — 30분 동안 쓰지 않거나 로그인 후 8시간이 지나면 다시 로그인해야 하고,
> 로그아웃하거나 API·관리 화면에서 그 사용자를 강등·비활성화·삭제하면(또는 `--set-password` 로 비밀번호를 바꾸면) 세션이 즉시 지워집니다.
> 로그인·생성·수정·삭제·로그아웃 같은 상태를 바꾸는 요청은 모두 CSRF 토큰을 싣고(화면 스크립트가 자동으로 붙인다), 없거나 다르면 403 입니다.
> 로그아웃은 POST 전용입니다(GET 은 405). 날짜 필터는 같은 날·이후·이전과 **기간**(시작일~종료일, 양 끝 포함)을 고를 수 있습니다.
> 세션은 **`/admin` 전용**이며 API 인증(JWT Bearer)과 섞이지 않습니다. 설계·흐름도·문제 해결은
> [관리 화면 인증 가이드](docs/guides/admin-auth-guide.html), 배포 체크리스트는 [아키텍처 §11](docs/guides/ARCHITECTURE.md#11-운영보안과-알려진-제한)에 있습니다.

선택 기능(Celery worker, replica 라우팅, Alembic)은 기본 실행에 필요 없습니다 — 필요할 때 [아키텍처 레퍼런스](docs/guides/ARCHITECTURE.md)를 봅니다.

### 세션·토큰 만료

세션·토큰의 만료는 아래 네 설정이 정한다 — 이 표가 정본이고, 다른 문서는 이 표를 가리킨다.

| 대상 | 설정 | 기본값 | 뜻 |
|---|---|---|---|
| `/admin` 관리 세션 — 절대 만료 | `ADMIN_SESSION_MAX_AGE_SECONDS` | `28800` (8시간) | 로그인 시각부터 세며 요청이 있어도 연장되지 않는다(쿠키 Max-Age 도 이 값). 60 미만은 기동 실패 |
| `/admin` 관리 세션 — 미사용 만료 | `ADMIN_SESSION_IDLE_SECONDS` | `1800` (30분) | 마지막 요청부터 다시 센다. 절대 만료를 넘지 않는다. 60 미만이거나 절대 만료보다 크면 기동 실패 |
| API 접근 토큰 (access) | `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` (분) | 발급 후 이 시간이 지나면 401. 즉시 폐기 목록은 없다 — 짧은 수명이 그 대신이다 |
| API refresh 토큰 | `REFRESH_TOKEN_EXPIRE_DAYS` | `7` (일) | refresh 수명이자 Redis 기록·폐기 표시 TTL |

JWT 검증 설정(`JWT_ISSUER`·`JWT_AUDIENCE`·`JWT_ALGORITHM`(HS256/384/512)·`JWT_LEEWAY_SECONDS`)과 레이트 리밋
`AUTH_LOGIN_*`·`AUTH_REGISTER_*` 는 `.env.example`·[아키텍처 §7](docs/guides/ARCHITECTURE.md#7-인증-jwt)에 있습니다.

### 테스트

```bash
uv run python -m pytest -m "not mysql and not browser"   # 외부 인프라 불필요 (SQLite·가짜 Redis)
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run python -m scripts.review_gate --fast              # 게이트 일괄 (MySQL 통합·브라우저 테스트 제외)
```

커버리지는 게이트·CI 가 항상 측정해 출력하지만 하한(`pyproject.toml` 의 `fail_under`)은 기본 **0** 입니다 — 처음에는 기능이 동작하는지가
먼저이고, 필요해지면 그 값 하나만 올립니다(올리는 법은 개발 가이드 §6.1).
`mysql`·`browser` 마커 테스트의 준비물과 CI 구성은 [개발 가이드 §6](docs/guides/DEVELOPMENT.md#6-테스트와-품질-게이트)에 있습니다.

### 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동·주소·인증 오류 | `REDIS_HOST` 등과 서버 확인. `DEBUG=false` 로 우회되지 않는다 |
| startup 에서 `Redis 6.x 는 지원하지 않는다` | 서버가 7.0 미만 — 레이트 리밋의 `EXPIRE NX` 가 문법 오류가 된다 | Redis 7.0 이상으로 올린다 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 가 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500, `/ready` 503 | DB 없음 | 2단계 진행 |
| 새 기능 route 가 안 보임 | `INSTALLED_APPS` 미등록 또는 `<name>_router` 이름 불일치 | 아래 절 참고. module 은 있는데 공개 이름이 없거나 import 가 깨지면 **기동이 실패**한다 |
| `.env 파일이 없고, 필수 설정이 …` | `.env` 가 없다 | 0단계. 컨테이너라면 메시지에 나온 환경 변수를 주입 |
| 기동 실패 (`ADMIN 은 ADMIN_DISABLED 로 바뀌었다`) | 환경 변수나 `.env` 에 예전 `ADMIN` 줄이 남아 있다 | `ADMIN` 이 false 였다면 `ADMIN_DISABLED=true` 로 바꾸고, true 였다면 그 줄을 지운다 |
| `/admin` 로그인 후 다시 로그인 화면 | staging/production 에서 HTTP 로 접속해 `Secure` 쿠키가 저장되지 않았다 / 계정이 슈퍼유저·활성이 아니다 | HTTPS 로 접속(프록시 TLS 종단 포함). 계정은 `scripts.create_superuser` 로 승격 |
| `/admin` 로그인이 429 | ip 또는 ip+사용자명 시도 한도(`AUTH_LOGIN_*`) 초과. 프록시 뒤에서 `TRUSTED_PROXY_HOPS=0` 이면 모두가 한도를 나눠 쓴다 | `Retry-After` 초만큼 기다린다. 프록시 뒤라면 `TRUSTED_PROXY_HOPS` 설정 |
| 기동 실패 (`설정이 안전하지 않습니다`) | 비밀키·비밀번호가 placeholder·빈 값·32자 미만이거나 access·refresh 키가 같다(개발 환경 포함) / 배포 환경의 `DEBUG=true` 또는 `LOG_LEVEL=DEBUG` | 메시지에 나온 설정을 고친다 — 비밀키는 `secrets.token_urlsafe(48)` 로 만든 서로 다른 값으로 교체, 인증 없는 Redis 면 `REDIS_PASSWORD` 는 비운다, debug 모드는 끈다 |

## 앱 설치 — 목록에 한 줄

```powershell
uv run python -m scripts.new_app orders --with-models --with-admin
```

생성기는 `app/features/orders/` 골격과 `apps.py` 를 만들고 **설정 파일은 건드리지 않습니다.** 출력된 한 줄을 목록 끝에 붙입니다.

```python
# config.py
INSTALLED_APPS: list[str] = [
    # 기존 설치 앱 항목은 유지
    "app.features.orders.apps.OrdersConfig",
]
```

이 줄을 넣기 전까지 앱은 존재하지만 설치되지 않은 상태입니다. 넣으면 Router·Models·Admin·`ready()` 가 함께 켜지고,
`main.py`·`migrations/env.py` 는 손대지 않습니다. 기능 root `__init__.py` 는 Router·Model 을 재노출하지 않는 package marker 이고,
결선 규칙은 `apps.py` 의 `AppConfig` 가 선언합니다(`app/features/home/apps.py` 참고).
태그 선언·migration·체크리스트까지의 전체 절차는 [개발 가이드 §2](docs/guides/DEVELOPMENT.md#2-새-기능-추가)에 있습니다.

## ORM / Raw 데이터 접근

데이터 접근은 두 계열이고 갈라지는 곳은 **Repository 하나뿐**입니다. 두 Base 는 상속 관계가 없습니다.

| | ORM (기본값) | Raw SQL |
|---|---|---|
| 상속할 Base | `BaseRepository` | `RawRepositoryBase` |
| 참조 예제 | `app/features/catalog/repositories/product_repository.py` | `app/features/reports/repositories/sales_report_repository.py` |

Raw 는 집계·리포트, 필요한 컬럼만 읽는 대량 조회, DB 고유 기능처럼 ORM 이 못 하는 일에만 씁니다.
SQL 은 `text()` 모듈 상수, 외부 값은 named bind parameter, `query_name` 은 코드 상수여야 합니다.
읽기/쓰기 의도는 `RawRepositoryBase` 가 메서드마다 붙입니다(`fetch_*` 는 읽기, `execute`·`for_update=True` 는 쓰기) — 세션에 `text()` 를 직접 던지면 태그가 없어 읽기 전용 세션에서 거부됩니다.
판단 기준과 규칙 전문은 [개발 가이드 — ORM 과 Raw 선택](docs/guides/DEVELOPMENT.md#orm-raw)에 있습니다.

## API

`DEBUG=true` 일 때 Scalar 문서 `/docs` 와 `/openapi.json` 이 열립니다(Swagger UI·ReDoc 은 끔). `/admin` 은 `ADMIN_DISABLED=false`(기본)일 때만
있고 슈퍼유저 로그인이 필요합니다 — OpenAPI 에는 나오지 않습니다(SQLAdmin 하위 앱).

`app.openapi()` 실측 **23 경로 / 38 오퍼레이션**입니다. 공개 경로 목록은 `tests/test_route_inventory.py` 가 고정하므로 route 를 바꾸면 이 표도 함께 고칩니다.

| 앱 | 메서드 · 경로 | 인증 |
|---|---|---|
| — | GET `/health` (liveness) · GET `/ready` (writer DB·Redis readiness, 하나라도 실패 시 503) | — |
| home | GET `/api/v1/home/access-logs` · `/recent` · `/by-ip/{ip_address}` · `/by-user/{user_id}` · `/stats` | 슈퍼유저 |
| blog | GET·POST `/api/v1/blog/posts` · GET·PATCH·DELETE `/api/v1/blog/posts/{post_id}` | GET 공개 · POST 로그인 · PATCH·DELETE 작성자/슈퍼유저 |
| reply | GET·POST `/api/v1/reply/replies` · GET·PATCH·DELETE `/api/v1/reply/replies/{reply_id}` | GET 공개 · POST 로그인 · PATCH·DELETE 작성자/슈퍼유저 |
| sns | GET·POST `/api/v1/sns/posts` · GET·PATCH·DELETE `/api/v1/sns/posts/{post_id}` | GET 공개 · POST 로그인 · PATCH·DELETE 작성자/슈퍼유저 |
| user | GET·POST `/api/v1/user/users` · GET·PATCH·DELETE `/api/v1/user/users/{user_id}` | 목록·생성·삭제 슈퍼유저 · 단건 GET·PATCH 본인/슈퍼유저 |
| auth | POST `/api/v1/auth/register` (JSON) · POST `/api/v1/auth/login` (**form**) · POST `/api/v1/auth/refresh` (JSON) · POST `/api/v1/auth/logout` (JSON, 204) · GET `/api/v1/auth/me` | `/me` 만 로그인. register·login 은 레이트 리밋(429 + `Retry-After`) |
| catalog | GET·POST `/api/v1/catalog/products` · GET·PATCH·DELETE `/api/v1/catalog/products/{product_id}` | GET 공개 · 쓰기 슈퍼유저 |
| reports | GET `/api/v1/reports/daily-sales?start_date=&end_date=` (종료일 포함, 최대 366일, 1970-01-01~9998-12-31) | 슈퍼유저 |

```bash
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'   # 비밀번호 8자 이상
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer","expires_in":900}
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'
curl -X POST localhost:8000/api/v1/auth/refresh -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'        # 새 쌍 발급, 쓴 refresh 는 소비된다
curl -X POST localhost:8000/api/v1/auth/logout -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'        # 204, 그 family 의 refresh 가 모두 무효
```

### 인증 흐름

login 이 access(기본 15분)·refresh(7일) 쌍을 준다. access 가 만료되면 refresh 로 새 쌍을 받고, 쓴 refresh 는
버린다 — **한 번 쓴 refresh 를 다시 보내면 재사용(탈취 신호)으로 보고 그 로그인 세션(family) 전체를 폐기**한다(401). logout 은
family 를 폐기한다. access 는 즉시 폐기되지 않으므로 수명을 짧게 둔다. 로그인은 ip 당·ip+username 당, 회원가입은 ip 당 시도 수를
Redis 고정 창으로 세고 넘으면 429 + `Retry-After` 다. 기존 bcrypt 해시 사용자는 로그인할 때 Argon2 로 다시 저장된다.

토큰 정책·오류 응답 형식·접속 로그 수집 항목은 [아키텍처 레퍼런스](docs/guides/ARCHITECTURE.md)를 봅니다.

### 권한 표

권한은 **슈퍼유저/일반 2단계**입니다. 인가는 core 의 `get_current_principal`(access 토큰만 검증, DB 조회 없음)·`require_superuser`·
`OwnershipPolicy` 로 겁니다 — 세부는 [아키텍처 §7.1](docs/guides/ARCHITECTURE.md#71-인가--주체소유권슈퍼유저), 붙이는 법은
[개발 가이드 §4.5](docs/guides/DEVELOPMENT.md#45-인증인가-붙이기).

**접근 수준은 뷰마다 선언합니다.** 경로 데코레이터의 `dependencies=[...]` 에 `Public`(공개 조회)·`PublicWrite`(인증 없는 쓰기)·
`LoginRequired`·`SuperuserRequired`(`app/core/security/access.py`) 중 하나를 적거나, 핸들러 인자로 `principal: CurrentPrincipal`·
`SuperuserPrincipal` 을 받습니다. **선언이 없는 라우트가 하나라도 있으면 서버가 기동하지 않습니다**(`AccessPolicyGuard` — 기본 거부).
쓰기 메서드에 `Public` 을 적거나 수준을 둘 이상 적어도 기동이 멈춥니다. 아래 예시 정책은 `tests/test_authorization_policy.py` 가 가드의 판정과 대조해 고정합니다.

```python
@router.get("/posts", dependencies=[Public])                  # 공개 조회
@router.post("/auth/login", dependencies=[PublicWrite])       # 인증 없는 쓰기는 명시적으로 연다
@router.get("/users", dependencies=[SuperuserRequired])       # 슈퍼유저
async def create_post(payload: PostCreate, principal: CurrentPrincipal): ...   # 인자 = 로그인
```

| 등급 | 오퍼레이션 |
|---|---|
| 공개 | `/health`·`/ready`, auth register·login·refresh·logout, blog·sns·reply·catalog 의 목록·단건 GET |
| 로그인 | auth `/me`, blog·sns·reply 생성(작성자는 서버가 로그인 사용자로 채운다 — 본문의 `author` 는 받지 않는다) |
| 작성자 또는 슈퍼유저 | blog·sns·reply 수정·삭제 (작성자 기록이 없는 기존 행은 슈퍼유저만) |
| 본인 또는 슈퍼유저 | user 단건 GET·PATCH (`is_active`·`is_superuser` 변경은 슈퍼유저만) |
| 슈퍼유저 | user 목록·생성(비밀번호 필수)·삭제, catalog 생성·수정·삭제, reports, home 접속 로그 5종 |

토큰이 없으면 401(`WWW-Authenticate: Bearer`), 토큰이 만료·위조됐거나 refresh 토큰을 access 로 보내면 401, 권한이 없으면 403 입니다.
사용자를 비활성화·강등·삭제하면(또는 `--set-password` 로 비밀번호를 바꾸면) 그 사용자의 refresh 토큰과 `/admin` 관리 세션이 모두 폐기됩니다(이미 받은 access 는 만료까지 유효).

```bash
curl -X POST localhost:8000/api/v1/blog/posts -H 'Authorization: Bearer <access_token>' \
  -H 'Content-Type: application/json' -d '{"title":"첫 글","content":"본문"}'   # author·author_id 는 서버가 채운다
```

### 첫 관리자 만들기

Django 의 `createsuperuser` 와 같은 역할입니다. 마이그레이션은 기존 사용자를 아무도 관리자로 만들지 않습니다.

```bash
uv run python -m scripts.create_superuser --username admin --email admin@example.com          # 비밀번호를 두 번 묻는다
printf '%s\n' "$PW" | uv run python -m scripts.create_superuser --username admin --email admin@example.com --password-stdin
uv run python -m scripts.create_superuser --username alice                                     # 기존 사용자 승격(비밀번호 유지)
uv run python -m scripts.create_superuser --username alice --set-password                      # 승격 + 비밀번호 변경
```

비밀번호는 명령행 인자로 받지 않습니다(셸 기록에 남는다). 종료 코드는 0 성공 · 1 입력 거부 · 2 인자 오류입니다.
만든 뒤 로그인하면 access 토큰의 `su` claim 이 true 가 됩니다. **같은 계정이 `/admin` 로그인 계정입니다** — 활성 슈퍼유저만
들어갈 수 있고, API·관리 화면에서 강등·비활성화하면 그 사용자의 관리 세션이 즉시 지워져 다음 요청부터 로그인 화면으로 돌아갑니다(refresh 토큰도 함께 지운다).

## 운영 배포 체크리스트

전체 표는 [아키텍처 §11.1](docs/guides/ARCHITECTURE.md#111-배포-체크리스트--사람이-확인할-것)입니다. 배포 전에 해야 할 일:

- **`TRUSTED_PROXY_HOPS`** — 프록시 뒤 배포면 앞단 프록시 단 수로 설정합니다. 0 으로 두면 모든 클라이언트가 프록시 IP 하나로 보여
  접속 로그와 로그인 레이트 리밋(API·`/admin`, 로그인 20회/60초·가입 5회/시간)이 **전체 사용자를 한 사람으로 취급**합니다 — 한 사람이
  한도를 채우면 전원이 429 를 받습니다. 실제보다 크게 잡으면 위조된 `X-Forwarded-For` 를 믿어 IP 를 위조할 수 있습니다(service-hardening R-013).
- **KST→UTC 시각 마이그레이션** — 리비전 `e5a7c2d9f310` 은 기존 MySQL 시각 값이 `+09:00` 으로 저장됐다고 가정합니다. 다른 시간대로
  운영했다면 적용 전에 리비전의 `LEGACY_OFFSET` 상수를 그 오프셋으로 바꿉니다. **적용 전에 백업합니다.**
- **첫 관리자** — `scripts/create_superuser.py` 로 만듭니다(대화형 또는 `--password-stdin`). 이 계정이 `/admin` 로그인 계정입니다.
  일반 사용자 토큰으로 관리 API(예: `/api/v1/user/users`)가 403 인지도 확인합니다.
- **`/admin` 은 슈퍼유저 로그인이 필요합니다** — 관리 세션은 Redis 에 있습니다. Redis 를 쓸 수 없으면 관리 화면은 503 입니다(fail-closed).
  `SESSION_SECRET_KEY` 는 세션 ID 를 Redis 키로 바꾸는 HMAC 키라 바꾸면 모든 관리 세션이 끊깁니다(다시 로그인하면 된다).
  staging/production 은 쿠키에 `Secure` 가 붙으므로 HTTPS 로 접속해야 로그인이 유지됩니다.
- **관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true`** — 마운트·링크·세션 미들웨어가 모두 사라집니다. 예전 `ADMIN` 줄이 `.env`·환경에
  남아 있으면 기동이 멈추니 `ADMIN_DISABLED` 로 옮깁니다.
- `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY` 는 서로 다른 무작위 값이어야 합니다 — 키를 아는 사람은 `su=true` 토큰을 만들 수 있습니다.
- 마이그레이션 `uv run alembic upgrade head` 로 `users.is_superuser`·게시물 `author_id` 를 추가합니다(리비전 `a3c9e8f1b274`).
- **Redis 7.0 이상** — 레이트 리밋이 `EXPIRE … NX`(7.0)를 씁니다. 7.0 미만이면 기동이 멈추고, `INFO` 를 막아 둔 관리형 Redis 는 확인을
  건너뛰고 WARNING 만 남기므로 버전을 직접 확인합니다.
- **접속 로그 보존** — `ACCESS_LOG_RETENTION_DAYS`(기본 365일, `0` = 삭제 안 함)를 개인정보 정책에 맞춥니다. 삭제는 Celery **beat** 가
  매일 03:30(`TIME_ZONE`)에 `home.purge_expired_access_logs` 를 워커로 보내야 돈다 — worker 와 함께 beat 를 **하나만** 띄웁니다:
  `uv run celery -A app.celery.app worker --loglevel=info` · `uv run celery -A app.celery.app beat --loglevel=info`.
- **업그레이드 노트 — 지운 설정** — 메일(SMTP_*)·업로드(UPLOAD_*)·SESSION_EXPIRE_SECONDS 는 읽는 코드가 없어 지웠습니다.
  `.env`·환경 변수에 남은 이 줄들은 **지워도 되고, 남아도 무시됩니다**(기동은 멈추지 않는다 — 예전 `ADMIN` 과 다르다).
  세션·토큰 만료는 [세션·토큰 만료](#세션토큰-만료) 표의 네 설정이 정합니다.

## 문서 안내

**문서 색인은 이 표 한 곳에만 둡니다.** 같은 내용을 두 곳에 쓰지 않습니다 — HTML 안내서는 흐름을 따라 읽는
요약이고, 표·수치의 정본은 Markdown 가이드입니다(HTML 은 브라우저로 엽니다).

| 문서 | 역할 | 언제 보나 |
|---|---|---|
| `README.md` (이 문서) | 개요 · 빠른 시작 · 문서 안내 | 처음 받았을 때, 실행 방법·API 목록을 볼 때 |
| [docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md) | 구조 · 런타임 동작 레퍼런스 | App Registry·수명주기·설정·세션/트랜잭션·Repository API·운영 체크리스트·변경 이력을 확인할 때 |
| [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md) | 기능 개발 가이드 | 새 기능·API·테이블을 만들 때, ORM/Raw 를 고를 때, 테스트·CI 게이트를 돌릴 때 |
| [docs/guides/server-lifecycle-guide.html](docs/guides/server-lifecycle-guide.html) | 서버 수명주기 안내서 (설정 → 기동 → 요청 → 종료 추적) | 기동 실패·로그 레벨·요청별 세션·종료 순서를 코드 흐름대로 따라갈 때 |
| [docs/guides/feature-development-guide.html](docs/guides/feature-development-guide.html) | 신규 뷰·테이블 개발 안내서 | catalog(ORM)·reports(Raw) 예제를 따라 새 뷰·테이블을 연결할 때 |
| [docs/guides/admin-auth-guide.html](docs/guides/admin-auth-guide.html) | 관리 화면(`/admin`) 인증 가이드 — 세션 범위·구성도·로그인 시퀀스·쿠키·위협 모델·운영 | 관리 화면 로그인을 이해·운영·확장할 때, `ADMIN_DISABLED` 를 정할 때 |
| [docs/specs/orm-raw-repository/requirements.md](docs/specs/orm-raw-repository/requirements.md) | 고정 기준선 — ORM/Raw 착수 요구명세 | 코드 주석의 `RAW-REP-*`·`NFR-0xx`·`DOC-*` 원문을 찾을 때 |
| [docs/specs/orm-raw-repository/development-plan.md](docs/specs/orm-raw-repository/development-plan.md) | 고정 기준선 — 착수 개발계획 | 코드 주석의 `development-plan §N`·`Phase N` 인용을 따라갈 때 |
| [docs/specs/orm-raw-repository/workflow-guide.md](docs/specs/orm-raw-repository/workflow-guide.md) | 고정 기준선 — 착수 워크플로 지침 | 착수 당시의 작업·검수 절차를 확인할 때 |
| `docs/crp/groups/` | 검수 이력 (append-only) | 코드 주석의 `ADR-*`·`C-*`·`F-*`·`L-*` 인용과 설계 결정의 근거를 찾을 때 |

명세 3종은 **2026-08 착수 시점의 고정 기준선**이라 내용을 고치지 않습니다. 현재 사용법은 위 가이드가 기준입니다.
코드와 문서가 어긋나면 코드가 정답이며, 확인한 뒤 문서를 고칩니다. 문서 정합성(경로·심볼·환경변수·링크·앵커, 문서가 인용한
비밀값, HTML 의 `data-source`·코드 경로 포함)은 `tests/test_docs_consistency.py`·`tests/test_docs_references.py`·`tests/test_docs_secret_examples.py` 가 검사합니다.

## 참고 자료

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) · [Pydantic v2](https://docs.pydantic.dev/latest/) · [Django — Applications](https://docs.djangoproject.com/en/6.0/ref/applications/)

## 라이선스

MIT License
