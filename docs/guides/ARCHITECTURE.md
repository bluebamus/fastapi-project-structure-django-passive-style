# 아키텍처 문서

이 문서는 현재 아키텍처의 요약·수동 설치 규약을 설명합니다.
코드와 문서 간 불일치가 있으면 코드가 정답이며, 이 문서를 업데이트하세요.

검토 기준: **2026-09-17 현재 작업 트리**. 클래스·함수 중심의 단계별 실행은
[서버 시작·종료 HTML 안내서](./server-lifecycle-guide.html), MVC·주입·비동기·신규 기능 작성은
[개발 HTML 지침서](./feature-development-guide.html)에서 확인합니다.

주제별 심화 가이드 9종은 [docs/project-guide/v1.1/](../project-guide/v1.1/README.md) 에 있습니다.

---

## 1. 폴더 분류체계

```
fastapi-project-structure-django-passive-style/
├── main.py                          # 진입점: create_app() 호출만 (얇은 entrypoint)
├── config.py                        # INSTALLED_APPS + Pydantic Settings 12종
│                                    # (timezone/app/db/cors/log/middleware/redis/jwt/api/session/smtp/upload)
├── pyproject.toml                   # 의존성 + [tool.uv] package = false + pytest 마커(mysql·browser)
├── alembic.ini
├── compose.test.yaml                # 테스트 전용 MySQL 8.4 (127.0.0.1:3309, `-m mysql` 용)
├── .env.example                     # 설정 키 전체 목록 (자동 fallback 아님)
│
├── app/
│   ├── features/                    # 기능 단위 앱
│   │                                # 설치: home·blog·reply·sns·user·auth·catalog(ORM 예제)·reports(Raw 예제)
│   │   ├── home/                    # 예시 앱 — 접속 로그 (access_log_sink.py 를 ready() 에서 등록)
│   │   │   ├── __init__.py          # 가벼운 package marker (Router·Model import 금지)
│   │   │   ├── apps.py              # AppConfig, ready()는 process-local wiring
│   │   │   ├── api/routers/
│   │   │   │   ├── router.py        # 앱 루트 라우터 (<name>_router: v1 취합)
│   │   │   │   └── v1/              # 버전별 엔드포인트 (뷰는 HTTP 역할만)
│   │   │   ├── models/              # SQLAlchemy ORM 모델
│   │   │   ├── schemas/             # Pydantic 요청/응답 스키마
│   │   │   ├── services/            # 비즈니스 로직
│   │   │   ├── repositories/        # 데이터 접근 계층
│   │   │   ├── dependencies/        # FastAPI Depends 헬퍼 (Service 구성 — 커밋은 핸들러)
│   │   │   ├── admin.py             # SQLAdmin ModelView + admin_views (모델이 있으면 필수)
│   │   │   ├── exceptions.py        # 기능 예외 (선택)
│   │   │   └── tests/               # 기능 테스트
│   │   └── <name>/                  # 추가 앱은 같은 구조를 따름
│   │
│   ├── core/                        # 프레임워크 인프라 (features 가 의존)
│   │   ├── bootstrap.py             # create_app() 및 lifespan 조립, /health·/ready, 예외 핸들러
│   │   ├── resources.py             # manage_application_resources(): Redis ping·개발 DDL·AsyncExitStack 역순 정리
│   │   ├── apps/                    # AppConfig·Apps(config/registry/exceptions) + wiring.py(FastAPI·SQLAdmin adapter)
│   │   ├── exception.py             # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터 (새 앱의 태그도 여기 선언)
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리·세션 Dependency, background_session, owned_tables
│   │   │   ├── router.py            # 읽기/쓰기 라우팅 (DatabaseRouter·RoutingSession·read/write intent)
│   │   │   └── errors.py            # convert_db_error: DB 예외 → 공통 예외 (SQL·바인딩 값 비노출)
│   │   ├── models/models_base.py    # SQLAlchemy Base (declarative) + UUIDPrimaryKey·Timestamp Mixin
│   │   ├── repositories/
│   │   │   ├── repository_base.py   # BaseRepository (ORM 공개 CRUD)
│   │   │   ├── crud_base.py         # CRUDBase: ORM protected primitive (_get/_add/_update/_delete)
│   │   │   ├── raw_repository_base.py # RawRepositoryBase (Raw SQL 공개 API, query_name 검증)
│   │   │   └── raw_crud_base.py     # RawCRUDBase: Raw 실행 primitive (read/write intent)
│   │   ├── services/services_base.py # BaseService (commit/rollback 헬퍼)
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       ├── background_tasks.py  # 응답 후 태스크 추적 (누수 방지)
│   │       └── access_log_sink.py
│   │
│   ├── celery/                      # 중앙 Celery (기능별 worker/ 미사용)
│   │   ├── app.py                   # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── tasks.py                 # 중앙 태스크 모듈 (모든 기능 백그라운드 작업)
│   │   ├── task.py                  # run_async() 동기 브릿지 (worker 프로세스당 영속 loop)
│   │   └── lifecycle.py             # worker_process_shutdown: DB dispose → loop 종료
│   │
│   └── utils/                       # 순수 유틸 (외부·상위 계층 의존 없음)
│       ├── logs/                    # 구조화 로깅 (get_logger, setup_uvicorn_logging)
│       ├── authenticator/           # 인증 (JWT·bcrypt)
│       ├── pagination/              # 페이지네이션 (순수 dataclass)
│       └── validators.py            # 공통 값 검증
│
├── scripts/
│   ├── new_app.py                   # 신규 앱 골격 생성기 (설정 파일은 수정하지 않음)
│   ├── review_gate.py               # 검수 게이트 일괄 실행 (--fast / --list)
│   ├── bandit_gate.py               # Bandit MEDIUM 이상 게이트
│   └── openapi_revert_check.py      # OpenAPI 규칙 fail-on-revert 검사
│
├── tests/                           # 횡단 테스트 (core 계약·배선·교차 기능)
│   ├── core/                        # 설정 계약, registry(apps/), 자원 수명, admin 정책, 마이그레이션 체인
│   ├── integration/                 # `-m mysql` — compose.test.yaml 의 MySQL 8.4 필요 (미가용 시 skip)
│   ├── browser/                     # `-m browser` — 실제 uvicorn + Chromium 으로 Scalar 렌더링 확인
│   ├── scripts/                     # new_app 생성기 테스트
│   ├── utils/                       # 로깅·인증·페이지네이션
│   └── test_*.py                    # route inventory·OpenAPI 계약·계층 규칙·문서 정합성 등
│
├── migrations/
│   ├── env.py                       # App Registry 로 설치 앱의 모델만 수집 (runtime 과 동일 경로)
│   └── versions/                    # baseline → user password → catalog → sales_orders
├── .github/workflows/ci.yml         # CI 게이트 (ruff·format·mypy 콜드캐시·bandit·pytest 커버리지 85%·
│                                    #  alembic head/드리프트) + MySQL·browser job
└── docs/
    ├── guides/
    │   ├── ARCHITECTURE.md          # ← 이 문서 (아키텍처 SSOT)
    │   ├── QUICKSTART.md            # 최소 실행 경로
    │   ├── server-lifecycle-guide.html # 설정·기동·요청·종료 상세 추적
    │   └── feature-development-guide.html # MVC·DI·신규 API/테이블 개발
    ├── django-style-app-registry/   # registry 설계·Django 호환 범위
    ├── project-guide/v1.1/          # 주제별 심화 가이드
    └── crp/groups/                  # 검수 기록 (결정·잔여 위험 이력)
```

