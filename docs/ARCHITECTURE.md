# 아키텍처 문서

이 문서는 프로젝트의 유일한 공식 아키텍처 소스입니다.
코드와 문서 간 불일치가 있으면 코드가 정답이며, 이 문서를 업데이트하세요.

---

## 1. 폴더 분류체계

```
fastapi-default-project-structure/
├── main.py                          # 진입점: create_app() 호출만 (얇은 entrypoint)
├── config.py                        # Pydantic Settings (app/db/cors/log/redis/middleware/timezone)
├── pyproject.toml                   # 의존성 + [tool.uv] package = false
│
├── app/
│   ├── features/                    # 기능 단위 앱
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── __init__.py          # router 공개 + models import (admin_views 재노출 금지)
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
│   │   ├── exception.py             # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── rate_limit.py            # slowapi limiter + 초과 핸들러
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀, background_session
│   │   │   ├── router.py            # 읽기/쓰기 라우팅 (RoutingSession)
│   │   ├── models/models_base.py    # SQLAlchemy Base (declarative) + Timestamp·UUID Mixin
│   │   ├── repositories/
│   │   │   ├── repository_base.py   # BaseRepository
│   │   │   └── crud_base.py         # 제네릭 CRUD 메서드
│   │   ├── services/services_base.py # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       ├── background_tasks.py  # 응답 후 태스크 추적 (누수 방지)
│   │       └── access_log_sink.py
│   │
│   ├── celery/                      # 중앙 Celery (기능별 worker/ 미사용)
│   │   ├── app.py                   # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── tasks.py                 # 중앙 태스크 모듈 (모든 기능 백그라운드 작업)
│   │   └── task.py                  # run_async() 동기 브릿지
│   │
│   └── utils/                       # 순수 유틸 (외부·상위 계층 의존 없음)
│       ├── logs/                    # 구조화 로깅 (get_logger, setup_uvicorn_logging)
│       ├── authenticator/           # 인증 (JWT·bcrypt)
│       ├── pagination/              # 페이지네이션 (순수 dataclass)
│       └── validators.py            # 공통 값 검증
│
├── tests/                           # 횡단 테스트 (core 계약·배선·교차 기능)
│   ├── core/                        # 설정 계약, admin 뷰 정책, 마이그레이션 체인
│   └── utils/                       # 로깅·인증·페이지네이션
│
├── migrations/env.py                # import_all_models()(SSOT) 로 전 기능 모델 자동 수집
├── .github/workflows/ci.yml         # CI 게이트 (ruff·format·mypy 콜드캐시·pytest·bandit·alembic)
└── docs/
    ├── ARCHITECTURE.md              # ← 이 문서 (아키텍처 SSOT)
    └── QUICKSTART.md                # 최소 실행 경로
```

> 기능 테스트는 `app/features/<name>/tests/`, 횡단 테스트는 최상위 `tests/` 에 둡니다.
> `pytest` 가 양쪽을 모두 수집합니다.

### 의존 방향

```
features → core → utils
```

`core`는 `utils`만 알고, `features`는 `core`를 사용합니다.
`core`는 절대로 `features`를 import하지 않습니다(기능 앱이 미들웨어 등에 붙어야 하면
등록 훅으로 연결 — 예: `access_log_sink.register_sink()`).

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
]
```

Django 와 같은 두 가지 형식을 받습니다.

- **config class 경로** — `"app.features.blog.apps.BlogConfig"` (권장, 명시적)
- **package 경로** — `"app.features.blog"` (registry 가 `blog.apps` 에서 기본 config 선택)

디렉터리를 만드는 것만으로는 앱이 설치되지 않습니다. 목록에서 빼면 디렉터리가 남아
있어도 route·모델·Admin·`ready()` 가 전부 떨어집니다.

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

`ready()` 는 **process-local wiring 전용**입니다. DB 쿼리·network·subprocess·secret
출력을 하지 않습니다 — migration 과 CLI 도 이 hook 을 실행할 수 있기 때문입니다.
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
4. CORS · user-info middleware · rate limiter · 예외 핸들러
5. install_routers(app, registry)          ← registry 기반
6. /health + Scalar docs
7. ADMIN=true 일 때만 create_admin(...)     ← registry 기반, 여기서 sqladmin import
```

2번이 3번보다 먼저인 이유는 startup 테이블 생성과 migration metadata 가 같은 모델
집합을 봐야 하기 때문입니다.

