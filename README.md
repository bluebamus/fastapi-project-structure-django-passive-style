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
- [문서 안내](#문서-안내)

## 주요 특징

- **수동 앱 설치**: `config.INSTALLED_APPS` 에 `AppConfig` 경로를 넣어야 route·모델·Admin·`ready()` 가 켜진다. Django 의 3단계 app loading(config → models → ready)을 그대로 따른다.
- **계층 분리**: Router → Dependency → Service → Repository → DB. 기능마다 `app/features/<name>/` 에 모은다.
- **명시적 트랜잭션 경계**: 쓰기 핸들러 본문이 응답 전에 `await service.commit()`. 조회는 `get_read_only_db_session`, 쓰기는 `get_writer_db_session`.
- **ORM·Raw SQL 두 Repository 계열**과 나란히 비교할 수 있는 예제 기능 2개.
- **읽기/쓰기 라우팅**(선택): primary/replica 분리, Raw SQL 은 명시적 read/write 의도로 fail-closed.
- **JWT 인증**: OAuth2 password flow + access/refresh, bcrypt.
- **운영 기본기**: `/health`·`/ready` 분리, 불투명한 500, SQL·비밀값 로그 차단, 종료 시 자원 정리 순서 보장.
- **Scalar** API 문서(`DEBUG=true`), **SQLAdmin** 관리 화면(`ADMIN=true`, 인증 없음).

## 기술 스택

| 구분 | 기술 |
|---|---|
| Runtime | Python ≥ 3.12 (`.python-version` 3.14), uv |
| Framework | FastAPI 0.141.x |
| ORM / Migration | SQLAlchemy 2.0 async, Alembic |
| Database | MySQL (aiomysql / 마이그레이션은 PyMySQL) |
| Validation / Settings | Pydantic v2, pydantic-settings |
| Redis | startup 연결 검증 + Celery broker·result backend |
| Task Queue | Celery 5 |
| Auth | OAuth2 Password + PyJWT + bcrypt |
| Admin / Docs | SQLAdmin / Scalar |
| Quality | pytest, Ruff, mypy, Bandit, Playwright |

정확한 버전 범위는 `pyproject.toml` 과 `uv.lock` 이 기준입니다.

## 프로젝트 구조

```
fastapi-project-structure-django-passive-style/
├── main.py                      # app = create_app() + 로컬 uvicorn 실행만
├── config.py                    # INSTALLED_APPS + Pydantic Settings 12종
├── pyproject.toml / uv.lock     # 의존성·도구 설정 ([tool.uv] package = false)
├── alembic.ini
├── compose.test.yaml            # 테스트 전용 MySQL 8.4 (127.0.0.1:3309)
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
│   │   ├── home/                # 접속 로그 조회·통계, ready() 에서 로그 sink 결선
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
│   │   ├── exception.py         # AppException 계층 + ErrorResponse
│   │   └── tags_metadata.py     # OpenAPI 태그 선언
│   ├── celery/                  # 중앙 Celery 앱 · tasks.py · run_async 브릿지 · worker 종료 정리
│   └── utils/                   # logs · authenticator(JWT·bcrypt) · pagination · validators
│
├── migrations/                  # Alembic — env.py 가 App Registry 로 설치 앱 모델만 수집
├── scripts/                     # new_app(골격 생성) · review_gate · bandit_gate · openapi_revert_check
├── tests/                       # 횡단 테스트: core/(apps/ 포함) · integration/(mysql) · browser/ · scripts/ · utils/
├── .github/workflows/ci.yml     # CI 게이트
├── docs/                        # 아래 "문서 안내"
└── logs/ media/ static/ poc/    # 런타임·예약 디렉터리 (.gitkeep 만 추적)
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

### 1단계 — Redis 만으로 HTTP 배선 확인

앱은 기동할 때 `REDIS_HOST`/`REDIS_PORT` 로 `ping()` 하고, 실패하면 시작하지 않습니다(`DEBUG` 와 무관).
MySQL 없이 배선을 보려면 `DEBUG=false` 로 개발용 테이블 생성을 끕니다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
uv sync
DEBUG=false uv run uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"0.1.0"}   ← .env 가 없을 때의 VERSION 기본값
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
| `GET /ready` | 503 | writer DB 의 SELECT 1 이 실패한다 |
| 기능 API (`GET /api/v1/blog/posts` 등) | 500 | MySQL 이 필요하다 |
| `/docs`, `/openapi.json` | 404 | `DEBUG=false` 가 문서를 끈다 |

API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL 을 요구합니다 — 첫 실행에서 가장 헷갈리는 지점입니다.

### 2단계 — MySQL 추가

`DEBUG=true`(기본값)면 startup 에서 **설치 앱이 소유한 테이블**을 `create_all` 로 만듭니다. 그래서 설정 없이
`uvicorn main:app` 만 실행하면 MySQL 이 없어 startup 이 실패합니다(`(2003, "Can't connect to MySQL server ...")`).

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -e MYSQL_DATABASE=fastapi_db mysql:8.4
uv run uvicorn main:app --reload --port 8000
```

기본값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, 빈 `MYSQL_PASSWORD`, `MYSQL_DATABASE=fastapi_db`)에 맞춘 로컬 전용 예시입니다.
MySQL 8.4 의 기본 인증은 의존성의 `cryptography` 가 처리합니다. 문자셋을 직접 만들 때는
`CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;` 를 씁니다.