> 기능 테스트는 `app/features/<name>/tests/`, 횡단 테스트는 최상위 `tests/` 에 둡니다.
> `pytest` 가 양쪽을 모두 수집합니다.

### 의존 방향

```
features → core → utils
```

`core`는 `utils`만 알고, `features`는 `core`를 사용합니다.
업무 기반 `core`가 특정 기능의 Service/Repository에 의존하지 않는 것이 원칙입니다.
등록을 담당하는 `Apps`·`AppConfig`와 wiring adapter는 설치 목록에 따라 기능 모듈을 동적으로 import합니다.
기능 앱이 미들웨어 등에 붙어야 하면 등록 훅으로 연결합니다(예: `access_log_sink.register_sink()`).

---

## 2. Django식 수동 앱 등록 (INSTALLED_APPS + registry)

라우터 등록에 자동 디렉터리 스캔을 쓰지 않습니다. `main.py` 에 `include_router` 를
한 줄씩 쌓지도 않습니다. **설치 앱의 유일한 진실 공급원은 `config.INSTALLED_APPS`**
이고, 등록된 앱의 Router·Models·Admin 결선은 registry 가 컨벤션대로 처리합니다.

수동으로 결정하는 것과 컨벤션이 처리하는 것을 나눈 것이 이 구조의 핵심입니다.