`main.py` 는 `app = create_app()` 과 로컬 uvicorn 실행만 남는 얇은 진입점입니다.
factory 로 만든 이유는 테스트가 **격리된 앱**(auth 를 뺀 앱, ADMIN=False 인 앱, 독립
registry 를 쓴 앱)을 만들 수 있어야 하기 때문입니다 — 모듈 최상단 조립은 프로세스당
하나뿐이라 "등록 안 한 앱은 안 붙는다" 를 실행으로 증명할 수 없습니다.

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
호환 범위는 [`django-style-app-registry/DJANGO-APP-COMPATIBILITY.md`](django-style-app-registry/DJANGO-APP-COMPATIBILITY.md) 참고.

---

## 3. 새 기능 추가 — 목록에 한 줄

### 3.1 생성과 등록

```powershell
uv run python -m scripts.new_app orders --with-models --with-admin
```

생성기는 `app/features/orders/` 골격과 `apps.py` 를 만들고 **설정 파일은 건드리지
않습니다.** 마지막에 붙여 넣을 한 줄을 출력합니다.

```python
# config.py
INSTALLED_APPS: list[str] = [
    ...
    "app.features.orders.apps.OrdersConfig",   # ← 이 한 줄이 설치다
]
```

이 한 줄을 넣기 전까지 앱은 존재하지만 설치되지 않은 상태입니다. `main.py`·
`migrations/env.py`·`session.py` 는 손대지 않습니다.

### 3.2 등록 후 확인

```powershell
uv run alembic revision --autogenerate -m "add orders"   # 모델을 추가했다면
uv run alembic upgrade head
uv run python -m pytest app/features/orders
```

- route: `GET /api/v1/orders/ping`
- 모델: 등록된 앱의 model 만 `Base.metadata` 에 들어갑니다.
- Admin: `ADMIN=true` 인 환경에서만 등록됩니다(운영은 비활성 권장).

**앱을 목록에서 빼도 테이블은 자동으로 지워지지 않습니다.** metadata 에서 빠지므로
`alembic revision --autogenerate` 가 DROP TABLE 을 제안할 수 있습니다 — 데이터 보존이
필요하면 그 마이그레이션을 그대로 적용하지 마세요.

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `apps.py` | ✅ | `AppConfig` subclass — 등록 대상 |
| `__init__.py` | ✅ | 가벼운 package marker (Router·Model import 금지) |
| `api/routers/router.py` + `v1/` | 선택 | 있으면 `<label>_router` 를 공개해야 함 |
| `models/` | 선택 | 없으면 테이블 없는 앱(예: `auth`) |
| `schemas/` `services/` `repositories/` `dependencies/` | 선택 | 데이터/로직 계층 |
| `admin.py` | 선택 | 있으면 `admin_views` 를 공개해야 함 |
| `tests/` | ✅ | pytest 테스트 |

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
    session: AsyncSession = Depends(get_session),          # 쓰기용
) -> <Name>Service:
    return <Name>Service(session)


