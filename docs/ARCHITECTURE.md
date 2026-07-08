# 아키텍처 문서

이 문서는 프로젝트의 아키텍처를 요약한다. 코드와 문서가 어긋나면 **코드가 정답**이며 이 문서를 갱신한다.
단계별 튜토리얼(설치/실행/새 앱 추가)은 루트 [`README.md`](../README.md)를 참조한다.

---

## 1. 한눈에 보기

- **정체성**: Django의 `INSTALLED_APPS`처럼 도메인 앱을 **명시적으로 수동 등록(passive)** 하는 FastAPI 구조 템플릿.
- **등록 SSOT**: [`config.py`](../config.py)의 `INSTALLED_APPS` 리스트(문자열 이름). 자동 스캔이 아니라 이 목록이 진실 공급원이며, 목록 순서가 곧 로드 순서다.
- **결선 엔진**: [`app/core/registry.py`](../app/core/registry.py)의 `AppRegistry`가 목록을 읽어 라우터/모델/Admin을 **컨벤션**으로 연결한다.
- **계층**: `Router → Depends(get_<name>_service) → Service → Repository → DB`. 트랜잭션 경계는 **기능 의존성**이 담당한다(UnitOfWork 미사용).
- **진입점**: [`main.py`](../main.py)는 `app = create_app()` 한 줄. 조립은 전부 `create_app()` 안에서 일어난다.

---

## 2. 폴더 구조

```
fastapi-project-structure-django-passive-style/
├── main.py                         # 진입점: app = create_app()
├── config.py                       # Pydantic Settings + INSTALLED_APPS (등록 SSOT)
├── pyproject.toml                  # 의존성 + 도구 설정([tool.uv] package = false)
│
├── app/
│   ├── core/                       # 프레임워크 인프라 (도메인이 의존)
│   │   ├── bootstrap.py            # create_app() 팩토리 (lifespan·예외핸들러·미들웨어·라우터·Admin)
│   │   ├── registry.py             # AppRegistry — INSTALLED_APPS 읽어 컨벤션 결선
│   │   ├── exception.py            # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py        # OpenAPI 태그 메타데이터
│   │   ├── db/
│   │   │   ├── session.py          # 비동기 엔진(메인/백그라운드), 세션 팩토리, get_session
│   │   │   └── redis.py            # (플레이스홀더)
│   │   ├── models/models_base.py   # DeclarativeBase + UUIDMixin/TimestampMixin
│   │   ├── repositories/
│   │   │   ├── crud_base.py        # CRUDBase — 최소 CRUD (제네릭 ModelType)
│   │   │   └── repository_base.py  # BaseRepository — CRUD + eager-loading primitives
│   │   ├── services/services_base.py  # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py       # CORS 설정
│   │       ├── user_info_middleware.py  # 접속정보 수집(응답 후 백그라운드 저장)
│   │       ├── access_log_sink.py       # sink 프로토콜/전역 등록
│   │       └── background_tasks.py      # fire-and-forget 러너(백프레셔 + 종료 drain)
│   │
│   ├── celery/                     # 중앙 Celery (앱별 worker/ 없음)
│   │   ├── app.py                  # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── task.py                 # run_async() — 워커용 영속 이벤트루프 브릿지
│   │   └── tasks.py                # 중앙 태스크 정의
│   │
│   ├── domains/                    # 기능 단위 앱 (config.INSTALLED_APPS 에 이름 등록)
│   │   └── <name>/                 # home · blog · reply · sns · user
│   │       ├── api/routers/
│   │       │   ├── router.py        # <name>_router: APIRouter (컨벤션 진입점, /v1/<name> 프리픽스)
│   │       │   └── v1/<name>.py     # 버전별 엔드포인트
│   │       ├── models/models.py     # SQLAlchemy 모델 (Base + UUIDMixin/TimestampMixin)
│   │       ├── schemas/             # Pydantic 요청/응답 스키마
│   │       ├── services/            # 비즈니스 로직 (세션 주입)
│   │       ├── repositories/        # 데이터 접근 (BaseRepository 상속)
│   │       ├── dependencies/        # get_<name>_service (트랜잭션 경계: 성공 시 commit)
│   │       ├── admin.py             # admin_views: list[type] (선택, SQLAdmin)
│   │       ├── exceptions.py        # 도메인 예외 (선택)
│   │       └── tests/               # 도메인 테스트
│   │
│   └── utils/                      # 순수 유틸리티
│       ├── logs/                   # 구조화 로깅 (get_logger, setup_uvicorn_logging)
│       ├── authenticator/          # (플레이스홀더)
│       └── pagination.py           # Paginator + PaginatedResponse(dataclass)
│
├── migrations/env.py               # AppRegistry(discover+import_models)로 메타데이터 수집
├── scripts/new_app.py              # 앱 스캐폴딩 생성기
└── docs/                           # 문서 (이 파일 포함)
```

### 의존 방향

```
domains → core → utils
```