| | 결정 주체 |
|---|---|
| 어떤 앱을 설치할지, 어떤 순서로 | 사람 (`config.INSTALLED_APPS`) |
| 설치된 앱의 Router·Models·Admin 결선 | registry (컨벤션) |

### 2.1 `config.INSTALLED_APPS`

```python
INSTALLED_APPS: list[str] = [
    "app.features.home.apps.HomeConfig",
    "app.features.blog.apps.BlogConfig",
    "app.features.reply.apps.ReplyConfig",
    "app.features.sns.apps.SnsConfig",
    "app.features.user.apps.UserConfig",
    "app.features.auth.apps.AuthConfig",
    "app.features.catalog.apps.CatalogConfig",
    "app.features.reports.apps.ReportsConfig",
]
```

Django 와 같은 두 가지 형식을 받습니다.

- **config class 경로** — `"app.features.blog.apps.BlogConfig"` (권장, 명시적)
- **package 경로** — `"app.features.blog"` (registry 가 `blog.apps` 에서 기본 config 선택)

디렉터리를 만드는 것만으로는 앱이 설치되지 않습니다. **새 프로세스에서** 목록에서 뺀 앱은
route·registry 소유 모델·Admin·`ready()`의 등록 대상에서 제외됩니다. 다만 이미 import한
매핑 클래스는 전역 `Base.metadata`에 남습니다. 실행 중 목록 변경이나 새 registry 생성이
SQLAlchemy metadata를 자동으로 청소하는 것은 아닙니다.

### 2.2 앱 패키지 — `apps.py` 와 가벼운 `__init__.py`

```python
# app/features/<name>/apps.py
from app.core.apps import AppConfig


class <Name>Config(AppConfig):
    name = "app.features.<name>"
```

```python
# app/features/<name>/__init__.py — 가벼운 package marker
"""<Name> 기능 패키지."""
```

`__init__.py` 는 Router 도 Model 도 import 하지 않습니다. 3단계 초기화 순서를 지키려면
root package import 단계에서 하위 모듈이 딸려오면 안 되기 때문입니다.

결선 컨벤션은 `AppConfig` 가 선언합니다.

| 구성요소 | 경로 | 공개 이름 | 없으면 |
|---|---|---|---|
| Router | `api/routers/router.py` | `<label>_router` | 그 앱은 route 없음(정상) |
| Models | `models/` | 매핑된 model class | 그 앱은 테이블 없음(정상, 예: `auth`) |
| Admin | `admin.py` | `admin_views` | 그 앱은 관리 화면 없음(정상) |

**module 자체가 없는 것과 module 안의 import 가 깨진 것은 다릅니다.** 전자는 선택 기능
부재로 넘어가고, 후자는 기동을 실패시킵니다 — 오타 하나가 "이 앱은 라우터가 없나 보다"
로 흡수되면 안 됩니다.

### 2.3 3단계 population

```text
Apps.populate(INSTALLED_APPS)
  1) config/root package import   →  apps_ready = True
  2) models import                →  models_ready = True
  3) AppConfig.ready()            →  ready = True
```

단계는 **앱별이 아니라 phase 단위**로 진행됩니다. 앱 하나를 끝까지 처리하고 다음으로
가는 것이 아니라, 모든 앱의 1단계가 끝난 뒤 2단계로 넘어갑니다. 그래야 어떤
`ready()` 든 모든 앱의 model 을 볼 수 있습니다.

`ready()`는 **process-local wiring 전용**입니다. DB 쿼리·network·subprocess·secret
출력을 하지 않습니다. 일반 CLI 호출에서는 실행될 수 있지만 현재 Alembic은
`run_ready=False`로 명시적으로 생략합니다.
`home` 의 access-log sink 등록이 유일한 사용 예입니다.
(회귀 가드: `tests/core/apps/test_installed_apps.py` 의 AST 검사)

### 2.4 `create_app()` — 조립 순서

```python
# app/core/bootstrap.py
def create_app(installed_apps=None, registry=None, *, enable_admin=None) -> FastAPI:
    ...
```