async def get_<name>_service_readonly(
    session: AsyncSession = Depends(get_read_session),     # 조회용
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
- 예외로 빠져나가면 `get_session` teardown이 `rollback()` 합니다.
- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_session` 을 받고 커밋하지 않습니다.
  `DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅되며, 읽기 경로에서 쓰기를 시도하면
  `ReadOnlyRoutingError` 로 즉시 실패합니다.
- `Service`는 `BaseService`를, `Repository`는 `BaseRepository`(제네릭 CRUD)를 상속합니다.
- 요청 밖(백그라운드/Celery) 세션은 `background_session()` 컨텍스트(별도 풀)를 씁니다.

> **왜 의존성이 아니라 핸들러인가.** 이전에는 의존성이 `yield` 이후 커밋했습니다. 그런데
> FastAPI 상위 버전에서 yield dependency 의 종료 코드가 **응답 전송 후에** 실행되도록 바뀌면서,
> 커밋이 실패해도 클라이언트는 이미 `201` 을 받은 상태가 됩니다. 커밋을 핸들러 본문으로 옮기면
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

---

## 6. Alembic 마이그레이션

`migrations/env.py`는 **런타임과 같은 registry** 로 모델을 수집합니다. 디렉터리를 훑지 않으므로 등록하지 않은 앱의 테이블이 autogenerate 에 새어 들지 않습니다. 새 앱을 추가해도 이 파일은 손대지 않습니다 — `config.INSTALLED_APPS` 한 줄이면 됩니다.

```python
from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS

# run_ready=False: migration 은 스키마만 다룬다. 앱의 runtime 결선(sink 등록 등)을
# 실행할 이유가 없다. 격리 인스턴스라 alembic 이 전역 상태를 만들지도 않는다.
Apps().populate(INSTALLED_APPS, run_ready=False)
target_metadata = Base.metadata
```

**DB URL 우선순위:**
1. `ALEMBIC_DATABASE_URL` 환경 변수 (로컬/CI 오버라이드, SQLite 등)
2. `db_settings.MYSQL_URL` — 비동기 드라이버(`+aiomysql`)를 동기(`+pymysql`)로 치환

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
| `uv run pytest` | 테스트 실행 |
| `uv run ruff check .` / `uv run mypy .` | 정적 분석 |

`[tool.uv] package = false` — 루트 패키지 빌드 없이 의존성만 설치(flat layout).

---

## 8. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-08-12 | **default `a980b71` 기준선 위에 Django app registry 이식**: 구현 tree 를 기준 저장소 tracked tree 로 교체한 뒤 `app/core/apps/`(`AppConfig`·`Apps`·`wiring`)와 `app/core/bootstrap.create_app()` 을 추가. 설치 앱의 진실 공급원이 `config.INSTALLED_APPS` 로 일원화됐다 — `main.py` 의 `include_router` 나열, 중앙 admin 취합 파일, 디렉터리 스캔 모델 수집을 모두 대체한다. 기능 `__init__.py` 는 가벼운 marker 가 되고, home sink 등록은 `HomeConfig.ready()` 로 이동. 공개 route inventory·auth·rate limit·미들웨어·migration chain 은 불변. 호환 범위: `docs/django-style-app-registry/DJANGO-APP-COMPATIBILITY.md`. |
| 2026-06-23 | 기능 모델 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-07-01 | **표준 FastAPI 배선으로 전환**: `AppRegistry`/`bootstrap.create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py`가 `router` 공개 + `main.py`가 명시 `include_router`로 취합. |
| 2026-08-11 | **`app/features/` 명칭 확정 + SQLAdmin 소유권을 기능으로 이전**: 폴더·import·문서 참조 70개 파일 일괄 정정. 과거 중앙 관리자 패키지 삭제 — ModelView 는 모델과 같은 폴더에 있어야 컬럼 변경이 함께 눈에 들어오고 기능 단위 복사·삭제 시 따라온다. `app/features/<name>/admin.py` 가 ModelView 와 `admin_views` 를 소유하고, 신설 `app/features/admin.py` 가 **명시 import** 로 `ADMIN_VIEWS` 에 취합한다(과거 `getattr(module, "admin_views", [])` 관용 수집은 빈 `admin.py` 를 무신호로 건너뛰어 ADMIN-1 을 낳았으므로 복원하지 않음). 회귀 가드 `tests/test_admin_wiring.py` 에 "모델을 가진 기능은 자기 `admin.py` 를 갖는다" 검사 추가. C-7 자격증명 비노출·생성차단 정책과 공개 API 경로·응답 스키마 불변. |
| 2026-08-11 | **문서 드리프트 정정**: §4 와 README 가 P1-3 이전의 "의존성이 `yield` 후 커밋" 을 계속 설명하고 있었다(코드는 이미 핸들러 커밋). §4 예시를 실제 코드(쓰기/조회 의존성 분리 + 핸들러 `await service.commit()`)로 교체하고, `BaseService` 독스트링도 같이 정정. 아울러 재구조화 잔재 정리 — `tests/features/` 잔류분을 `app/features/<name>/tests/` 로 통합, 이동 중 겹친 디렉터리 레벨과 빈 `tests/scripts/` 제거. |
| 2026-08-11 | **Django 배선 제거 (구조는 vertical slice 유지)**: 옛 중앙 목록 순회 → 명시 `include_router`; 기능별 `admin.py` 관용 수집(`getattr(..., "admin_views", [])`) → 중앙 `app/features/admin.py`의 명시 import(`ADMIN_VIEWS`+`register_admin`); `scripts/new_app.py` 제거. 폴더는 실제 코드 기준 `app/features/` 를 유지한다. 모델 등록은 `models_registry` 디렉터리 스캔 유지. 공개 API 경로·응답 스키마·SQLAdmin 보안 정책 불변. |
| 2026-08-11 | **문서 정합성 재정리**: 삭제된 심화·리팩터링 문서 참조, 존재하지 않는 과거 모듈·관리자 경로 참조, 제거된 중앙 목록 설명을 실제 코드 기준으로 정정. |