`domains`는 `core`(와 `utils`)를 사용하고, `core`는 절대로 `domains`를 import 하지 않는다.
도메인 간에도 하드 결합을 피한다(도메인 간 참조는 느슨한 문자열, FK/relationship 없음 → INSTALLED_APPS 탈착성 보존).

---

## 3. 수동 등록(Passive Registration) 아키텍처

자동 스캔(pkgutil/inspect)은 쓰지 않는다. 앱 목록은 `config.INSTALLED_APPS` 한 곳에 **명시적으로** 둔다.

### 3.1 SSOT — `config.INSTALLED_APPS`

```python
# config.py
INSTALLED_APPS: list[str] = ["home", "blog", "reply", "sns", "user"]
```

### 3.2 결선 — `AppRegistry` (app/core/registry.py)

`create_app()`이 아래 순서로 `AppRegistry`를 구동한다.

```
create_app()
 ├─ registry.discover()          # INSTALLED_APPS 읽고 각 app.domains.<name> 패키지 import(부수효과 실행)
 ├─ registry.import_models()     # 각 앱 models 패키지 import → Base.metadata 채움
 ├─ FastAPI(...) 생성 + 미들웨어(CORS, UserInfo) + 글로벌 예외핸들러 4종
 ├─ registry.install_routers(app)   # 각 앱 <name>_router 를 prefix "/api" 로 마운트
 ├─ _add_health_and_docs(app)       # /health, (DEBUG 시)/docs(Scalar)
 └─ if ADMIN: registry.install_admin(admin)  # 각 앱 admin.py 의 admin_views 등록
```

### 3.3 컨벤션 (`app/domains/<name>/`)

| 구성요소 | 위치 | 규칙 |
|---|---|---|
| 라우터 | `api/routers/router.py` | 모듈 레벨 `<name>_router: APIRouter` (내부에서 `/v1/<name>` 프리픽스) |
| 모델 | `models/` | import 시 `Base.metadata`에 테이블 등록 |
| Admin | `admin.py` | 모듈 레벨 `admin_views: list[type]` (선택) |
| 부수효과 | `__init__.py` | import-time 등록(예: home의 access-log sink) (선택) |

> 최종 경로 예: `install_routers`가 `user_router`를 `/api`에 마운트하고, `user_router`가 내부적으로 `/v1/user`를 더해 `→ /api/v1/user/users`.

---

## 4. 요청 처리 계층

```
HTTP 요청
  → Router (api/routers/v1)          # HTTP 역할만: 파라미터 수신 → 서비스 호출 → 응답 변환
  → Depends(get_<name>_service)      # 세션 주입 + 서비스 구성, yield 후 성공 시 session.commit()
  → Service (services/)              # 비즈니스 로직, 도메인 예외 발생
  → Repository (repositories/)       # BaseRepository CRUD/eager-loading
  → Database (async SQLAlchemy)
```

- **트랜잭션 경계**: 기능 의존성이 `yield` 후 `commit`. 예외 시에는 `get_session` teardown 이 `rollback`(UnitOfWork 미사용).
- **예외 처리**: `bootstrap`이 `AppException`/`RequestValidationError`/`StarletteHTTPException`/`Exception` 4종 글로벌 핸들러를 등록해 일관된 `ErrorResponse`로 변환(운영 모드에서는 상세 숨김).

---

## 5. 인프라 요약

- **DB 세션** (`core/db/session.py`): 메인/백그라운드 **분리 엔진**(풀 고갈 방지). `get_session`은 요청 스코프 세션 제너레이터, `background_session()`은 요청 밖(Celery/백그라운드) 컨텍스트.
- **접속 로그**: `UserInfoMiddleware`가 응답 후 정보를 수집해 `BackgroundTaskRunner`(백프레셔 상한 + 종료 시 drain)로 fire-and-forget 저장. lifespan shutdown 이 drain 후 엔진 dispose.
- **Celery** (`app/celery/`): 중앙 태스크 모듈. `run_async()`가 워커 프로세스당 영속 이벤트 루프를 재사용해 aiomysql 커넥션을 안전하게 다룬다.
- **마이그레이션** (`migrations/env.py`): `AppRegistry`로 모든 도메인 모델을 자동 수집해 autogenerate 가 누락 없이 동작. URL은 `ALEMBIC_DATABASE_URL`(예: sqlite) 우선, 없으면 `MYSQL_URL`의 드라이버를 `+pymysql`로 교체(Alembic은 동기 실행).
- **DEBUG 게이팅**: `DEBUG=true`면 시작 시 `create_all`로 테이블 자동 생성 + `/docs`(Scalar)·`/openapi.json` 노출. 운영은 Alembic + 문서 비노출.

---

## 6. 실행

개발 서버(로컬):

```bash
uv run uvicorn main:app --reload            # 또는: uv run python main.py
```

- `main.py` 진입점은 `app_settings.HOST`(기본 `127.0.0.1`)·`PORT`(기본 `8000`)를 사용한다. 외부/컨테이너 노출이 필요하면 `HOST=0.0.0.0`을 env로 주입한다.
- 로깅 설정은 `app.utils.logs.setup_uvicorn_logging()`을 사용한다.