```text
1. 설치 앱 목록 결정 (config.INSTALLED_APPS 또는 주입값)
2. registry population (config → models → ready)
3. FastAPI 생성 + lifespan
4. CORS · user-info middleware · 예외 핸들러
5. install_routers(app, registry)          ← registry 기반, 각 앱 router 를 "/api" prefix 로 마운트
6. /health + /ready (+ DEBUG=true 일 때만 Scalar /docs·/openapi.json)
7. app.state.app_registry 저장
   ADMIN=true 일 때만 create_admin(...)     ← registry 기반, 여기서 sqladmin import
```

`install_routers()`는 앱 간 같은 method+path가 겹치면 `ImproperlyConfigured`로 기동을
실패시킵니다(먼저 등록된 쪽이 조용히 이기는 구조가 아닙니다). `enable_admin=None`이면
`ADMIN` 설정을 따릅니다.

2번이 3번보다 먼저인 이유는 모델·hook 등록을 앱 조립 전에 완료하기 위해서입니다.
기본 설치 경로에서는 startup과 migration이 같은 설치 목록을 따릅니다. 단, factory에
custom registry/설치 목록을 주입해도 현재 lifespan의 `_prepare_database()`·`owned_tables()`는
전역 `apps`와 `config.INSTALLED_APPS`를 사용합니다. **custom factory의 route 집합이
startup DDL 집합까지 자동 결정한다고 가정하면 안 됩니다.**

`main.py` 는 `app = create_app()` 과 로컬 uvicorn 실행만 남는 얇은 진입점입니다.
factory 로 만든 이유는 테스트가 **격리된 앱**(auth 를 뺀 앱, ADMIN=False 인 앱, 독립
registry 를 쓴 앱)을 만들 수 있어야 하기 때문입니다 — 모듈 최상단 조립은 프로세스당
하나뿐이라 "등록 안 한 앱은 안 붙는다" 를 실행으로 증명할 수 없습니다.

lifespan의 자원 조립은 `app/core/resources.py`의 `manage_application_resources()`가 담당합니다.
시작 시 Redis `ping()`을 확인하고 실패하면 서버 시작을 중단합니다. 종료는 background task →
Redis client → DB engine 순서이며, 사용 가능한 client는 `app.state.redis`에 있습니다.

`AsyncExitStack`은 DB cleanup을 먼저 등록하고 Redis context 진입 뒤 background cleanup을
등록합니다. startup ping 실패도 client 종료와 이미 등록된 DB 정리 경로로 연결됩니다.
각 cleanup은 background 5초·Redis close 5초·DB 10초의 개별 timeout이며 전체 deadline은
별도로 없습니다. 일반 오류·timeout은 기록하고 다음 callback을 시도하지만 정리 성공을
보장하지는 않습니다. DB dispose는 엔진을 순차 처리하므로 첫 엔진 오류가 뒤 엔진의 dispose를
건너뛰게 할 수 있습니다. 로그는 동기 console/file handler이며 queue listener가 없습니다.

Redis 검증과 별개로, 설정 import 단계의 fail-fast 검사도 있습니다. `ENV`가
`production`/`staging`인데 `ADMIN=true`이고 `ADMIN_UNAUTHENTICATED_ACK`가 켜져 있지 않으면
`config.py` import 자체가 실패합니다(인증 없는 `/admin` 사고 공개 방지).

### 2.5 core 와 adapter 의 경계

```text
app/core/apps/
├── config.py      AppConfig      ← Django lifecycle. 웹 프레임워크 모름
├── registry.py    Apps           ← Django lifecycle. 웹 프레임워크 모름
├── exceptions.py
└── wiring.py      install_routers / install_admin / create_admin   ← FastAPI 전용 확장
```

`config.py` 와 `registry.py` 는 FastAPI·SQLAdmin·SQLAlchemy 를 import 하지 않습니다.
Alembic 이나 CLI 가 registry 를 쓸 때 웹 스택이 딸려오지 않고, `ADMIN=False` 에서
sqladmin 이 로드되지 않는다는 보장도 여기서 시작됩니다.
(회귀 가드: `tests/core/apps/test_core_independence.py`, `tests/core/test_admin_lazy_loading.py`)

Router·Admin 결선은 **Django 기능이 아니라 이 프로젝트의 adapter** 입니다. 자세한
호환 범위는 [`django-style-app-registry/DJANGO-APP-COMPATIBILITY.md`](../django-style-app-registry/DJANGO-APP-COMPATIBILITY.md) 참고.

---

## 3. 새 기능 추가 — 목록에 한 줄

### 3.1 생성과 등록

```powershell
uv run python -m scripts.new_app orders --with-models --with-admin
```