- API 문서: <http://127.0.0.1:8000/docs> · 관리 화면: <http://127.0.0.1:8000/admin> · 헬스체크: `/health`, `/ready`
- 운영처럼 스키마를 Alembic 으로 관리하려면 `uv run alembic upgrade head` 후 `DEBUG=false` 로 실행합니다.

### 환경 변수 — 처음에 알아야 할 것

설정은 프로세스 환경변수 → 작업 디렉터리의 `.env` → 코드 기본값 순으로 읽습니다. `.env.example` 은 복사용 전체 목록이며 자동으로 읽히지 않습니다.

```bash
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
```

복사하면 `MYSQL_PASSWORD=your_password`·`VERSION=1.0.0` 등 예시값이 들어가므로 환경에 맞게 고칩니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DEBUG` | `true` | true = 개발 테이블 생성 + `/docs` 노출 + DEBUG 로그 / false = 모두 끔(스키마는 Alembic) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | startup `ping()` 대상. 연결 실패 시 서버가 뜨지 않는다 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / 빈 값 / `fastapi_db` | primary DB |
| `ADMIN` | `true` | `/admin` 이 **인증 없이** 열린다(개발 편의 결정) |
| `ENV` | `development` | production/staging 에서 `ADMIN=true` 면 `ADMIN_UNAUTHENTICATED_ACK=true` 없이는 설정 로드가 실패한다 |
| `DB_ROUTER_ENABLED` | `false` | 읽기/쓰기 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 써도 되지만 **배포 전 반드시 교체** |

> **`/admin` 에는 인증이 없습니다.** `ADMIN=true` 면 앱에 도달할 수 있는 누구나 사용자·게시글·접속 로그 등을 조회·수정·삭제하고
> 내보낼 수 있습니다(비밀번호 해시만 제외). 운영·스테이징은 `ADMIN=false` 를 명시하세요. 배포 체크리스트는
> [아키텍처 §11](docs/guides/ARCHITECTURE.md#11-운영보안과-알려진-제한)에 있습니다.

선택 기능(Celery worker, replica 라우팅, Alembic)은 기본 실행에 필요 없습니다 — 필요할 때 [아키텍처 레퍼런스](docs/guides/ARCHITECTURE.md)를 봅니다.

### 테스트

```bash
uv run python -m pytest -m "not mysql and not browser"   # 외부 인프라 불필요 (SQLite·가짜 Redis)
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run python -m scripts.review_gate --fast              # 게이트 일괄 (MySQL 통합·브라우저 테스트 제외)
```

`mysql`·`browser` 마커 테스트의 준비물과 CI 구성은 [개발 가이드 §6](docs/guides/DEVELOPMENT.md#6-테스트와-품질-게이트)에 있습니다.

### 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동·주소·인증 오류 | `REDIS_HOST` 등과 서버 확인. `DEBUG=false` 로 우회되지 않는다 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 가 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500, `/ready` 503 | DB 없음 | 2단계 진행 |
| 새 기능 route 가 안 보임 | `INSTALLED_APPS` 미등록 또는 `<name>_router` 이름 불일치 | 아래 절 참고. module 은 있는데 공개 이름이 없거나 import 가 깨지면 **기동이 실패**한다 |
| production 설정에서 기동 실패 | `ENV` 가 production/staging 인데 `ADMIN=true` | `ADMIN=false` 또는 프록시 차단 후 `ADMIN_UNAUTHENTICATED_ACK=true` |

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
판단 기준과 규칙 전문은 [개발 가이드 — ORM 과 Raw 선택](docs/guides/DEVELOPMENT.md#orm-raw)에 있습니다.

## API

`DEBUG=true` 일 때 Scalar 문서 `/docs` 와 `/openapi.json` 이 열립니다(Swagger UI·ReDoc 은 끔). `/admin` 은 `ADMIN=true` 일 때만 있습니다.

`app.openapi()` 실측 **22 경로 / 37 오퍼레이션**입니다. 공개 경로 목록은 `tests/test_route_inventory.py` 가 고정하므로 route 를 바꾸면 이 표도 함께 고칩니다.

| 앱 | 메서드 · 경로 | 인증 |
|---|---|---|
| — | GET `/health` (liveness) · GET `/ready` (writer DB readiness, 실패 시 503) | — |
| home | GET `/api/v1/home/access-logs` · `/recent` · `/by-ip/{ip_address}` · `/by-user/{user_id}` · `/stats` | 없음 |
| blog | GET·POST `/api/v1/blog/posts` · GET·PATCH·DELETE `/api/v1/blog/posts/{post_id}` | 없음 |
| reply | GET·POST `/api/v1/reply/replies` · GET·PATCH·DELETE `/api/v1/reply/replies/{reply_id}` | 없음 |
| sns | GET·POST `/api/v1/sns/posts` · GET·PATCH·DELETE `/api/v1/sns/posts/{post_id}` | 없음 |
| user | GET·POST `/api/v1/user/users` · GET·PATCH·DELETE `/api/v1/user/users/{user_id}` | 없음 |
| auth | POST `/api/v1/auth/register` (JSON) · POST `/api/v1/auth/login` (**form**) · POST `/api/v1/auth/refresh` (JSON) · GET `/api/v1/auth/me` | `/me` 만 Bearer |
| catalog | GET·POST `/api/v1/catalog/products` · GET·PATCH·DELETE `/api/v1/catalog/products/{product_id}` | 없음 |
| reports | GET `/api/v1/reports/daily-sales?start_date=&end_date=` (종료일 포함, 최대 366일) | 없음 |

```bash
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'   # 비밀번호 8자 이상
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer"}
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'
curl -X POST localhost:8000/api/v1/auth/refresh -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'        # access·refresh 둘 다 새로 발급
```

토큰 정책·오류 응답 형식·접속 로그 수집 항목은 [아키텍처 레퍼런스](docs/guides/ARCHITECTURE.md)를 봅니다.

## 문서 안내

**문서 색인은 이 표 한 곳에만 둡니다.** 같은 내용을 두 곳에 쓰지 않습니다 — HTML 안내서 두 편은 흐름을 따라 읽는
요약이고, 표·수치의 정본은 Markdown 가이드입니다(HTML 은 브라우저로 엽니다).

| 문서 | 역할 | 언제 보나 |
|---|---|---|
| `README.md` (이 문서) | 개요 · 빠른 시작 · 문서 안내 | 처음 받았을 때, 실행 방법·API 목록을 볼 때 |
| [docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md) | 구조 · 런타임 동작 레퍼런스 | App Registry·수명주기·설정·세션/트랜잭션·Repository API·운영 체크리스트·변경 이력을 확인할 때 |
| [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md) | 기능 개발 가이드 | 새 기능·API·테이블을 만들 때, ORM/Raw 를 고를 때, 테스트·CI 게이트를 돌릴 때 |
| [docs/guides/server-lifecycle-guide.html](docs/guides/server-lifecycle-guide.html) | 서버 수명주기 안내서 (설정 → 기동 → 요청 → 종료 추적) | 기동 실패·로그 레벨·요청별 세션·종료 순서를 코드 흐름대로 따라갈 때 |
| [docs/guides/feature-development-guide.html](docs/guides/feature-development-guide.html) | 신규 뷰·테이블 개발 안내서 | catalog(ORM)·reports(Raw) 예제를 따라 새 뷰·테이블을 연결할 때 |
| [docs/specs/orm-raw-repository/requirements.md](docs/specs/orm-raw-repository/requirements.md) | 고정 기준선 — ORM/Raw 착수 요구명세 | 코드 주석의 `RAW-REP-*`·`NFR-0xx`·`DOC-*` 원문을 찾을 때 |
| [docs/specs/orm-raw-repository/development-plan.md](docs/specs/orm-raw-repository/development-plan.md) | 고정 기준선 — 착수 개발계획 | 코드 주석의 `development-plan §N`·`Phase N` 인용을 따라갈 때 |
| [docs/specs/orm-raw-repository/workflow-guide.md](docs/specs/orm-raw-repository/workflow-guide.md) | 고정 기준선 — 착수 워크플로 지침 | 착수 당시의 작업·검수 절차를 확인할 때 |
| `docs/crp/groups/` | 검수 이력 (append-only) | 코드 주석의 `ADR-*`·`C-*`·`F-*`·`L-*` 인용과 설계 결정의 근거를 찾을 때 |

명세 3종은 **2026-08 착수 시점의 고정 기준선**이라 내용을 고치지 않습니다. 현재 사용법은 위 가이드가 기준입니다.
코드와 문서가 어긋나면 코드가 정답이며, 확인한 뒤 문서를 고칩니다. 문서 정합성(경로·심볼·환경변수·링크·앵커, HTML 의
`data-source`·코드 경로 포함)은 `tests/test_docs_consistency.py`·`tests/test_docs_references.py` 가 검사합니다.

## 참고 자료

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) · [Pydantic v2](https://docs.pydantic.dev/latest/) · [Django — Applications](https://docs.djangoproject.com/en/6.0/ref/applications/)

## 라이선스

MIT License