생성기는 `app/features/orders/` 골격과 `apps.py` 를 만들고 **설정 파일은 건드리지
않습니다.** 옵션은 `--with-models`(models 골격), `--with-admin`(admin_views 골격, models 포함)
두 가지뿐이며, 대상 디렉터리가 이미 있으면 덮어쓰지 않고 실패합니다. 마지막에 붙여 넣을
한 줄을 출력합니다.

```python
# config.py
INSTALLED_APPS: list[str] = [
    # 기존 설치 앱 항목은 유지하고 아래 항목을 추가
    "app.features.orders.apps.OrdersConfig",   # ← 이 한 줄이 설치다
]
```

이 한 줄을 넣기 전까지 앱은 존재하지만 설치되지 않은 상태입니다. `main.py`·
`migrations/env.py`·`session.py` 는 손대지 않습니다.

골격 라우터가 쓰는 태그(예: `"Orders"`)는 `app/core/tags_metadata.py` 에 직접 선언해야
합니다 — 생성기가 출력하는 안내에 항목이 함께 나오며, 선언하지 않은 태그는 OpenAPI 계약
검사(`tests/test_openapi_contract.py`)에서 실패합니다.

### 3.2 등록 후 확인

```powershell
uv run alembic revision --autogenerate -m "add orders"   # 모델을 추가했다면
uv run alembic upgrade head
uv run python -m pytest app/features/orders
```

- route: `GET /api/v1/orders/ping`
- 모델: 등록된 앱의 model을 registry가 소유합니다. `models/__init__.py`에서 매핑 클래스를
  공개해야 소유권을 수집할 수 있습니다. 전역 `Base.metadata`와 registry 소유 집합은 다릅니다.
- Admin: `ADMIN=true` 인 환경에서만 등록됩니다(운영은 비활성 권장).

**앱을 목록에서 빼도 테이블은 자동으로 지워지지 않습니다.** 깨끗한 migration 프로세스에서
수집 대상에서 빠지면 `alembic revision --autogenerate`가 DROP TABLE을 제안할 수 있습니다 — 데이터 보존이
필요하면 그 마이그레이션을 그대로 적용하지 마세요.

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `apps.py` | ✅ | `AppConfig` subclass — 등록 대상 |
| `__init__.py` | ✅ | 가벼운 package marker (Router·Model import 금지) |
| `api/routers/router.py` + `v1/` | 선택 | 있으면 `<label>_router` 를 공개해야 함 |
| `models/` | 선택 | 없으면 테이블 없는 앱(예: `auth`). `models/__init__.py` 에서 매핑 클래스 공개 |
| `schemas/` `services/` `repositories/` `dependencies/` | 선택 | 데이터/로직 계층 |
| `admin.py` | 조건부 | 있으면 `admin_views` 를 공개해야 함. 모델이 있는 앱은 필수(`tests/core/test_admin_wiring.py`) |
| `tests/` | ✅ (컨벤션) | pytest 테스트. registry 가 강제하지는 않지만 생성기가 만든다 |

---

## 4. 요청 처리 & 트랜잭션 경계 (UnitOfWork 미사용)

UnitOfWork 패턴은 사용하지 않습니다. 트랜잭션 경계는 **쓰기 핸들러 본문**이 담당하고,
기능 의존성은 Service 구성만 합니다.

```
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → DB
     ↑ commit() 은 여기서
```

```python
# app/features/<name>/dependencies/<name>_dependencies.py — 구성만 한다
async def get_<name>_service(
    session: AsyncSession = Depends(get_writer_db_session),   # 쓰기용
) -> <Name>Service:
    return <Name>Service(session)


async def get_<name>_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),  # 조회용
) -> <Name>Service:
    return <Name>Service(session)


# app/features/<name>/api/routers/v1/<name>.py — 커밋은 여기서
async def create_<name>(
    payload: <Name>Create,
    service: <Name>Service = Depends(get_<name>_service),
) -> <Name>Response:
    obj = await service.create(payload)
    await service.commit()          # 트랜잭션 경계 — 응답 생성 전에 끝난다
    return <Name>Response.model_validate(obj)
```

- 뷰(view)는 HTTP 역할과 **커밋 시점 결정**을 맡습니다: 파라미터 수신 → 주입된 Service 호출
  → (쓰기면) `await service.commit()` → 응답 변환.
- 예외로 빠져나가면 `get_writer_db_session` teardown 이 `rollback()` 합니다.
- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_only_db_session` 을 받고 커밋하지 않습니다.
  `DB_ROUTER_ENABLED=true`이고 replica가 구성돼 있으면 읽기가 replica로 향합니다.
  read-only 쓰기 차단(`ReadOnlyRoutingError`)은 두 곳에 있습니다. `RoutingSession.get_bind()`의
  검사는 **router가 켜져 있을 때만** 동작하므로, router가 꺼진 기본 설정에서는 ORM 쓰기가
  read-only 세션에서 차단되지 않습니다. Raw primitive(`RawCRUDBase`)는 router와 무관하게
  `is_read_only_session()`으로 **실행 전에** Raw 쓰기를 거부합니다. 어느 쪽도 임의
  `session.execute()` 경로의 모든 SQL까지 완전히 보호하는 sandbox는 아니며, 읽기 전용
  경계는 `tests/test_read_path_no_commit.py`의 구조 검사로도 고정합니다.
- `Service`는 `BaseService`를 상속합니다. `Repository` 는 **두 계열 중 하나**를 상속합니다 —
  ORM 이면 `BaseRepository`(제네릭 CRUD, `app/core/repositories/repository_base.py`),
  Raw SQL 이면 `RawRepositoryBase`(`app/core/repositories/raw_repository_base.py`).
  두 계열은 **상속 관계가 없습니다** — 하나의 Base 가 모델과 row 를 함께 돌려주면 호출부가
  무엇을 받았는지 타입으로 알 수 없기 때문입니다. 참조 예제는
  `app/features/catalog/repositories/product_repository.py`(ORM) 와
  `app/features/reports/repositories/sales_report_repository.py`(Raw) 입니다.
  어느 쪽을 고를지는 [ORM vs Raw 결정 가이드](../project-guide/v1.1/09-orm-vs-raw-decision.md)
  에 판단 기준과 Raw 전용 제약이 정리돼 있습니다.
- 요청 밖(백그라운드/Celery) 세션은 `background_session()` 컨텍스트(별도 풀)를 씁니다.

> **왜 의존성이 아니라 핸들러인가.** 이전에는 의존성이 `yield` 이후 커밋했습니다. 그런데
> 기본 request scope의 yield dependency 종료 코드는 **응답 전송 후에** 실행되므로,
> 그곳의 commit이 실패해도 클라이언트는 이미 `201`을 받을 수 있습니다. function scope는
> 종료 시점이 다릅니다([FastAPI 공식 설명](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)). 핸들러에서 commit하면
> 실패가 응답 코드에 정직하게 반영됩니다. 구조 증거: `tests/test_read_path_no_commit.py`.

---

## 5. Celery 태스크 — 중앙 집중 include

`app/celery/app.py`는 중앙 태스크 모듈 하나만 `include`합니다(기능별 `worker/` 미사용).

```python
celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
```

- 모든 기능 백그라운드 태스크는 `app/celery/tasks.py`에 `@celery_app.task`로 정의합니다.
  (예: `home.aggregate_access_stats`)
- 동기 워커에서 async 코루틴 실행: `app/celery/task.py`의 `run_async(coro)`.
- 태스크 내 DB 세션: `background_session()` 컨텍스트.
- worker 종료: `app/celery/lifecycle.py`가 `worker_process_shutdown` 신호에서 DB engine dispose →
  `shutdown_asyncgens()` → loop close 순으로 정리합니다. FastAPI lifespan과는 소유권이 다른
  프로세스이며, API 기동이 worker를 띄우지도 않습니다.

---

## 6. Alembic 마이그레이션

`migrations/env.py`는 **런타임과 같은 설치 규칙**으로 별도의 `Apps()` 인스턴스에서 모델을
수집합니다. 디렉터리 전체를 훑지는 않습니다. 새 앱을 추가해도 이 파일은 손대지 않습니다 —
`config.INSTALLED_APPS` 한 줄이면 됩니다. 다만 `target_metadata = Base.metadata`는 전역
객체이므로, 같은 프로세스에서 미등록 모델을 미리 import하면 metadata에 남을 수 있습니다.
Alembic metadata를 registry 소유 모델만으로 완전히 필터링하는 구현은 아닙니다.

```python
from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS, db_settings

# run_ready=False: migration 은 스키마만 다룬다. 앱의 runtime 결선(sink 등록 등)을
# 실행할 이유가 없다. Apps 인스턴스는 격리되지만 Base.metadata·Python import 상태는 전역이다.
Apps().populate(INSTALLED_APPS, run_ready=False)
target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)
```

**DB URL 결정** — `env.py`는 환경변수를 직접 읽지 않고 `db_settings.ALEMBIC_URL` property만 씁니다.
1. `ALEMBIC_DATABASE_URL` 설정값이 있으면 그대로 (로컬/CI 오버라이드, SQLite 등)
2. 없으면 primary DSN(`db_settings.MYSQL_WRITER_URL`)의 `+aiomysql`을 `+pymysql`로 치환
   — migration은 항상 writer에서 실행합니다.

```bash
uv run alembic revision --autogenerate -m "add <name> model"
uv run alembic upgrade head
```

---

## 7. 환경 및 툴링

| 명령 | 설명 |
|------|------|
| `uv sync` | 의존성 설치 (가상환경 자동 생성) |
| `uv run uvicorn main:app --reload` | 개발 서버 실행 |
| `uv run alembic upgrade head` | DB 마이그레이션 적용 |
| `uv run python -m pytest -m "not mysql and not browser"` | 외부 인프라 없는 테스트 (CI 기본 job 과 같은 범위) |
| `docker compose -f compose.test.yaml up -d --wait` → `uv run python -m pytest -m mysql` | MySQL 8.4 통합 테스트 |
| `uv run python -m playwright install chromium` → `uv run python -m pytest -m browser` | Scalar 브라우저 렌더링 테스트 |
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` | 정적 분석 |
| `uv run python -m scripts.bandit_gate` | Bandit MEDIUM 이상 보안 게이트 |
| `uv run python -m scripts.review_gate [--fast\|--list]` | 위 검사 일괄 실행 (`--fast` 는 MySQL 통합 제외) |

`[tool.uv] package = false` — 루트 패키지 빌드 없이 의존성만 설치(flat layout).
Python 요구 버전은 `>=3.12`(`.python-version` 은 3.14), 주요 의존성은 FastAPI `0.141.x`,
SQLAlchemy 2.x, Pydantic 2.x, Celery 5.x, redis-py 5.x 입니다(정확한 범위는 `pyproject.toml`).
`mysql` 마커 테스트는 MySQL 이 없으면 skip 되고(CI 는 그 skip 을 실패로 봄), `browser` 마커
테스트는 skip 없이 **실패**합니다. browser 테스트는 실제 uvicorn 을 `DEBUG=true` 로 띄우므로
Chromium 외에 compose.test.yaml 의 MySQL 과 startup `ping()` 이 통과할 Redis(기본
`localhost:6379`)도 필요합니다 — compose.test.yaml 에는 Redis 서비스가 없습니다.

---

## 8. 변경 이력

아래는 기반 저장소 전환을 포함한 **과거 기록**이며 현재 사용법은 본문의 INSTALLED_APPS 규약입니다.

| 날짜 | 변경 내용 |
|------|----------|
| 2026-09-17 | **가이드 문서 위치 이동 + 현행화**: `docs/ARCHITECTURE.md`·`docs/QUICKSTART.md` 를 `docs/guides/` 로 옮기고 HTML 안내서 2종과 함께 현재 작업 트리 기준으로 대조했다. startup 필수 Redis `ping()`(`app/core/resources.py`)과 종료 순서(background → Redis → DB)를 반영하고, read-only 차단 범위(router 꺼짐 시 ORM 미차단) 서술, Alembic URL 결정 경로(`ALEMBIC_URL`), 생성기의 태그 선언 단계, 테스트 마커·게이트 명령을 정정·보강했다. |
| 2026-08-25 | **골격 목적 기준 검수 + 문서 정리**: 완료된 착수 명세 5종과 폐기된 가이드 버전(`docs/orm-raw-repository/`, 통합 계획, 운영 준비 계획, `project-guide/v1.0/`)을 삭제했다 — 15파일 5,840줄. "무엇을 만들 것인가" 를 지시하는 문서는 이미 만들어진 지금 길만 늘리고, 결정 근거는 `docs/crp/groups/` 와 git 이력에 남는다. 아울러 문서가 없는 기능을 있다고 서술한 것들을 정정했다(`require_admin`·`AppRegistry.discover()` 부재, `/ready` 실재, Raw 계층 실재, reports 경로 오기). 코드는 `scripts/new_app.py` 한 곳만 고쳤다 — 생성기 골격에 `operation_id` 가 없어 만든 즉시 OpenAPI 계약 검사에 걸리던 것을 닫았다. 공개 route inventory·응답 스키마·registry 계약은 불변. 기록: `docs/crp/groups/skeleton-purpose-audit/`. |
| 2026-08-13 | **레이트 리밋 제거**: `app/core/rate_limit.py`·`slowapi` 의존성·`RATE_LIMIT_*` 설정·`auth` 라우트 데코레이터를 모두 삭제했다. 요청 한도가 필요하면 리버스 프록시나 API gateway 단에서 건다 — 인메모리 카운터는 워커별로 갈라져 실질 한도를 보장하지 못했다. 나머지 미들웨어·예외 핸들러·공개 route inventory 는 불변. |
| 2026-08-12 | **default `a980b71` 기준선 위에 Django app registry 이식**: 구현 tree 를 기준 저장소 tracked tree 로 교체한 뒤 `app/core/apps/`(`AppConfig`·`Apps`·`wiring`)와 `app/core/bootstrap.create_app()` 을 추가. 설치 앱의 진실 공급원이 `config.INSTALLED_APPS` 로 일원화됐다 — `main.py` 의 `include_router` 나열, 중앙 admin 취합 파일, 디렉터리 스캔 모델 수집을 모두 대체한다. 기능 `__init__.py` 는 가벼운 marker 가 되고, home sink 등록은 `HomeConfig.ready()` 로 이동. 공개 route inventory·auth·rate limit·미들웨어·migration chain 은 불변. 호환 범위: `docs/django-style-app-registry/DJANGO-APP-COMPATIBILITY.md`. |
| 2026-06-23 | 기능 모델 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-07-01 | **표준 FastAPI 배선으로 전환**: `AppRegistry`/`bootstrap.create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py`가 `router` 공개 + `main.py`가 명시 `include_router`로 취합. |
| 2026-08-11 | **`app/features/` 명칭 확정 + SQLAdmin 소유권을 기능으로 이전**: 폴더·import·문서 참조 70개 파일 일괄 정정. 과거 중앙 관리자 패키지 삭제 — ModelView 는 모델과 같은 폴더에 있어야 컬럼 변경이 함께 눈에 들어오고 기능 단위 복사·삭제 시 따라온다. `app/features/<name>/admin.py` 가 ModelView 와 `admin_views` 를 소유하고, 신설 `app/features/admin.py` 가 **명시 import** 로 `ADMIN_VIEWS` 에 취합한다(과거 `getattr(module, "admin_views", [])` 관용 수집은 빈 `admin.py` 를 무신호로 건너뛰어 ADMIN-1 을 낳았으므로 복원하지 않음). 회귀 가드 `tests/test_admin_wiring.py` 에 "모델을 가진 기능은 자기 `admin.py` 를 갖는다" 검사 추가. C-7 자격증명 비노출·생성차단 정책과 공개 API 경로·응답 스키마 불변. |
| 2026-08-11 | **문서 드리프트 정정**: §4 와 README 가 P1-3 이전의 "의존성이 `yield` 후 커밋" 을 계속 설명하고 있었다(코드는 이미 핸들러 커밋). §4 예시를 실제 코드(쓰기/조회 의존성 분리 + 핸들러 `await service.commit()`)로 교체하고, `BaseService` 독스트링도 같이 정정. 아울러 재구조화 잔재 정리 — `tests/features/` 잔류분을 `app/features/<name>/tests/` 로 통합, 이동 중 겹친 디렉터리 레벨과 빈 `tests/scripts/` 제거. |
| 2026-08-11 | **Django 배선 제거 (구조는 vertical slice 유지)**: 옛 중앙 목록 순회 → 명시 `include_router`; 기능별 `admin.py` 관용 수집(`getattr(..., "admin_views", [])`) → 중앙 `app/features/admin.py`의 명시 import(`ADMIN_VIEWS`+`register_admin`); `scripts/new_app.py` 제거. 폴더는 실제 코드 기준 `app/features/` 를 유지한다. 모델 등록은 `models_registry` 디렉터리 스캔 유지. 공개 API 경로·응답 스키마·SQLAdmin 보안 정책 불변. |
| 2026-08-11 | **문서 정합성 재정리**: 삭제된 심화·리팩터링 문서 참조, 존재하지 않는 과거 모듈·관리자 경로 참조, 제거된 중앙 목록 설명을 실제 코드 기준으로 정정. |
