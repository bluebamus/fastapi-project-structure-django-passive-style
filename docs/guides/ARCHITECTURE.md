# 아키텍처 레퍼런스

이 문서는 **지금 코드가 어떻게 동작하는가**를 한곳에 모은 정본이다. 설치·실행은
[README](../../README.md), 새 기능을 만드는 방법과 규칙은 [개발 가이드](./DEVELOPMENT.md)가 맡는다.

- 기준: 2026-10-21 main `8553cdc`. 코드와 이 문서가 어긋나면 **코드가 정답**이고, 확인한 뒤 이 문서를 고친다.
- 폴더 트리는 README 의 [프로젝트 구조](../../README.md#프로젝트-구조)에만 둔다. 여기서는 모듈의 책임을 설명한다.
- 설정 → 기동 → 요청 → 종료를 코드 흐름대로 따라 읽는 요약은 [서버 수명주기 안내서](./workflows/server-lifecycle.html)다.
  표·수치(예산·기본값·순서)의 정본은 이 문서이고, 안내서는 이 문서와 어긋나지 않게 함께 고친다.
- 문서 전체 색인은 README 의 [문서 안내](../../README.md#문서-안내) 한 곳에 있다. `docs/guides/index.html` 은 브라우저에서 가이드로 들어가는 링크 목록일 뿐 색인이 아니다.
- 문서 정합성은 `tests/test_docs_consistency.py`·`tests/test_docs_references.py` 가 검사한다.

## 목차

0. [목적과 설계 원칙](#0-목적과-설계-원칙)
1. [모듈 경계와 계층](#1-모듈-경계와-계층)
2. [App Registry — Django 식 수동 앱 설치](#2-app-registry--django-식-수동-앱-설치)
3. [서버 수명주기와 설정](#3-서버-수명주기와-설정)
4. [요청·세션·트랜잭션](#4-요청세션트랜잭션)
5. [로깅](#5-로깅)
6. [접속 로그](#6-접속-로그)
7. [인증 (JWT)](#7-인증-jwt)
8. [관리 화면 (SQLAdmin)](#8-관리-화면-sqladmin)
9. [Celery](#9-celery)
10. [Alembic 마이그레이션](#10-alembic-마이그레이션)
11. [운영·보안과 알려진 제한](#11-운영보안과-알려진-제한)
12. [변경 이력](#12-변경-이력)

---

## 0. 목적과 설계 원칙

이 저장소는 **Django 식으로 앱을 수동 설치하고, URL 은 라우터 파일로 수동 관리하는
FastAPI 프로젝트 골격**이다. 한 문장으로 줄이면 다음과 같다.

> 앱의 설치 여부와 순서는 사람이 한 곳(`config.INSTALLED_APPS`)에서 명시하고,
> 설치된 앱 내부의 결선(Router·Models·Admin)은 컨벤션이 처리한다.

| 결정 | 주체 |
|---|---|
| 어떤 앱을, 어떤 순서로 설치할지 | 사람 — `config.INSTALLED_APPS` |
| 설치된 앱의 Router·Models·Admin 결선 | App Registry — `AppConfig` 컨벤션 |

### 0.1 원칙

- **설치는 목록에만 있다.** `app/features/` 에 디렉터리를 만드는 것으로는 아무 일도 일어나지 않는다.
  목록에서 빼면 디렉터리가 남아 있어도 route·registry 소유 모델·Admin·`ready()` 가 모두 빠진다.
  대가로 설치 범위를 한 곳에서 읽고, 로드 순서를 목록 순서로 통제하며, 실험 중인 앱을 비활성으로 둘 수 있다.
- **URL 은 라우터 파일 계층이 소유한다.** 프레임워크가 경로를 추론하지 않는다.

  ```text
  v1/<view>.py   엔드포인트 경로        /products
  router.py      버전·기능 prefix, tag  /v1/catalog, tags=["Catalog"]
  AppConfig      마운트 prefix          /api
    → /api/v1/catalog/products
  ```

- **기능 중심 구조.** 한 기능의 Router·Dependency·Service·Repository·Model·Schema·Admin·테스트는
  `app/features/<name>/` 안에 둔다. 기능 단위로 복사·삭제할 수 있어야 "탈착 가능한 앱"이 성립한다.
- **예측 가능한 트랜잭션 경계.** 커밋은 쓰기 핸들러 본문이 응답 전에 한 번 한다(§4.5).
  별도 UnitOfWork 계층은 두지 않는다.
- **조용한 실패 금지.** 선택 모듈 부재는 허용하지만, 모듈 안의 import 오류·공개 이름 누락·route 충돌은 기동 실패다.

### 0.2 의도적으로 택하지 않은 것

| 택하지 않은 것 | 이유 |
|---|---|
| 디렉터리 자동 스캔으로 앱 활성화 | 설치 범위와 순서가 파일 시스템 상태에 암묵적으로 끌려간다 |
| `main.py` 에 `include_router` 를 앱마다 나열 | 앱이 늘수록 `main.py` 가 모든 기능 추가의 공유 편집 지점이 된다(한때 이 방식으로 되돌렸다가 registry 로 복귀했다 — §12) |
| 기능 간 직접 import·FK·relationship 중심의 예제 | 앱 탈착성이 깨진다. 실제 제품에서 관계를 추가할 때는 앱 제거 가능성과 migration 순서를 함께 설계한다 |
| 관리 화면에 API 와 같은 JWT 를 쓰기 | 브라우저 화면은 서명 세션 쿠키가 표준이다. 대신 세션은 `/admin` 하위 앱에만 두고 API 인증과 섞지 않는다(§8) |
| 인메모리 레이트 리밋 | 워커별로 카운터가 갈라져 실질 한도를 보장하지 못했다. 필요하면 프록시·게이트웨이에서 건다 |

---

## 1. 모듈 경계와 계층

### 1.1 의존 방향

```text
features → core → utils
```

| 영역 | 역할 | 규칙 |
|---|---|---|
| `app/features/<name>/` | 기능 vertical slice | 비즈니스 코드는 전부 여기. 다른 기능을 import 하지 않는다 — 예외는 횡단 관심사인 `auth` 가 `user` 의 `User` 모델·Repository 를 쓰는 것 하나 |
| `app/core/` | 프레임워크 인프라 | 기능 구현을 직접 import 하지 않는다. 기능이 core 에 붙어야 하면 등록 훅을 쓴다(예: home 이 `set_access_log_sink()` 로 sink 등록). `Apps`·wiring adapter 만 설치 목록에 따라 기능 모듈을 동적으로 import 한다 |
| `app/utils/` | 순수 유틸(로그·인증·페이지네이션·검증) | 상위 계층에 의존하지 않는다 |

의존 방향은 `tests/test_layering_and_openapi.py` 가 AST 로 검사한다.

### 1.2 계층 책임

```text
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → AsyncSession → DB
     ↑ 쓰기면 await service.commit() 을 여기서
```

| 계층 | 하는 일 | 하지 않는 일 |
|---|---|---|
| Router(view) | HTTP 입력 검증·Service 호출·**커밋 시점 결정**·응답 DTO 변환·OpenAPI 메타데이터 | SQL, 도메인 규칙 |
| Dependency | 세션 종류 선택, `Service(session)` 조립 후 **return** | 비즈니스 실행, 커밋 |
| Service | 유스케이스·도메인 규칙, Repository 조합, 부재 → 기능 예외 변환 | FastAPI Request/Response 의존, SQL 문자열, 커밋 시점 결정 |
| Repository | 데이터 접근(ORM 또는 Raw), 필요 시 flush | 커밋, HTTP 상태 결정 |
| Model / Schema | 테이블 매핑 / 외부 입출력 계약 | 앱 조립 |

### 1.3 core 모듈 책임

| 모듈 | 책임 |
|---|---|
| `app/core/bootstrap.py` | `create_app()` factory, `lifespan`, 전역 예외 핸들러 5종, `/health`·`/ready`·Scalar `/docs` |
| `app/core/resources.py` | `manage_application_resources()` — Redis 검증, 개발용 테이블 생성, 종료 순서 |
| `app/core/apps/` | `AppConfig`·`Apps`·예외(Django lifecycle) + `wiring.py`(FastAPI·SQLAdmin adapter) |
| `app/core/db/session.py` | 엔진·세션 팩토리(엔진 옵션 정본 `session.ENGINE_SAFETY_OPTIONS`), 세션 Dependency, `background_session()`, `owned_tables()`, `create_db_tables()`, `ping_writer_db()`, `dispose_engine()` |
| `app/core/admin_filters.py` | 관리 목록 날짜 필터 `LocalDateFilter` — 지역 날짜를 UTC 범위로 바꿔 `UTCDateTime` 컬럼을 거른다(sqladmin 미의존, §8) |
| `app/core/db/router.py` | `DatabaseRouter`·`RoutingSession`, `using_writer`·`mark_read_only`·`is_read_only_session`, `read_intent`·`write_intent` |
| `app/core/db/errors.py` | `convert_db_error()` — DB 예외를 SQL·바인딩 값 없이 애플리케이션 예외로 변환 |
| `app/core/exception.py` | `AppException` 계층(`headers` 를 핸들러가 응답에 싣는다 — 429 `Retry-After`)과 `ErrorResponse` |
| `app/core/redis.py` | `get_redis()` 주입 provider, `ping_redis()`, 최소 버전 `redis.REDIS_MIN_VERSION`(7.0)·`ensure_redis_version()` |
| `app/core/security/` | 인증·인가 부품 `PasswordHasher`·`TokenService`·`RefreshTokenStore`·`RateLimiter`·`Principal`·`OwnershipPolicy`, 관리 세션 `admin_session.py`(`AdminSessionStore`·`RedisSessionMiddleware`, §8)와 주입 경로 `dependencies.py`(`get_current_principal`·`require_superuser`, §7·§7.1) |
| `app/core/models/models_base.py` | `Base` + `UUIDPrimaryKeyMixin`·`CreatedAtMixin`·`UpdatedAtMixin`·`TimestampMixin` |
| `app/core/repositories/` | ORM: `CRUDBase`·`BaseRepository` / Raw: `RawCRUDBase`·`RawRepositoryBase` (두 계열은 상속 관계가 없다) |
| `app/core/services/services_base.py` | `BaseService` — 세션 보관, `commit()`·`rollback()` 헬퍼 |
| `app/core/middlewares/` | CORS, `UserInfoMiddleware`, `AccessLogSink` Protocol, `BackgroundTaskRunner` |
| `app/core/tags_metadata.py` | OpenAPI 태그 선언(라우터 태그와 집합이 같아야 한다) |

---

## 2. App Registry — Django 식 수동 앱 설치

### 2.1 `config.INSTALLED_APPS`

```python
INSTALLED_APPS: list[str] = [
    "app.features.home.apps.HomeConfig",
    "app.features.blog.apps.BlogConfig",
    "app.features.reply.apps.ReplyConfig",
    "app.features.sns.apps.SnsConfig",
    "app.features.user.apps.UserConfig",
    "app.features.auth.apps.AuthConfig",
    "app.features.catalog.apps.CatalogConfig",   # ORM 예제
    "app.features.reports.apps.ReportsConfig",   # Raw SQL 예제
]
```

- 항목 형식은 Django 와 같다. **config class 경로**(권장)와 **package 경로**(`"app.features.blog"` →
  `blog.apps` 에서 기본 config 선택) 둘 다 받는다. 짧은 이름(`"blog"`)은 받지 않는다.
- **순서가 계약이다.** population·`ready()`·Router 등록·Admin view 등록이 모두 이 순서를 따른다. 새 앱은 뒤에 붙인다.
- 환경변수로 덮어쓰지 않는다. 설치 구성은 코드 리뷰 대상이다.
- 새 **프로세스**에서 목록에서 뺀 앱은 결선 대상에서 빠진다. 다만 같은 프로세스에서 이미 import 한 매핑 클래스는
  전역 `Base.metadata` 에 남는다. registry 를 새로 만들어도 SQLAlchemy metadata 가 청소되지는 않는다.

### 2.2 앱 패키지와 결선 컨벤션

```python
# app/features/<name>/apps.py
from app.core.apps import AppConfig


class <Name>Config(AppConfig):
    name = "app.features.<name>"
```

기능 root `__init__.py` 는 **가벼운 package marker** 다. Router 도 Model 도 import 하지 않는다 —
1단계(root package import)에서 하위 모듈이 딸려오면 3단계 순서가 무너진다.

| `AppConfig` 속성 | 기본값 | 의미 |
|---|---|---|
| `name` | (필수) | 앱 package 전체 경로 |
| `label` | `name` 의 마지막 조각 | 유일해야 하고 유효한 Python identifier 여야 한다 |
| `verbose_name` | label 의 title 표현 | 예: `SnsConfig` 는 `"SNS"` 로 재정의 |
| `default` | `None` | `<package>.apps` 에 config 가 여럿일 때 선택 표시 |
| `router_module` / `router_attribute` | `api.routers.router` / `<label>_router` | Router 결선 |
| `models_module` | `models` | 이 module 에 **노출된** 매핑 클래스 중 `__module__` 이 앱 하위인 것을 수집 — `models/__init__.py` 에서 재노출해야 한다 |
| `admin_module` | `admin` | 공개 이름 `admin_views` |
| `tasks_module` | `tasks` | Celery 태스크 module(선택). 워커 `include` 에 들어간다(§9) |
| `router_prefix` | `/api` | 마운트 prefix, 앱별 재정의 가능 |

| 구성요소 | module 이 없으면 | module 은 있는데 공개 이름이 없거나 내부 import 가 깨지면 |
|---|---|---|
| Router | route 없는 앱(정상) | 기동 실패 (`ImproperlyConfigured` / 원래 `ModuleNotFoundError`) |
| Models | 테이블 없는 앱(정상, 예: `auth`) | 기동 실패 |
| Admin | 관리 화면 없는 앱(정상) | 기동 실패 |
| Tasks | 태스크 없는 앱(정상) | 워커가 include 를 import 할 때 실패 — 발견은 `find_spec` 으로 존재만 본다(§9) |

### 2.3 3단계 population

```text
Apps.populate(INSTALLED_APPS)
  1) config/root package import   →  apps_ready = True
  2) models import                →  models_ready = True
  3) AppConfig.ready()            →  ready = True
```

- 단계는 **앱별이 아니라 phase 단위**다. 모든 앱의 1단계가 끝난 뒤 2단계로 간다 — 어떤 `ready()` 든 모든 앱의 모델을 볼 수 있다.
- 중복 항목, 중복 `name`, 중복 `label`, 잘못된 label, 해석할 수 없는 항목, `AppConfig` 가 아닌 class,
  기본 config 를 고를 수 없는 경우(복수 후보에 `default=True` 가 하나가 아님)는 `ImproperlyConfigured`.
- `populate()` 는 thread-safe(RLock)하고 멱등이다. 같은 목록으로 완료 후 재호출은 no-op, **다른 목록**이면
  `ImproperlyConfigured`(다른 구성은 새 `Apps()` 로 만든다), 진행 중 재진입은 `RuntimeError`
  (`ready()` 안에서 `populate()` 를 부르지 않는다). 실패하면 registry 상태를 되돌린 뒤 원래 예외를 전파한다 —
  단, 이미 import 된 Python 모듈과 전역 metadata 까지 되돌리지는 않는다.
- `populate(..., run_ready=False)` 는 1·2단계만 수행한다. Alembic·Celery 워커(`app/celery/app.py`)와 startup DDL 준비가 쓴다. 이후 같은 registry 에
  `run_ready=True` 로 다시 부르면 3단계만 실행된다.
- 조회 API: `get_app_configs()`, `get_app_config(label)`, `is_installed(name)`, `get_models()`,
  `get_model(app_label, model_name)`(대소문자 무시). 준비 전 조회는 `AppRegistryNotReady`, 없는 대상은 `AppLookupError`.
- 전역 기본 registry 는 `app.core.apps.apps`. 테스트와 factory 는 `Apps()` 를 새로 만들어 주입할 수 있다.

### 2.4 wiring adapter (`app/core/apps/wiring.py`)

| 함수 | 동작 |
|---|---|
| `install_routers(app, registry)` | 설치 순서대로 `<label>_router` 를 `router_prefix` 로 마운트. 두 앱이 같은 method + 최종 path 를 등록하면 `ImproperlyConfigured` 로 기동 실패(먼저 등록된 쪽이 조용히 이기지 않는다) |
| `install_admin(admin, registry)` | 설치 앱의 `admin_views` 를 선언 순서대로 `add_view` |
| `create_admin(app, engine, registry, title=...)` | **함수 안에서** `sqladmin` 을 import 하고, 슈퍼유저 로그인 백엔드(`AdminAuthBackend`)를 조립해 `Admin(authentication_backend=..., templates_dir=...)` 로 `/admin` 을 마운트(§8). `ADMIN_DISABLED=true` 프로세스는 이 함수를 부르지 않아 sqladmin 과 앱별 `admin.py` 를 로드조차 하지 않는다 |

`app/core/apps/config.py`·`registry.py` 는 FastAPI·SQLAdmin·SQLAlchemy 를 import 하지 않는다. Alembic·CLI 가
registry 를 써도 웹 스택이 딸려오지 않는다(`tests/core/apps/test_core_independence.py`,
`tests/core/test_admin_lazy_loading.py`).

### 2.5 `ready()` 의 제약

`ready()` 는 **process-local wiring 전용**이다.

- 허용: 모듈 전역 결선(예: `HomeConfig.ready()` 의 access-log sink 등록 — 현재 유일한 사용처), 다른 앱 모델 조회(`apps.get_model(...)`)
- 금지: DB 쿼리·커밋, network 호출, subprocess 실행, secret 출력

migration 과 CLI 도 이 hook 을 실행할 수 있기 때문이다(`alembic upgrade` 가 외부 연결을 만들면 배포가 예측 불가능해진다).
Alembic 은 `run_ready=False` 로 hook 자체를 건너뛴다. 회귀 가드는
`tests/core/apps/test_installed_apps.py` 의 `test_ready_hooks_perform_no_io`(구현을 AST 로 읽는다).

### 2.6 Django 호환 범위

기준: [Django 6.0 — Applications](https://docs.djangoproject.com/en/6.0/ref/applications/). "Django 식"이
어디까지 실제 호환이고 어디부터 이 프로젝트 확장인지 구분한다.

**동일** — app loading lifecycle 의 공개 의미를 보존한다.

| 항목 | Django | 이 프로젝트 |
|---|---|---|
| 설치 목록 | `settings.INSTALLED_APPS` | `config.INSTALLED_APPS` |
| 항목 형식 | package 경로 또는 `AppConfig` class 경로 | 동일 |
| 기본 config 선택 | `<package>.apps` 후보 0개 → 기본 `AppConfig`, 1개 → 그것, 복수 → 유일한 `default=True` | 동일 |
| 정규화 결과 | `name`·`label`·`verbose_name`·`path`·`module` | 동일 |
| 초기화 | config/root package → models → `ready()`, phase 단위, 목록 순서 | 동일 |
| 준비 상태 | `apps_ready`·`models_ready`·`ready` | 동일 |
| 고유성 | `name`·`label` 각각 유일 | 동일 |
| 조회 API | `get_app_configs`·`get_app_config`·`is_installed`·`get_models`·`get_model` | 동일(`get_model` 대소문자 무시) |
| 재진입 / 중복 populate | 금지 / no-op | `RuntimeError` / 같은 목록 no-op, 다른 목록 `ImproperlyConfigured` |

| Django 예외 | 이 프로젝트 (`app.core.apps.exceptions`) |
|---|---|
| `django.core.exceptions.ImproperlyConfigured` | `ImproperlyConfigured` |
| `django.core.exceptions.AppRegistryNotReady` | `AppRegistryNotReady` |
| `LookupError` | `AppLookupError` (`LookupError` 서브클래스) |

모든 registry 예외의 공통 base 는 `AppRegistryError` 다.

**확장** — Django 에는 없다. Django 기능이라고 부르지 않는다.

| 항목 | 동작 |
|---|---|
| Router 결선 | `router_module` 의 `<label>_router` 를 `router_prefix` 로 마운트, route 충돌 시 기동 실패 |
| Admin 결선 | `admin_module` 의 `admin_views` 를 SQLAdmin 에 등록(지연 import) |
| Model 수집 | SQLAlchemy 매핑 클래스 중 `__module__` 이 앱 package 하위인 것 |
| Alembic 통합 | `migrations/env.py` 가 같은 구현을 `run_ready=False` 로 사용 |
| `create_app()` | 설치 목록·registry·Admin 여부를 주입받는 factory |
| 선택 module 구분 | 부재는 허용, 내부 import 실패는 기동 실패 |

**비지원** — Django 코드를 옮겨도 동작하지 않는다.

| Django 기능 | 대체 |
|---|---|
| Django ORM·QuerySet·manager | SQLAlchemy 2.0 async |
| Django migration engine | Alembic |
| URLConf (`urls.py`, `path()`, `reverse()`) | FastAPI `APIRouter` |
| signals | 명시적 Service 호출 |
| template / static 자동 탐색 | 없음(API 전용) |
| management command 프레임워크 | `scripts/` 의 개별 스크립트 |
| `AppConfig.default_auto_field` | 모델이 직접 선언(`UUIDPrimaryKeyMixin`) |
| `apps.get_containing_app_config()` | 없음 |
| settings 분기에 따른 조건부 설치 | 없음 — 목록은 코드 리뷰 대상 |
| 앱 제거 시 데이터 migration 자동 생성 | 없음(§2.7) |

### 2.7 앱 비활성화·제거 시 주의

**목록에서 빼도 테이블은 지워지지 않는다.** 앱을 목록에서 빼면 route·Admin view·`ready()`·Celery 태스크(워커 `include`)는 즉시 사라지고,
깨끗한 migration 프로세스에서 그 앱의 모델이 수집 대상에서 빠진다 → `alembic revision --autogenerate` 가
DROP TABLE 을 **제안할 수 있다**. 데이터를 보존해야 하면 생성된 migration 을 그대로 적용하지 않는다.

```text
1. 앱을 목록에서 뺀다 → 테스트 → route/Admin 이 사라졌는지 확인
2. alembic revision --autogenerate 로 제안된 diff 를 읽는다
3. 데이터가 필요 없으면 그대로, 필요하면 편집하거나 별도 보존 절차를 만든다
4. alembic upgrade head
```

### 2.8 코드 주석의 요구 ID 색인

코드·테스트 주석의 `FR-*`·`CR-*`·`NFR-*`·`SEC-*`·`AC-*` 와 `§6.x` 는 registry 이식(2026-08-12) 때의 통합 계획서
번호다. 계획서는 구축 완료 후 커밋 `7dc527b` 에서 삭제했고(원문은 그 부모 커밋에 있다), 의미는 아래가 유지한다. `RAW-REP-*`·`NFR-0xx`·`DOC-*`·`development-plan §N`·`Phase N` 은
`docs/specs/orm-raw-repository/` 를, `ADR-*`·`C-*`·`F-*`·`L-*` 는 `docs/crp/groups/` 를 가리킨다.

| ID | 의미 |
|---|---|
| FR-01 | 설치 SSOT 는 `config.INSTALLED_APPS`. 디렉터리 존재만으로 활성화하지 않는다 |
| FR-02 / FR-03 | package 경로·config class 경로를 받아 `AppConfig`(name·label·verbose_name·path·module)로 정규화 |
| FR-04 | 설치 앱의 Router·Models·Admin 을 설정대로 결선, 구성요소 없는 앱 허용 |
| FR-05 | 조회 API 5종 제공 |
| FR-06 | 모델 import 와 Alembic metadata 가 같은 목록·같은 registry 구현을 쓴다 |
| FR-07 | `create_app()` 이 population → middleware → 예외 → Router → 조건부 Admin 순으로 조립 (§6.5) |
| FR-08 | `AppConfig.ready()` hook |
| FR-09 / FR-10 | 생성기가 `apps.py`·Router 골격을 만들고, 설정 파일은 고치지 않은 채 붙여 넣을 한 줄을 출력 |
| CR-01 / CR-02 | 기본 config 선택 규칙 / explicit class 검증 |
| CR-03 / CR-05 / CR-07 | 3단계 순서, 준비 flag 는 phase 완료 후, `ready()` 는 앱별 1회 |
| CR-04 / CR-06 | name·label 유일성과 identifier 검증 / 준비 전·조회 실패를 명시적 예외로 |
| CR-08 | Router·SQLAdmin 결선은 adapter 이며 Django 기능이라 부르지 않는다 |
| NFR-01 | 등록 순서가 결정적(파일 시스템 열거 순서에 의존하지 않음) |
| NFR-02 / NFR-04 | populate 는 thread-safe·멱등·재진입 거부 / 실패 시 부분 상태를 남기지 않음 |
| NFR-03 / NFR-07 | 모듈 부재와 내부 import 실패 구분(traceback 보존) / 오류 메시지에 고칠 위치 포함 |
| NFR-05 / NFR-06 | 격리 `Apps()` 주입 가능 / registry core 는 FastAPI·SQLAdmin 에 의존하지 않음 |
| NFR-08 | registry·adapter 커버리지 기준(프로젝트 전체 하한은 `pyproject.toml` `fail_under` 하나가 정본이고 CI·로컬 게이트가 함께 읽는다 — 기본 0 = 측정만, 필요해지면 그 값만 올린다) |
| SEC-01 | `ADMIN_DISABLED=true` 면 sqladmin·앱 `admin.py` 를 로드하지 않음 |
| SEC-02 | allowlist(`INSTALLED_APPS`)만 import, 디렉터리 스캔 금지 |
| SEC-03 / SEC-04 | 생성기 경로 이탈 차단 / 부분 생성·덮어쓰기 금지 |
| SEC-05 | `ready()` 에서 DB·network·subprocess·secret 출력 금지 |
| SEC-07 | 내부 import 실패를 선택 기능 부재로 위장하지 않음 |
| §6.7 | Alembic 은 `run_ready=False` 로 registry 를 채운다 |

| 인수 조건 | 검증 테스트 |
|---|---|
| AC-01 config 선택·정규화 | `tests/core/apps/test_config.py` |
| AC-02 population 순서 | `tests/core/apps/test_population_order.py` |
| AC-03 오류 종류·메시지 | `tests/core/apps/test_registry_errors.py` |
| AC-04 동시·재진입·멱등 | `tests/core/apps/test_registry_lifecycle.py` |
| AC-05 선택 module | `tests/core/apps/test_optional_modules.py` |
| AC-06 미등록 앱 비노출 | `tests/core/apps/test_manual_registration.py` |
| AC-07 Admin 지연 로드 | `tests/core/test_admin_lazy_loading.py` |
| AC-08 Admin 결선 | `tests/core/test_admin_wiring.py` |
| AC-09 runtime·Alembic 모델 동일 | `tests/core/test_alembic_metadata.py`, `tests/core/test_migration_chain.py` |
| AC-10 / AC-11 생성기 동작·경계 | `tests/scripts/test_new_app.py` |

---

## 3. 서버 수명주기와 설정

```mermaid
flowchart TD
    A["main:app import"] --> B["config.py — 설정 생성·검증"]
    B --> C["로깅·엔진 객체 준비 (아직 접속 아님)"]
    C --> D["create_app — registry population·미들웨어·예외·Router·/health·/ready·Admin"]
    D --> E["lifespan 진입 → manage_application_resources"]
    E --> F["Redis ping + 버전 >= 7.0 (실패 시 기동 중단)"]
    F --> G{"소유 테이블 > 0 이고 DEBUG?"}
    G -- 예 --> H["create_db_tables (개발용 DDL)"]
    G -- 아니오 --> I["DDL 생략"]
    H --> J["yield — 요청 처리"]
    I --> J
    J --> K["종료: background drain → Redis close → DB dispose"]
```

### 3.1 진입점과 프로세스 경계

- `main.py` 는 `app = create_app()` 과 직접 실행용 `uvicorn.run()` 만 둔다. 직접 실행(`uv run python main.py`)은
  `SERVER_HOST`·`SERVER_PORT`·`reload=DEBUG`·`setup_uvicorn_logging()` 을 넘긴다. `uvicorn main:app` CLI 는
  CLI 옵션을 따르며 `DEBUG=true` 만으로 reload 가 켜지지 않는다.
- 두 경로 모두 정상 ASGI lifespan 을 탄다. `--lifespan off` 는 Redis 검증·자원 정리를 건너뛰므로 정상 경로가 아니다.
- reload·다중 worker 는 프로세스마다 import·lifespan 을 다시 수행한다. API worker 마다 Redis client 와 DB pool 이 따로 있고,
  Celery worker 는 별도 프로세스다.
- factory 로 만든 이유는 테스트가 **격리된 앱**(auth 를 뺀 앱, 관리 화면을 끈 앱, 독립 registry 앱)을 만들어
  "등록 안 한 앱은 안 붙는다"를 실행으로 증명하기 위해서다.

### 3.2 설정 로딩

`config.py` 의 각 `BaseSettings` 는 `env_file=".env"`, `extra="ignore"` 로 **자기 필드만** 해석한다.

- 우선순위: 프로세스 환경변수 → **작업 디렉터리의** `.env` → 필드 기본값. `.env.example` 은 복사용 목록이며 자동 fallback 이 아니다.
- 리스트 값은 JSON 배열로 준다(예: `CORS_ALLOW_ORIGINS=["http://localhost:3000"]`). `DEBUG=false` 는 bool 로 파싱된다.
- `get_*_settings()` 는 `lru_cache` 싱글턴이고, 모듈 끝의 `app_settings` 등 전역 참조가 import 시 만들어진다.
  실행 중 `.env` 를 바꿔도 반영되지 않는다. 테스트에서 캐시를 비워도 이미 가져간 전역 참조는 바뀌지 않는다.
- 타입 오류·validator 위반은 `config` import 자체를 실패시킨다(lifespan 이전).

| 설정 클래스 (전역 인스턴스) | 소비처 |
|---|---|
| `TimezoneSettings` (`timezone_settings`) | 모델 시각 기본값, 로그 시각, Celery timezone |
| `AppSettings` (`app_settings`) | 앱 메타데이터, `DEBUG`·`ENV`·`ADMIN_DISABLED`, 직접 실행 host/port |
| `DatabaseSettings` (`db_settings`) | DSN·라우팅·풀, `session.py`, Alembic URL |
| `CORSSettings` (`cors_settings`) | `CustomCORSMiddleware` |
| `LogSettings` (`log_settings`) | `build_dictconfig()` — 앱·`python main.py`·`uvicorn main:app` CLI·Celery 워커가 함께 쓴다 |
| `MiddlewareSettings` (`middleware_settings`) | `UserInfoMiddleware` 활성·제외 규칙·민감 query 키, `ClientIPResolver` 신뢰 홉 수 |
| `RedisSettings` (`redis_settings`) | startup Redis ping, `/admin` 서버 세션, refresh 토큰 회전 기록, 레이트 리밋, Celery broker/backend (일반 캐시는 없다) |
| `JWTSettings` (`jwt_settings`) | 토큰 서명·검증·수명 |
| `SessionSettings` (`session_settings`) | `SESSION_COOKIE_NAME` 은 접속 로그 미들웨어가 읽는다(그 쿠키 값을 `session_id` 로 기록, 인증에는 쓰지 않는다). `SESSION_SECRET_KEY` 는 `/admin` 관리 세션 ID 를 Redis 키(`admin:sess:{HMAC}`)로 바꾸는 HMAC 키다(§8). 관리 세션 만료는 `ADMIN_SESSION_*` 가 정한다(미사용이 절대보다 크면 기동 실패, 값은 [README 세션·토큰 만료](../../README.md#세션토큰-만료)) |

API 버전 prefix(`/v1`)는 설정이 아니라 각 기능 `router.py` 가 정한다 — 버전 설정 클래스는 config-cleanup-2 에서 지웠다(`.env` 에 남은 줄은 무시된다, §12).

**설정 검증(fail-fast)**

| 검증 | 거부 조건 |
|---|---|
| `DatabaseSettings._validate_routing` | 복제 on + 라우터 off, 복제 on + replica 목록 비어 있음, 잘못된 replica 표기(IPv6 는 대괄호 필수), `DB_MAX_SERVER_CONNECTIONS` 가 0이 아닐 때 최대 연결 수 초과 |
| `CORSSettings._reject_wildcard_with_credentials` | Origin `*` 와 `CORS_ALLOW_CREDENTIALS=true` 조합 |
| `LogSettings` field validator 3종 | `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT` 이 샘플 레코드로 렌더되지 않거나 필수 필드가 빠짐, `LOG_APP_LEVELS` 해석 실패, 빈 `LOG_DATE_FORMAT` |
| `SessionSettings._validate_admin_session_expiry` | `ADMIN_SESSION_IDLE_SECONDS` > `ADMIN_SESSION_MAX_AGE_SECONDS` |
| `_validate_cross_settings()` | production/staging 에서 `LOG_SQL_ECHO_ENABLED=true` |
| `validate_removed_settings()` | 예전 `ADMIN` 설정이 환경 변수나 `.env` 에 남아 있다(대소문자 무시) — 뜻이 뒤집혀 `ADMIN_DISABLED` 로 바뀌었으므로 조용히 무시하지 않는다. test 는 검사하지 않는다 |
| `validate_env_source()` | `.env` 가 없으면 필수 값(`ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE`)이 환경 변수로 모두 있어야 한다. 컨테이너 주입은 통과. test 는 검사하지 않는다 |
| `validate_deployment_safety()` | test 외 모든 ENV(개발 포함)에서 `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY`·`MYSQL_PASSWORD` 중 placeholder(빈 값·`your-` 시작·`change-this` 포함)가 있거나, 비밀 키 3종이 32자 미만이거나, access 키 = refresh 키. `REDIS_PASSWORD` 는 **값이 있을 때만** 같은 판정을 받는다(인증 없는 Redis 는 정당한 구성이라 빈 값을 막지 않는다). **또는** production/staging 에서 `DEBUG=true` 이거나 `LOG_LEVEL` 이 `DEBUG`(대소문자 무시) — 유효 로그 레벨이 DEBUG 면 세션 롤백 경로가 SQL·바인딩 값·트레이스백 전문을 남긴다(§5). 위반을 한 번에 모아 `ValueError` 로 알리고 메시지에는 설정 **이름만** 담는다(값은 싣지 않는다). test 는 검사하지 않는다 |

`_validate_cross_settings()`·`validate_env_source()`·`validate_removed_settings()`·`validate_deployment_safety()` 는 모듈 함수라 `config` import 시점에 차례로 실행된다 — 호출을 빠뜨릴 수 없다.
배포 환경에서 관리 화면을 켜는 것은 더 이상 거부하지 않는다 — `/admin` 은 슈퍼유저 로그인이 필요하다(§8). 쓰지 않는 배포는 `ADMIN_DISABLED=true`.

**주요 환경변수** (전체 목록과 설명은 `.env.example`)

| 변수 | 기본값 | 효과 |
|---|---|---|
| `DEBUG` | `true` | true: 개발용 테이블 자동 생성, `/docs`·`/openapi.json` 노출, 미지정 로그 레벨 DEBUG, 직접 실행 시 reload. false: 모두 반대(로그 INFO, 스키마는 Alembic) |
| `ADMIN_DISABLED` | `false` | false: `/admin` 마운트(슈퍼유저 로그인 필요, §8). true: 관리 화면 자체가 없다 — 마운트·sqladmin import·세션 미들웨어·인증 백엔드가 생기지 않고 응답 어디에도 경로가 나오지 않는다. `DEBUG` 와 독립 |
| `ENV` | `development` | development / staging / production / test. 로그 핸들러·타임존과 위 검증에 쓰인다 |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | 직접 실행 시 바인딩 |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `3306` / `root` / 빈 값 / `fastapi_db` | primary(writer) DSN |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` | `false` / `false` | 읽기/쓰기 라우팅(§4.4) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `localhost` / `6379` / `0` / 없음 | startup ping 대상이자 Celery broker/backend |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | JWT 서명 키(§7). test 외 모든 ENV 에서 placeholder·32자 미만·동일 키 거부 |
| `SESSION_SECRET_KEY` | `change-this-...` | `/admin` 관리 세션 ID → Redis 키 HMAC 키(§8). 바꾸면 모든 관리 세션이 무효. test 외 모든 ENV 에서 placeholder·32자 미만 거부 |

세션·토큰 만료(`ADMIN_SESSION_*`·`ACCESS_TOKEN_EXPIRE_MINUTES`·`REFRESH_TOKEN_EXPIRE_DAYS`)는 [README 세션·토큰 만료](../../README.md#세션토큰-만료) 표 한 곳에 모았다.

### 3.3 `create_app()` 조립 순서

```python
def create_app(installed_apps=None, registry=None, *, admin_disabled=None) -> FastAPI: ...
```

1. 설치 목록 결정(`config.INSTALLED_APPS` 또는 주입값), registry 결정(전역 `apps` 또는 주입값)
2. `registry.populate(apps_list)` — config → models → `ready()`
3. `FastAPI(...)` 생성 — `docs_url=None`, `redoc_url=None`, `openapi_url` 은 `DEBUG` 일 때만 `/openapi.json`, `lifespan` 연결
4. CORS → `UserInfoMiddleware` 등록(나중에 추가한 UserInfo 가 바깥쪽에서 감싼다), 전역 예외 핸들러(Redis 연결·타임아웃 → 503, `AppException`, 요청 검증 422, Starlette `HTTPException`, `Exception` → 500)와 그 바깥의 `answer_unhandled_exception` 미들웨어(처리기 없는 예외를 500 으로 끝낸다, `DEBUG=true` 면 다시 던진다), OpenAPI 의 422 를 실제 본문 `ErrorResponse` 로 광고하는 후처리(`_document_real_validation_error`)
5. `install_routers(app, registry)`
6. `/health`, `/ready`, `DEBUG` 일 때만 Scalar `/docs`
7. `app.state.app_registry` 저장, `admin_disabled`(기본 `ADMIN_DISABLED`)가 false 면 `create_admin(...)` — 끈 경우 로그에도 경로를 싣지 않는다
8. `AccessPolicyGuard().verify(app)` — 접근 수준을 선언하지 않은 API 라우트가 있으면 기동을 멈춘다(라우트가 모두 붙은 뒤라야 빠짐없이 본다)

2번이 3번보다 먼저인 이유는 모델·hook 등록을 앱 조립 전에 끝내기 위해서다.

### 3.4 lifespan 과 자원 관리

`lifespan` 은 `manage_application_resources(app)` 를 열고 yield 할 뿐이다. 자원별 코드는 `app/core/resources.py` 한 곳에 있다.

```python
async with AsyncExitStack() as cleanup:
    cleanup.push_async_callback(_dispose_db_engines)       # 종료 시 3번째
    await cleanup.enter_async_context(_redis(app))         # 종료 시 2번째
    cleanup.push_async_callback(_drain_background_tasks)   # 종료 시 1번째
    await _prepare_database(resources, app.state.app_registry)
    yield resources
```

**Redis 검증** — `Redis.from_url(redis_settings.REDIS_URL, socket_connect_timeout=5, socket_timeout=5)` 후 `ping()`.
실패하면 오류 타입만 ERROR 로 남기고 다시 raise 한다 → yield 에 도달하지 않아 서버가 시작되지 않는다.
이어서 `ensure_redis_version()`(`app/core/redis.py`)이 `INFO server` 의 `redis_version` 을 `redis.REDIS_MIN_VERSION`(**7.0**)과 비교해
낮으면 `UnsupportedRedisVersion` 으로 기동을 멈춘다. 7.0 은 근거가 있는 값이다 — 레이트 리밋이 `EXPIRE … NX`(7.0)를, refresh 회전이
GETDEL(6.2)을 쓰고 최소 버전은 그 최댓값이다(6.x 서버는 `EXPIRE NX` 를 문법 오류로 거부해 로그인·가입이 첫 요청부터 500).
INFO 를 막아 둔 관리형 Redis·버전을 알려 주지 않는 서버(테스트의 fakeredis 포함)는 WARNING 만 남기고 계속한다.
`tests/core/test_redis_version.py` 가 소스의 명령과 상수를 대조한다.
`DEBUG` 와 무관한 필수 조건이며 끄는 설정은 없다(service-hardening ADR-011). 성공한 client 는 `app.state.redis` 에 보관되고,
요청 코드는 주입 provider `get_redis(request) -> Redis`(`app/core/redis.py`) 하나로 꺼낸다 — lifespan 밖이라 client 가 없으면
`ServiceUnavailableException`(503). 기능이 `Redis.from_url` 을 직접 만들지 않는다. 기동 뒤의 도달 가능성은 `/ready` 가 다시 본다(§3.5).
기동 뒤 Redis 가 사라지면 Redis 를 필수로 쓰는 요청은 503(SERVICE_UNAVAILABLE) 이다(§3.5 예외 표, fail-closed). Redis 를 쓰지 않는
조회(예: 글 목록)는 영향이 없고, 재기동하면 다시 연결된다(연결 풀이 재접속한다 — e2e L5 가 확인).

**개발용 테이블 생성** — `_prepare_database()` 는 `create_app()` 이 조립에 쓴 registry(`app.state.app_registry`)를
받아 `owned_tables(registry)` 로 **그 registry 가 소유한 테이블만** 센다. 전역 `apps` 를 따로 읽거나 다시 채우지 않는다.

| 조건 | 동작 |
|---|---|
| 소유 테이블 0개 | DB 에 접속하지 않는다 |
| `DEBUG=false` | 생성하지 않는다(Alembic 사용) |
| `DEBUG=true` | `create_db_tables(registry=registry, populate=False)` — writer `engine.begin()` 안에서 `Base.metadata.create_all(tables=소유 테이블)`, 30초 timeout |

`create_all` 은 없는 테이블만 만든다. 컬럼 변경·삭제·데이터 이동은 하지 않으며 DB 자체와 계정 권한은 미리 있어야 한다.
여러 worker 가 `DEBUG=true` 로 동시에 DDL 을 시도할 수 있으므로 운영은 `DEBUG=false` + 별도 migration 주체가 원칙이다.

> **custom factory** — `create_app(installed_apps, registry)` 로 조립하면 route 집합과 startup DDL 집합이 같은 registry 에서
> 나온다(`tests/core/test_bootstrap.py::test_lifespan_creates_only_the_injected_registrys_tables`, service-hardening F-012).

**종료** — background task drain → Redis `aclose()` → DB engine dispose.

| 단계 | 예산 | 비고 |
|---|---|---|
| background drain | 5초 | 그중 4초는 완료 대기, 남은 시간에 미완료 태스크를 cancel 후 gather 로 회수 |
| Redis close | 5초 | client pool 정리일 뿐 서버·키에 영향 없음 |
| DB dispose | 10초 | writer · replica · background 를 `asyncio.gather(..., return_exceptions=True)` 로 **병렬** 회수. 한 엔진이 실패해도 나머지는 끝까지 dispose 되고, 실패는 예외 **타입만** 로그로 남기고 올리지 않는다(원래의 종료 원인을 덮지 않도록) |

각 단계는 `_run_cleanup()` 이 감싸 실패·timeout 을 로그로 남기고 다음 단계로 넘어간다(전체 deadline 은 없다).
startup ping 실패도 client 종료와 이미 등록된 DB 정리 경로를 탄다(background drain 은 아직 등록 전). 끝나면
`app.state.resources` 를 `None` 으로 되돌린다. SIGKILL·강제 종료에서는 회수를 보장하지 않는다.
logging 은 console/file 핸들러를 직접 붙이는 구조라 닫을 queue listener 가 없다.

### 3.5 health · ready · 오류 응답

| 경로 / 오류 | 의미 |
|---|---|
| `GET /health` | liveness. `{"status": "healthy", "version": VERSION}`. DB·Redis 를 보지 않는다 — liveness 가 DB 에 의존하면 DB 가 흔들릴 때 오케스트레이터가 멀쩡한 프로세스를 죽인다 |
| `GET /ready` | readiness. `ping_writer_db()`(writer 에 `SELECT 1`)와 `ping_redis()`(`get_redis` 로 주입한 client 에 `ping()`)를 `asyncio.gather` 로 동시에, 각각 2초 안에 실행. 하나라도 실패·timeout 이면 원인을 숨긴 503(대상과 원인 타입만 서버 WARNING — 예: `[Readiness] Redis 준비 확인 실패: TimeoutError`). 준비 안 된 인스턴스는 재시작이 아니라 LB 에서 뺀다 |
| `/docs`, `/openapi.json` | `DEBUG=true` 일 때만. Swagger UI·ReDoc 은 끔 |
| 설정·registry 오류 | lifespan 이전 조립 실패 |
| Redis ping·Redis 7.0 미만·개발 DDL 오류 | startup 실패 |
| 요청 중 오류 | 전역 예외 핸들러 |
| background 저장 오류 | 이미 나간 응답과 무관(로그만) |

전역 핸들러 5종은 모두 `ErrorResponse{error_code, message, detail}` 로 응답한다.

| 예외 | 처리 |
|---|---|
| `AppException` 계열 | 예외의 status·error code 유지 (`NotFoundException` 404, `DuplicateException` 409, `DatabaseException` 500 등 — `app/core/exception.py`). 로그는 status < 500 이면 WARNING(detail 제외), 500 이상이면 ERROR |
| `RequestValidationError` | 422 VALIDATION_ERROR, detail 에 field·message·type 목록. OpenAPI 도 모든 operation 의 422 를 같은 `ErrorResponse` 로 광고한다 — FastAPI 기본 `HTTPValidationError` 는 `create_app()` 의 OpenAPI 후처리 한 곳에서 걷어낸다(`_document_real_validation_error`, integration-e2e ADR-012 결정 1) |
| Redis 연결 오류(`redis.exceptions.ConnectionError`·`TimeoutError`) | 503 SERVICE_UNAVAILABLE, detail 없음. **예외 클래스 전용** 핸들러라 응답 뒤 예외를 다시 던지지 않는다 — traceback 은 ERROR 로 **한 번**, keep-alive 연결도 유지된다(`Exception` 핸들러로 가면 Starlette `ServerErrorMiddleware` 가 다시 던져 traceback 이 두 번 남고 uvicorn 이 연결을 끊는다). 대상: 가입·로그인(레이트 리밋), refresh·logout(회전 기록), 사용자 비활성화·강등·삭제(세션 폐기 — 실패하면 커밋하지 않는다). `ResponseError` 같은 명령 오류는 결함이라 500 그대로 (integration-e2e ADR-009) |
| Starlette `HTTPException` | `HTTP_<status>` error code. 예외의 `headers` 는 응답에 그대로 싣는다(405 `Allow` 등). `AppException` 도 `headers` 를 싣는다(429 `Retry-After`). **401 은 두 핸들러가 모두 `WWW-Authenticate: Bearer` 를 붙인다**(`_challenge` 한 곳 — 보호 라우트·로그인·refresh·logout·비활성 사용자 `/me` 모두, integration-e2e ADR-012 결정 3) |
| 그 밖의 예외 | 500 INTERNAL_SERVER_ERROR, **DEBUG 에서도 detail 은 비운다**. SQLAlchemy 예외는 traceback 없이 타입·드라이버 코드만 로그. 사용자 미들웨어 중 가장 바깥의 `answer_unhandled_exception` 이 같은 처리기로 응답을 끝내 Starlette `ServerErrorMiddleware` 의 재던짐을 막는다 — 기록은 **한 번**, keep-alive 연결 유지, CORS·UserInfo 미들웨어 안에서 난 예외도 같다. `DEBUG=true` 면 지금처럼 다시 던진다. 응답이 시작된 뒤(스트리밍 본문 중)의 예외는 이 미들웨어에 오지 않아 기존대로다(integration-e2e ADR-012 결정 2) |

---

## 4. 요청·세션·트랜잭션

### 4.1 요청 흐름

```mermaid
sequenceDiagram
    participant C as Client
    participant M as Middleware
    participant R as Router
    participant D as Dependency
    participant S as Service
    participant P as Repository
    participant DB as Database
    C->>M: HTTP request
    M->>M: UserInfo 수집 · CORS
    M->>R: 설치된 route
    R->>D: get_<name>_service(_readonly)
    D-->>R: Service(session)
    R->>S: 유스케이스
    S->>P: 데이터 접근
    P->>DB: SQL / flush
    opt 쓰기
        R->>S: await service.commit()
    end
    R-->>C: 응답 DTO
    M-->>M: 접속 로그 태스크 spawn (별도 풀)
```

1. `UserInfoMiddleware` 가 활성·제외 규칙을 보고 요청 정보를 수집한다. CORS 가 preflight·헤더를 처리한다.
2. registry 가 설치한 route 가 선택되고 FastAPI 가 path/query/body/form/header 와 Dependency 를 검증·해석한다.
3. Dependency 그래프: 세션 generator → `get_<name>_service` → `Service(session)` → Repository.
4. 쓰기 핸들러는 업무 후 `await service.commit()` 을 부르고 응답을 만든다. 조회는 커밋하지 않는다.
5. 예외로 빠져나가면 세션 컨텍스트(`async with`)의 `close()` 가 활성 트랜잭션을 롤백하고 예외는 그대로 재전파되며, 전역 핸들러가 오류 응답을 만든다.
6. 미들웨어가 응답 상태·소요 시간을 붙여 접속 로그 저장 태스크를 제출한다(§6).

FastAPI 는 한 요청 안에서 같은 Dependency 를 기본 캐시(`use_cache=True`)한다. writer getter 와 read-only getter 는
서로 다른 callable 이라 같은 세션이 아니다. Service 를 전역 싱글턴으로 두면 세션이 요청을 넘나들므로 금지한다.

### 4.2 세션 API

| API | 용도 | 특성 |
|---|---|---|
| `get_read_only_db_session()` | 조회 endpoint (기능 앱 표준) | 세션을 read-only 로 표시 → 쓰기 차단(라우터 설정과 무관). 라우터 활성 시 replica 고정. 예외 시 rollback |
| `get_writer_db_session()` | 쓰기 endpoint (기능 앱 표준) | 첫 구문부터 writer 고정. 예외 시 rollback |
| `get_routed_db_session()` | 의도를 미리 정할 수 없는 예외 경로 | 구문 성격으로 자동 라우팅. 기능 앱은 쓰지 않는다 |
| `background_session()` | 요청 밖(sink·Celery) async context | background 풀, 예외 시 rollback, **커밋은 호출자** |
| `get_background_session()` | 요청 밖 generator 방식 | background 풀, 예외 시 rollback |

세션 팩토리는 `expire_on_commit=False`, `autoflush=False` 다. `session.add` 는 메모리 등록이라 동기, `flush`·`refresh`·`execute`·`commit` 은 await 한다.

### 4.3 엔진과 연결 예산

| 엔진 | 풀 (기본값) | 용도 |
|---|---|---|
| `engine` (= `writer_engine`) | `DB_POOL_SIZE` 20 + `DB_MAX_OVERFLOW` 20, timeout 30초 | 요청 처리·DDL·readiness·SQLAdmin |
| `read_engines` | replica 마다 writer 와 같은 크기 | 복제 활성 시 SELECT |
| `background_engine` | `DB_BACKGROUND_POOL_SIZE` 10 + `DB_BACKGROUND_MAX_OVERFLOW` 10, timeout 60초 | 접속 로그·요청 밖 작업, 라우팅 없이 primary |

모든 엔진은 `pool_pre_ping`, `pool_recycle=DB_POOL_RECYCLE`(280초 — DB/프록시 `wait_timeout` 보다 짧게),
반환 시 rollback, `connect_timeout` 10초, utf8mb4 를 쓴다. 엔진 생성은 import 시점이지만 **실제 연결은 첫 사용 때**다.
드라이버 의존성은 `aiomysql[rsa]` 다 — 함께 오는 `cryptography` 가 MySQL 8.4 `caching_sha2_password` 의 TLS 아닌 전체 인증(RSA)을 처리한다. 없으면 인증 캐시가 빈 첫 접속이 실패한다.

모든 엔진(writer·reader·background, Alembic 의 `engine_from_config` 포함)은 `session.ENGINE_SAFETY_OPTIONS` 를 펼쳐 받는다 — 지금은
`hide_parameters=True` 하나다. DB 오류(`IntegrityError` 등)의 메시지와 SQLAlchemy 로그에서 **바인드 값**(이메일·비밀번호 해시·토큰)이
빠지고 SQL 문과 `[SQL parameters hidden due to hide_parameters=True]` 만 남는다. 새 엔진을 만들면 같은 옵션을 넣는다 —
`tests/core/test_engine_hide_parameters.py` 가 모든 생성 지점을 AST 로 확인한다(security-ops-hardening ADR-001).

최대 연결 수(`db_settings.max_total_connections`)는 프로세스마다 다음과 같고 `DB_WORKER_PROCESSES`(uvicorn + celery worker 수)를 곱한다.

```text
(DB_POOL_SIZE + DB_MAX_OVERFLOW) × (1 + 복제 활성 시 replica 수) + (DB_BACKGROUND_POOL_SIZE + DB_BACKGROUND_MAX_OVERFLOW)
```

`DB_MAX_SERVER_CONNECTIONS` 를 주면 이 값이 넘칠 때 기동이 실패한다(0 이면 검증하지 않음).

### 4.4 읽기/쓰기 라우팅

`DB_ROUTER_ENABLED=false`(기본)면 세션이 writer 엔진에 직접 바인딩되고 바인딩 선택은 쓰이지 않는다.
켜면 `RoutingSession.get_bind()` 가 구문마다 엔진을 고른다. read-only 세션의 쓰기 차단은 이 설정과 무관하다(아래 "read-only 차단의 범위").

```mermaid
flowchart TD
    A[구문] --> B{ORM flush 또는 Core DML?}
    B -- 예 --> W[writer + 이후 sticky]
    B -- 아니오 --> T{TextClause?}
    T -- 예 --> I{read 의도가 붙었나?}
    I -- 아니오 --> W
    I -- 예 --> P
    T -- 아니오 --> P{writer 고정 세션?}
    P -- 예 --> W2[writer]
    P -- 아니오 --> R[세션에 고정된 replica<br/>없으면 writer]
```

- 쓰기 판정 시 세션이 read-only 로 표시돼 있으면 `ReadOnlyRoutingError`.
- `DB_READ_STICKY_AFTER_WRITE=true`(기본)면 쓰기 이후 같은 세션의 SELECT 는 writer 로 간다(read-after-write).
  새 요청의 read-only 세션까지 복제 지연을 없애 주지는 않는다.
- 한 세션은 라운드로빈으로 고른 replica 하나에 고정된다(트랜잭션이 여러 서버로 흩어지지 않도록).
- **replica 장애 → primary 로 한 번 재시도**(integration-e2e ADR-010): **읽기 전용 세션**의 읽기가 replica 에 **연결하지 못하면**
  (MySQL 2002·2003 접속 불가, 2006·2013·2055 연결 끊김, 1053 종료 중, 3032 `offline_mode`, 4031 유휴 끊김, 또는 SQLAlchemy 가
  연결 무효화로 표시한 오류) 같은 구문을 primary 로 한 번 다시 실행하고 WARNING `[DBRouter] replica 연결 오류 — primary 로 다시
  읽는다 (<예외 종류>, driver_code=<코드>)` 를 남긴다(DSN·메시지는 싣지 않는다). 그 뒤 그 세션은 writer 에 고정된다. 쿼리 자체의
  오류(문법·제약·없는 테이블)는 재시도하지 않는다. 쓰기와 섞일 수 있는 일반(라우팅) 세션도 재시도하지 않는다. primary 도 실패하면
  그 오류가 그대로 올라간다. replica 가 없는 구성은 동작 변화가 없다. `/ready` 는 그대로 writer 만 본다.
- `DB_REPLICATION_ENABLED=true` 는 `DB_ROUTER_ENABLED=true` 와 `MYSQL_REPLICA_HOSTS` 를 요구한다. replica 계정·DB 를
  비우면 primary 값을 재사용한다. replica 없이 라우터만 켜면 읽기도 writer 로 간다.
- 복제 지연을 허용할 수 없는 읽기는 `using_writer(session)` 으로 writer 에 고정한다.
- 기동 시 `db_settings.describe_routing()` 이 비밀번호를 가린 DSN(`URL.render_as_string(hide_password=True)`)으로 구성을 한 줄 남긴다.

**`text()` 는 SQL 을 해석하지 않는다.** 첫 단어 파싱은 `WITH doomed AS (SELECT ...) DELETE ...` 같은 CTE DML 을 읽기로
오판해 replica 로 보낸다. 그래서 호출부가 의도를 붙이고(`read_intent`·`write_intent`, 조회는 `statement_intent`),
**의도가 없는 `TextClause` 는 쓰기로 본다**(fail-closed). `RawRepositoryBase` 를 쓰면 메서드가 의도를 자동으로 붙인다.

**read-only 차단의 범위**

| 경로 | 차단 |
|---|---|
| ORM flush | `Session` 에 전역 등록된 `before_flush` 리스너가 거부 — 라우터 설정·sessionmaker 종류와 무관 |
| Core DML·임의 `session.execute()` | `do_orm_execute` 리스너가 **실행 전에** 판정 — 잠금 없는 `Select` 와 `read_intent()` 가 붙은 `text()` 만 통과하고 나머지는 거부(default-deny). ORM `with_for_update()` 는 쓰기로 보고 거부하며, 라우터는 writer 로 보낸다 |
| Raw 쓰기(`execute`, `for_update=True`) | 위 리스너에 더해 `RawCRUDBase` 가 `is_read_only_session()` 으로 먼저 거부 — 어느 메서드가 원인인지 메시지에 남는다 |

판정은 구문 타입과 의도 태그만 본다 — SQL 문자열을 해석하지 않으므로 완전한 sandbox 가 아니다. 위 세 경로의 차단은 라우터 on/off 두 구성에서 `tests/core/test_read_only_guard.py` 가 고정하고, 조회 경로가 쓰지 않는다는 규칙은 `tests/test_read_path_no_commit.py` 가 구조로 함께 고정한다.

read-only 표시는 DB 권한을 대체하지 않는다. 운영에서는 replica 전용 읽기 계정을 함께 쓴다.

### 4.5 트랜잭션 경계

- **커밋은 쓰기 핸들러 본문이 응답 생성 전에 한 번.** Repository·Service·Dependency 는 스스로 커밋하지 않는다.
- 순서는 `response = XResponse.model_validate(obj)` → `await service.commit()` → `return response` 하나다. 응답 DTO 검증이
  실패하면 커밋 없이 500 으로 끝나고 세션 Dependency 가 rollback 한다(`tests/test_validate_before_commit.py`).
- 예외로 빠져나가면 세션 Dependency 가 rollback 한다. 이미 커밋한 뒤의 실패는 되돌리지 않는다.
- 여러 Service 를 한 원자 단위로 묶으려면 같은 writer 세션을 주입하고 마지막에 한 번 커밋한다.
- `BaseService.commit()` 은 커밋 시점의 `SQLAlchemyError`(지연 제약, 연결 유실 등)도 `convert_db_error()` 로 바꾼다.
- 요청 밖에서는 `background_session()` 을 열고 직접 커밋한다 — 성공 시 자동 커밋하지 않는다.

> **왜 Dependency 가 아니라 핸들러인가.** 예전에는 Dependency 가 `yield` 뒤에서 커밋했다. 기본 request scope 의
> yield dependency 종료 코드는 **응답 전송 후** 실행되므로(FastAPI 0.141 에서 실측), 커밋이 실패해도 클라이언트는
> 이미 201 을 받는다. function scope 는 종료 시점이 다르지만
> ([FastAPI 문서](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)),
> 이 프로젝트는 커밋을 teardown 에 맡기지 않는다. 회귀 가드: `tests/test_read_path_no_commit.py`,
> 기능별 `test_transaction_boundary.py`.

DB 커밋과 HTTP 전송은 하나의 원자적 트랜잭션이 아니다. 커밋 후 연결이 끊길 수 있으므로 중요한 생성 업무는 멱등 키 정책을 요구사항으로 정한다.

### 4.6 Repository 두 계열

데이터 접근은 **ORM 과 Raw SQL 두 계열**이고 갈라지는 곳은 Repository 하나뿐이다. 두 Base 는 **상속 관계가 없다**
(하나의 Base 가 모델과 row 를 함께 돌려주면 호출부가 받은 것을 타입으로 알 수 없다). 어느 쪽을 고를지와 Raw 작성
규칙은 [개발 가이드 — ORM 과 Raw 선택](./DEVELOPMENT.md#orm-raw)에 있다.

| | ORM | Raw SQL |
|---|---|---|
| 기능 Repository 가 상속 | `BaseRepository` (`app/core/repositories/repository_base.py`) | `RawRepositoryBase` (`app/core/repositories/raw_repository_base.py`) |
| 하위 primitive (직접 상속하지 않음) | `CRUDBase` (`app/core/repositories/crud_base.py`) | `RawCRUDBase` (`app/core/repositories/raw_crud_base.py`) |
| 돌려주는 것 | 모델 인스턴스 | `RowMapping` / scalar / rowcount |
| 참조 예제 | `app/features/catalog/repositories/product_repository.py` | `app/features/reports/repositories/sales_report_repository.py` |

**`BaseRepository[Model]` 공개 메서드 — 정확히 8개** (ADR-016). 도메인 쿼리(eager loading·집계·정렬 목록 등)는 기능 Repository 에 둔다.

| 메서드 | 동작 |
|---|---|
| `create(data: dict)` | `id` 가 없으면 UUID 를 채우고 add → flush → refresh. DB 오류는 `convert_db_error` |
| `get_by_id(id)` | 없으면 `None` |
| `get_one(**filters)` | `filter_by` 단건, 없으면 `None` |
| `get_all(skip=0, limit=100)` | offset/limit 조회 — 기본 정렬 `created_at DESC, PK DESC`(`created_at` 이 없으면 PK 역순). 동률에도 페이지가 겹치지 않는다 |
| `count(**filters)` | 개수 |
| `exists(id)` | PK 존재 여부 |
| `update(id, data: dict)` | UPDATE → flush 후 **다시 조회**해 반환(없으면 `None`). MySQL 의 no-op UPDATE rowcount 0 을 부재로 읽지 않기 위해서다 |
| `delete(id)` | 삭제 여부 `bool` |

**`RawRepositoryBase` 공개 메서드 — 4개**. 모든 호출에 `query_name`(코드 상수)이 필요하고, 로그에는 `query_name`·소요 시간·성공 여부만 남는다(SQL·파라미터 제외).

| 메서드 | 결과 없음 | 반환 | 라우팅 의도 |
|---|---|---|---|
| `fetch_one(stmt, params, *, query_name, for_update=False)` | `None` | 첫 행 `RowMapping` | 읽기 (`for_update=True` 면 쓰기) |
| `fetch_all(...)` | 빈 목록 | `RowMapping` 목록 | 읽기 (`for_update=True` 면 쓰기) |
| `fetch_scalar(...)` | `None` | 첫 행 첫 컬럼 | 읽기 (`for_update=True` 면 쓰기) |
| `execute(stmt, params, *, query_name)` | — | 영향 행 수 `int`(존재 판단에 쓰지 않는다), 커밋하지 않음 | 항상 쓰기 |

### 4.7 DB 오류 변환

SQLAlchemy 예외의 문자열에는 실행 SQL·바인딩 값·때로 DSN 이 들어 있다. `convert_db_error()` 는 경계에서 한 번 변환하며
예외 클래스명·드라이버 코드·모델·연산만 로그에 남기고, 호출부는 `raise ... from None` 으로 원본을 끊는다.

| 원본 | 결과 |
|---|---|
| `IntegrityError` + MySQL 1062 / SQLite UNIQUE·PRIMARY KEY 위반 | `DuplicateException` (409) |
| `IntegrityError` + MySQL 1048·1364 / SQLite NOT NULL 위반 | `ValidationException` "필수 값이 비어 있습니다" (422) |
| `IntegrityError` + MySQL 1452 / SQLite FOREIGN KEY 위반 | `ValidationException` "참조하는 데이터가 존재하지 않습니다" (422) |
| `IntegrityError` + MySQL 1451 | `ConflictException` "다른 데이터가 참조하고 있어…" (409) |
| 그 밖의 `IntegrityError`(코드를 알 수 없는 경우 포함) | `DatabaseException` "제약 조건 불만족" (500) |
| 그 밖의 `SQLAlchemyError` | `DatabaseException` (500) |

SQLite 는 숫자 코드를 주지 않으므로 파이썬 `sqlite3` 예외의 `sqlite_errorname` 으로 가른다 — 메시지는 파싱하지 않는다.
변환을 거치지 않는 경로(잡히지 않은 예외의 traceback, 직접 `logger.exception`)도 엔진의 `hide_parameters=True`(§4.3) 덕분에 예외 문자열에 바인드 값이 없다.
4xx 로 바뀌는 위반은 WARNING, 나머지는 ERROR 로 남는다(service-hardening ADR-007).

### 4.8 모델과 기능 카탈로그

모델은 `Base` 에 필요한 Mixin 을 조합한다. `sort_order` 로 컬럼 순서(id → 도메인 → created_at → updated_at)를 고정해
`create_all` 과 migration 의 결과가 갈리지 않게 한다. 시각은 DB 가 아니라 앱이 `timezone_settings.utc_now()`(aware UTC)로 채운다.
`Mapped[datetime]` 은 `app/core/models/types.py` 의 `UTCDateTime` 이다 — MySQL `DATETIME(6)`·UTC 로 저장하고, naive datetime 은 저장 경계에서
`ValueError` 로 거부하며, 읽을 때 `tzinfo=UTC` 를 붙여 응답이 `Z` 오프셋을 갖는다. Raw SQL 은 `bindparam(..., type_=UTCDateTime())` 로 같은 변환을 태운다.
지역 시각(`TIME_ZONE`)은 표시·집계 경계에서만 쓴다 — 리포트·접속 로그의 날짜 범위는 지역 일자를 UTC 순간으로 바꿔 조회한다(service-hardening ADR-010).
`UpdatedAtMixin.onupdate` 는 ORM UPDATE 에만 적용된다.

| 앱 | 모델 → 테이블 | 기능 | Admin |
|---|---|---|---|
| home | `UserAccessLog` → `user_access_logs` | 접속 로그 조회·통계(읽기 전용), `ready()` 에서 sink 결선 | 조회·삭제·내보내기 |
| blog | `Post` → `blog_posts` | 게시글 CRUD | CRUD·내보내기 |
| reply | `Reply` → `replies` | 댓글 CRUD (게시글과의 FK·중첩 route 없음) | CRUD·내보내기 |
| sns | `SnsPost` → `sns_posts` | 피드 게시물 CRUD | CRUD·내보내기 |
| user | `User` → `users` | 사용자 CRUD, username 중복 검사 | 생성 불가, 해시 비노출 |
| auth | (없음 — `User` 사용) | 가입·로그인·재발급·현재 사용자 | 없음 |
| catalog | `Product` → `catalog_products` | **ORM 예제** — 상품 CRUD | CRUD·내보내기 |
| reports | `SalesOrder` → `sales_orders` | **Raw SQL 예제** — 일별 매출 집계(조회 전용) | 읽기 전용·내보내기 |

CRUD 앱의 공통 흐름: Create(스키마 검증 → create/flush → 응답 DTO 검증 → 핸들러 commit → 201), List(pagination → count + 목록, commit 없음),
Retrieve(없으면 기능별 Not Found), Update(변경 필드만 → flush → 응답 DTO 검증 → commit), Delete(삭제 → commit → 204).
조회는 `_readonly` Dependency, 쓰기는 writer Dependency 를 쓴다.

---

## 5. 로깅

설정 단일 지점은 `app/utils/logs/config.py` 의 `build_dictconfig()` 이고, 첫 `get_logger()` 호출이 `configure_logging()` 으로 한 번 적용한다(ADR-019).

| `ENV` | 핸들러 | 시각 |
|---|---|---|
| development | console (밀리초) | 로컬 타임존 |
| test | console | 로컬 타임존 |
| staging / production | console + 날짜·크기 회전 파일 2개(`LOG_FILE_ENABLED=true` 일 때) | UTC |

**모든 실행 경로가 이 구성 하나를 쓴다**(logging-overhaul ADR-001) — 앱 로거, `python main.py`(`setup_uvicorn_logging()` 은
`build_dictconfig()` 를 그대로 돌려준다), `uvicorn main:app`·`fastapi dev` CLI(uvicorn 이 자기 구성을 건 뒤 앱 import 의
`configure_logging()` 이 다시 건다), Celery 워커·beat(`setup_logging` 시그널 수신자 `app/celery/app.py` 의 `use_app_logging`).
`uvicorn`·`uvicorn.error`·`uvicorn.access` 로거는 자기 핸들러 없이 root 로 전파되므로 서버 줄·접속 줄이 앱 콘솔·파일에 같은 형식으로
나온다. 접속 줄의 요청 라인(`client - "GET /p HTTP/1.1" 200`)은 uvicorn 이 넘기는 메시지 그대로다. `--no-access-log` 은 유지된다.
예외: `--reload`(`fastapi dev`) 의 **감시 프로세스**는 앱을 import 하지 않아 `Will watch for changes`·`Started reloader process` 같은
몇 줄이 uvicorn 기본 형식으로 남는다(요청을 받는 자식 프로세스는 프로젝트 형식).

console 은 `LOG_CONSOLE_ENABLED=true`(기본)일 때만 붙는다(`app/utils/logs/config.py` 의 `console_enabled()`).
콘솔도 파일도 없으면 root 에 `NullHandler` 를 달아 `logging.lastResort` 가 stderr 로 새지 않게 하고, `configure_logging()` 이 stderr 에 경고 한 줄을 남긴다.
Celery `--loglevel` 은 워커 root 레벨로 따르고, `--logfile` 을 주면 그 파일에도 같은 형식(`LOG_FILE_FORMAT`)으로 쓴다.

- **파일**(staging/production 에서만, `LOG_DIR` 아래 고정 이름) — 프로세스 종류는 `app/utils/logs/setup.py` 의 `entry_process()` 한 곳이 정한다
  (진입 명령이 `celery` 면 워커 또는 beat, 아니면 웹. Celery 수신자는 `entry_process(default="celery")`).

  | 프로세스 | 일반(`LOG_FILE_LEVEL` 이상) | 에러(ERROR 이상) |
  |---|---|---|
  | 웹(앱·uvicorn) | `app.log` | `error.log` |
  | Celery 워커 | `celery.log` | `celery-error.log` |
  | Celery beat | `celery-beat.log` | `celery-beat-error.log` |

  웹과 워커가 한 `error.log` 를 함께 쓰면 두 프로세스가 같은 파일을 회전시켜 깨진다 — 그래서 에러 파일도 프로세스별이다(ADR-003).
  **기동 초기 줄도 파일에 남는다**: 설정 로드 직후 첫 `get_logger()` 가 진입 명령으로 프로세스 종류를 정하고 파일 핸들러까지 붙인다 —
  import 중에 나는 줄(예: `[database] 라우팅 구성`)이 콘솔에만 있고 파일에서 빠지지 않는다. 웹·`python main.py`·`uvicorn main:app`·
  워커·beat 모두 같고, 핸들러는 한 번만 붙는다(`tests/utils/test_log_early_lines.py`, e2e L6 이 실제 프로세스로 대조한다 —
  integration-e2e ADR-011).
- **회전·보관** — `app/utils/logs/handlers.py` 의 `DailySizeRotatingFileHandler`(표준 `TimedRotatingFileHandler` 상속). 매일 자정(UTC —
  파일은 UTC 를 쓰는 staging/production 에만 있다)에 `app.log` → `app.log.2026-10-19`, 하루 안에서 `LOG_MAX_SIZE_MB` 를 넘으면
  `app.log.2026-10-19.1`·`.2`…. 회전할 때마다 `LOG_RETENTION_DAYS`(기본 30, `0` = 지우지 않음)보다 오래된 날짜·분할 파일을 지운다
  (정확히 N일 전 파일은 남는다). 파일 I/O 는 호출 흐름에서 동기 수행된다.
- **여러 프로세스 주의** — 한 파일은 한 프로세스만 회전시킬 수 있다. `uvicorn --workers 2` 이상·Celery prefork(`--concurrency` > 1 의
  자식 프로세스)는 같은 파일을 여러 프로세스가 회전시켜 안전하지 않다. 그 배포는 **콘솔(stdout) + 수집기/`logrotate`, 파일 로그 끔**
  (`LOG_FILE_ENABLED=false`)으로 운영한다. 기동 시 감지하지는 않는다(워커 수를 앱이 믿을 만하게 알 방법이 없다 — 문서로만 안내).
- **헤더(`app=`)** — `filters._app_from_path()` 한 함수가 정한다. 우리 코드는 소스 경로(`<기능명>`·`core`·`celery`·`utils`·`migrations`·`app`),
  저장소 밖 코드는 로거 이름 표(`celery.*`·`kombu.*` → `celery`, `uvicorn.*` → `uvicorn`, `sqlalchemy.*` → `sqlalchemy`, `alembic.*` → `alembic`,
  그 밖 → `ext`). 새 기능은 아무것도 하지 않아도 자기 이름의 헤더가 붙는다.
- **앱별 레벨** — `LOG_APP_LEVELS="blog=DEBUG,sqlalchemy=WARNING"`. 키는 헤더 이름, 지정 없는 헤더는 `LOG_LEVEL`. 구현은 필터 하나
  (`AppLevelFilter`, 모든 핸들러에서 `ContextFilter` 바로 뒤)이고 root 레벨은 전체 최솟값으로 내려 레코드가 필터까지 오게 한다.
  형식·레벨이 틀리면 설정 로드가 실패하고, 모르는 헤더는 WARNING 한 줄만 남긴다. 핸들러는 여전히 root 에만 붙는다(앱별 로거 등록 없음, ADR-019).
- 포맷: console 은 `LOG_CONSOLE_FORMAT`, 파일은 `LOG_FILE_FORMAT`, 시각은 `LOG_DATE_FORMAT`(development 는 뒤에 `.밀리초`). 기본값은
  `[{asctime} {tzname}] {levelname:5} [app={appname}] [{module}:{classname}:{funcName}:{lineno}] {message}` / `%Y-%m-%d %H:%M:%S`
  (`config.DEFAULT_LOG_FORMAT` = `app.utils.logs.LOG_FORMAT`). 설정 로드 때 샘플 레코드로 한 번 렌더해 모르는 필드·괄호 불일치면 기동을 멈추고,
  필수 필드 `{asctime}`·`{levelname}`·`{appname}`·`{module}`·`{classname}`·`{funcName}`·`{message}` 가 하나라도 없어도 멈춘다(`config.REQUIRED_LOG_FIELDS`).
- `SqlNoiseFilter` 가 모든 핸들러에서 SQLAlchemy·드라이버 로거의 SQL 본문·바인딩 값을 막는다. `LOG_SQL_ECHO_ENABLED=true` 로만 열 수 있고, production/staging 에서는 설정 로드가 거부한다.
- **비밀값 가리기** — `app/utils/logs/redaction.py` 의 `SecretRedactor` 가 규칙의 정본이다(DSN·URL 의 **계정명과 비밀번호**
  `scheme://***:***@host` — 계정명 없는 `scheme://:***@host`·계정명만 있는 `scheme://***@host`, 비밀번호는 마지막 `@` 까지, `password`·`secret`·`token`·`api_key`·`authorization` 으로 끝나는 키의 값, Bearer 토큰, JWT → `***`).
  여기에 `config.LOG_REDACTED_SETTINGS`(DB writer·replica 계정명·비밀번호, Redis 비밀번호, JWT access/refresh 키, `SESSION_SECRET_KEY`)의
  **현재 값 원문**을 `configure_logging()` 이 넘겨, 로그 어디에 나와도 `***` 로 바꾼다. 4글자 미만 값(주로 짧은 계정명)은 일반 단어와 겹치므로
  `user=`·`username=` 뒤와 DSN 에서만 가린다. 새 비밀 설정은 이 목록에 넣어야 한다(`test_every_secret_setting_is_redacted_from_logs` 가 이름 규칙으로 강제).
  가리기는 **LogRecord factory** 에 걸려 렌더된 메시지·traceback 본문(`exc_text` 로 미리 포맷해 고정)·`stack_info` 를 레코드가 만들어질 때 가린다 —
  우리가 포매터를 소유하지 않는 경로도 같은 규칙을 탄다. 예외 타입·체인·파일·줄은 남는다. 접속 로그(DB 저장)는 대상이 아니다(§6).
- 세션 롤백 로그(`app/core/db/session.py`)는 ERROR 에 예외 **타입과 소요시간만** 남긴다 — DB 예외의 `str()` 에 실행된 SQL 과 바인딩 값이 들어 있고, 앱 로거 이름은 `SqlNoiseFilter` 를 통과하기 때문이다.
  추적이 필요하면 DEBUG 레벨에서 같은 지점의 `exc_info=True` 상세 레코드가 트레이스백 전문을 남긴다. 그래서 production/staging 은 debug 모드 자체를 거부한다(§3.2).
- Service 는 `LoggerMixin` 을 상속해 `self.log` 를 쓴다. 키 표·Django LOGGING 설정 대응표는 README "로깅" 절이 정본이다.

**레벨 결정** — root 레벨은 `LOG_LEVEL`, 없으면 `DEBUG` 에 따라 DEBUG/INFO. console 레벨은 `LOG_CONSOLE_LEVEL`, 없으면 같은 규칙.
`LOG_APP_LEVELS` 가 있으면 root 는 그중 가장 낮은 레벨까지 내려가고, 헤더별 컷은 `AppLevelFilter` 가 한다(지정 없는 헤더 = `LOG_LEVEL`).
명시값이 `DEBUG` 기본 계산보다 우선한다.

| `DEBUG` | `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` | console 에 나오는 것 |
|---|---|---|
| false | 미설정 / 미설정 | INFO 이상 |
| true | 미설정 / 미설정 | DEBUG 이상 |
| false | DEBUG / DEBUG | DEBUG 이상 (앱 DEBUG 모드는 여전히 꺼짐) |
| 무관 | INFO / DEBUG | INFO 이상 — root 가 먼저 거른다 |
| 무관 | DEBUG / INFO | INFO 이상 |

startup 로그의 `(DEBUG=%s)` 는 표시 값일 뿐 출력 조건이 아니다. INFO 가 안 보이면 위 두 설정과 핸들러부터 본다.

---

## 6. 접속 로그

`UserInfoMiddleware` 가 요청마다 정보를 모으고, 응답 후 저장을 백그라운드 태스크로 넘긴다. core 는 저장 구현을 모른다.

```text
UserInfoMiddleware (app/core/middlewares/user_info_middleware.py)
  └ access_log_tasks.spawn(...)          BackgroundTaskRunner — 동시 256개 상한, 초과분 drop·집계
      └ get_access_log_sink().save(data) AccessLogSink Protocol (core)
          └ HomeAccessLogSink            home 이 ready() 에서 set_access_log_sink() 로 등록
              └ background_session() → UserAccessLogService.create_access_log → commit
```

- sink 가 등록되지 않았으면(home 미설치) 저장을 건너뛴다. home 을 목록에서 빼면 Router·Model 과 함께 접속 로그 영속화 결선도 빠진다.
- 저장 실패는 로그만 남기고 응답에 영향을 주지 않는다. 태스크 제출은 `call_next` 가 응답을 돌려준 뒤이며, 클라이언트가 모든 바이트를 받았다는 보증은 아니다. `call_next` 가 처리되지 않은 예외로 끝나면 `response_status=500` 으로 기록한 뒤 예외를 그대로 다시 던진다.
- best-effort 다. 감사 목적의 필수 데이터라면 durable queue 로 바꿔야 한다. 중요한 업무 저장을 이 runner 에 넣지 않는다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_LOG_ENABLED` | `true` |
| `ACCESS_LOG_EXCLUDE_PATHS` | `["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]` (정확 일치) |
| `ACCESS_LOG_EXCLUDE_EXTENSIONS` | `[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"]` (접미사 일치) |
| `TRUSTED_PROXY_HOPS` | `0` — 앞단 신뢰 프록시 수. 0 이면 프록시 헤더를 보지 않는다 |
| `ACCESS_LOG_SENSITIVE_QUERY_KEYS` | `["password", "token", "access_token", "refresh_token", "secret", "api_key", "code"]` (대소문자 무시) |
| `SESSION_COOKIE_NAME` | `session` — 이 이름의 쿠키 값을 `session_id` 로 기록 |
| `ACCESS_LOG_RETENTION_DAYS` | `365` — 보존 일수. `0` = 지우지 않음, 음수는 설정 검증 오류 |

**보존 기간 삭제** (security-ops-hardening ADR-002·ADR-003): home 의 Celery 태스크 `home.purge_expired_access_logs` 가
`UserAccessLogService.purge_expired()` 를 부른다. 기준은 `now(UTC) - ACCESS_LOG_RETENTION_DAYS 일` 이고 그보다 **오래된** 행만 지운다
(정확히 그 순간의 행은 남는다). `UserAccessLogRepository.delete_created_before()` 가 오래된 순으로 id 를 최대 5,000개(`user_access_log_service.PURGE_BATCH_SIZE`) 고른 뒤
그 id 로 지우고, 서비스가 배치마다 커밋한다 — 긴 잠금·거대 트랜잭션을 피한다. 두 구문으로 나눈 이유는 MySQL 이 같은 테이블의
`IN (SELECT … LIMIT)` 을 거부하고 SQLite 는 `DELETE … LIMIT` 을 받지 않기 때문이다(두 DB 에서 같은 쿼리). 보존 0 이면 DB 에 가지 않는다.
일정은 매일 03:30(`TIME_ZONE`)이고 home 의 `tasks.py` 가 `celery_app.add_periodic_task` 로 등록한다(§9).

**클라이언트 IP** (`app/core/middlewares/client_ip.py` 의 `ClientIPResolver`, `setup_user_info_middleware()` 가
설정으로 한 번 만들어 미들웨어에 주입): `TRUSTED_PROXY_HOPS=0` 이면 소켓 주소(`request.client.host`)만 쓴다.
N 이면 `X-Forwarded-For` 목록 끝에 소켓 주소를 붙이고, 소켓 주소를 0번째로 센 **오른쪽 N번째**(= XFF 의 오른쪽
N번째, 가장 바깥 신뢰 프록시가 본 주소)를 쓴다. 그보다 왼쪽은 클라이언트가 쓴 값이라 믿지 않는다. 체인이 N보다
짧거나 값이 IP 가 아니면(`ipaddress.ip_address` 실패) 소켓 주소로 돌아간다. `X-Real-IP` 는 N>0 이고 XFF 가
없을 때만 본다. **기본값 0 은 이전 동작(XFF 첫 값을 무조건 신뢰)을 바꾼 것이다** — 프록시 뒤에 배포하면 홉 수를
설정해야 실제 클라이언트 IP 가 기록된다(service-hardening ADR-005).

**저장 전 정리**: query string 의 민감 키 값은 `***` 로 바뀐다. 문자열은 home 기능의
`UserAccessLogService.create_access_log` 가 모델 컬럼 길이(`UserAccessLog.__table__` 의 `String(n)`)로 자른다 —
긴 헤더·쿠키 하나로 MySQL strict 모드의 1406 이 나서 기록이 빠지던 경로를 막는다(service-hardening ADR-006).

**수집 필드** (`user_access_logs`): `ip_address`(위 `ClientIPResolver`), `forwarded_for`, `real_ip`(헤더 원문 — 위조 가능),
`user_agent` 와 파싱 결과(`os_name`·`os_version`·`browser_name`·`browser_version`·`device_type`·`device_brand`·`device_model`·`is_bot`),
`request_path`, `request_method`, `query_string`(민감 키 값 `***`), `referer`, `accept_language`, `session_id`(`SESSION_COOKIE_NAME` 쿠키 원문), `user_id`(`request.state`),
`response_status`, `response_time_ms`. 인덱스: created_at·ip_address·os_name·browser_name·device_type·country·session_id·user_id.

조회 API(`/api/v1/home/access-logs` 외 4개)는 모두 read-only 세션을 쓰며 **슈퍼유저 전용**이다(라우터 의존성 `require_superuser`, §7.1).
인증된 요청의 `user_id` 는 `get_current_principal` 이 핸들러 실행 중에 `request.state.user_id` 로 채우고, 미들웨어가 **응답 뒤에** 읽어 기록한다.

---

## 7. 인증 (JWT)

OAuth2 **password flow** + JWT access/refresh(회전). 자격증명은 `user` 기능의 `User.hashed_password` 에 있고,
`auth` 는 인증 로직만 담당한다(`auth → user` 의존은 의도된 예외). 목적마다 클래스 하나인 보안 부품은
`app/core/security/` 에 있다 — user 기능(해시)과 다른 기능의 인증 의존성(토큰 검증)도 써야 하므로 core 에 둔다.

| 부품 | 위치 | 역할 |
|---|---|---|
| `PasswordHasher` | `app/core/security/passwords.py` | pwdlib Argon2 해시. 기존 bcrypt(`$2…`)는 이전 규칙(72바이트 절단)으로 검증하고 성공하면 Argon2 새 해시를 돌려준다. 타이밍 균등화 더미 해시도 Argon2 |
| `TokenService` | `app/core/security/tokens.py` | PyJWT 발급·검증. claims `sub·type·iat·nbf·exp·jti·iss·aud` + access `username`·`su`(슈퍼유저 여부, bool 필수) / refresh `fam`. 실패는 원인과 무관하게 `InvalidTokenException`(401, 오류 코드 AUTH_INVALID_TOKEN) |
| `RefreshTokenStore` | `app/core/security/refresh_store.py` | Redis 에 미사용 refresh(`auth:rt:{jti}`)·사용자 family 집합·family 폐기 표시를 둔다. 소비는 Redis GETDEL 하나 |
| `RateLimiter` | `app/core/security/rate_limit.py` | Redis 고정 창(MULTI 안에서 INCR + EXPIRE NX + TTL). 초과는 `TooManyRequestsException`(429, `Retry-After`) |
| `Principal` · `OwnershipPolicy` | `app/core/security/principal.py` | 요청 주체(id·username·is_superuser, 불변)와 소유권 판정 `ensure_can_modify(owner_id, principal)` — 소유자 또는 슈퍼유저, 아니면 403 |

조립은 provider 함수가 한다(생성자 주입, service-hardening ADR-022). 여러 기능이 함께 쓰는 provider —
`get_password_hasher`·`get_token_service`·`get_ownership_policy`(프로세스당 하나, `lru_cache`)와 `get_refresh_token_store`(`Depends(get_redis)`, §3.4) —
는 `app/core/security/dependencies.py` 에 있고, 인증 기능(`app/features/auth/dependencies/auth_dependencies.py`)은 그것을 그대로 쓰면서
`get_client_ip_resolver`·`get_rate_limiter`·`get_auth_service(session, hasher, tokens, store)` 를 더한다.

| 메서드 | 경로 | 인증 | 요청 | 성공 | 실패 |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/register` | — | JSON (비밀번호 8~128자) | 201 | 409 사용자명 중복 · 422 · 429 |
| POST | `/api/v1/auth/login` | — | **form** (`username`·`password`) | 200 | 401 · 422 · 429 |
| POST | `/api/v1/auth/refresh` | — | JSON `{"refresh_token": ...}` | 200 | 401 무효·만료·재사용·폐기·비활성 · 422 |
| POST | `/api/v1/auth/logout` | — | JSON `{"refresh_token": ...}` | 204 | 401 무효·만료 · 422 |
| GET | `/api/v1/auth/me` | Bearer | — | 200 | 401 |

토큰 응답은 `{"access_token", "refresh_token", "token_type": "bearer", "expires_in": <access 수명 초>}` 다.

**흐름**

1. **login** — `login_rate_limit` 의존성이 ip(`AUTH_LOGIN_IP_MAX_ATTEMPTS`)와 ip+소문자 username(`AUTH_LOGIN_MAX_ATTEMPTS`)을
   `AUTH_LOGIN_WINDOW_SECONDS` 창으로 센다. ip 는 접속 로그와 같은 `ClientIPResolver`(`TRUSTED_PROXY_HOPS`, §6)로 정한다.
   `AuthService.authenticate`(`/admin` 로그인과 같은 `verify_credentials`)가 해시기를 `asyncio.to_thread` 로 부르고, bcrypt → Argon2 재해시가 있으면 `UserRepository.update` 로
   flush 해 둔다. 새 family 로 토큰 쌍을 발급하고 refresh 의 jti 를 기록한 뒤 핸들러가 **커밋**하고 ip+username 카운터를 지운다.
2. **refresh** — refresh 토큰을 검증하고 GETDEL `auth:rt:{jti}` 로 소비한다. 값이 없으면 이미 쓴 토큰의 **재사용**(탈취 신호)이라
   그 family 를 폐기하고 401 — 정상 사용자가 가진 같은 family 의 최신 토큰도 함께 죽는다. family 가 폐기됐거나 사용자가 없거나
   비활성이면 401(비활성·부재는 family 도 폐기). 통과하면 **같은 family** 로 새 쌍을 발급한다.
3. **logout** — refresh 토큰의 family 를 폐기하고 jti 를 소비한다(멱등, 204). access 토큰은 만료(`ACCESS_TOKEN_EXPIRE_MINUTES`)까지
   유효하다 — 즉시 폐기 목록은 두지 않고 짧은 수명으로 대신한다.
4. **/me** — `get_current_principal`(아래 §7.1) → read-only 세션을 **primary 에 고정**(`using_writer`)한 `UserRepository.get_by_id` → 없거나 비활성이면 401. replica 에서 읽으면 복제 지연 중 가입 직후의 유효한 토큰이 401 이 되고 비활성화·삭제가 늦게 반영된다(integration-e2e ADR-012 결정 5, F-008). 다른 읽기 라우팅은 그대로다.
   Redis 도 쓰기 세션도 쓰지 않는다.
5. **register** — `register_rate_limit`(ip, `AUTH_REGISTER_MAX_ATTEMPTS`/`AUTH_REGISTER_WINDOW_SECONDS`) 뒤 Argon2 해시로 저장, 응답 DTO 검증 후 커밋.

access·refresh 수명(`ACCESS_TOKEN_EXPIRE_MINUTES`·`REFRESH_TOKEN_EXPIRE_DAYS`)은 [README 세션·토큰 만료](../../README.md#세션토큰-만료) 표에 있다.

| 설정 | 기본값 | 설명 |
|---|---|---|
| `JWT_ALGORITHM` | `HS256` | HS256·HS384·HS512 만 허용. 검증은 이 값 하나만 받는다 |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `fastapi-project` / `fastapi-project-api` | 검증 시 일치해야 한다 |
| `JWT_LEEWAY_SECONDS` | `5` | exp·nbf·iat 시계 오차 허용 |
| `AUTH_LOGIN_MAX_ATTEMPTS` / `AUTH_LOGIN_IP_MAX_ATTEMPTS` / `AUTH_LOGIN_WINDOW_SECONDS` | `5` / `20` / `60` | 로그인 레이트 리밋 |
| `AUTH_REGISTER_MAX_ATTEMPTS` / `AUTH_REGISTER_WINDOW_SECONDS` | `5` / `3600` | 회원가입 레이트 리밋 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 서로 다른 값으로 **배포 전 반드시 교체** — 기본값이면 누구나 토큰을 위조한다. test 외 모든 ENV 에서 placeholder·32자 미만이거나 두 키가 같으면 기동이 실패한다(`validate_deployment_safety()`, §3.2) |

- access 와 refresh 는 서명 키가 다르고, `type` claim 도 검사한다(키가 같게 설정돼도 종류 혼동을 막는 두 번째 벽).
- **상수 시간 인증**: 사용자가 없거나 비밀번호가 없는 계정도 더미 Argon2 해시로 검증 비용을 치러 응답 시간차로 사용자명 존재를 알 수 없게 한다.
  bcrypt 해시가 남은 사용자는 bcrypt 비용이 드는 동안만 시간이 다르다(로그인하면 Argon2 로 바뀐다).
- **논블로킹 해싱**: Argon2·bcrypt 는 `asyncio.to_thread` 로 이벤트 루프 밖에서 돈다.
- **API 인증은 세션을 쓰지 않는다**: 메인 앱에는 세션 미들웨어가 없고, `admin_session` 쿠키를 보내도 API 는 401 이다. 세션 로그인은 `/admin` 전용이다(§8).

### 7.1 인가 — 주체·소유권·슈퍼유저

권한은 **슈퍼유저/일반 2단계**다(`users.is_superuser`). 인가는 core 의 주입 경로 하나(`app/core/security/dependencies.py`)로 한다 —
기능이 인가를 위해 user 기능을 import 하지 않는다(service-hardening C-11).

| 주입 | 하는 일 | 실패 |
|---|---|---|
| `oauth2_scheme` | `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)` — OpenAPI 에 Bearer 스킴을 싣는다 | 헤더가 없으면 아래가 401 |
| `get_current_principal` | access 토큰 검증 → `Principal(id, username, is_superuser)`. **DB 조회 없음**. `request.state.user_id` 를 채운다 | 401 UNAUTHORIZED(토큰 없음) · 401 AUTH_INVALID_TOKEN(만료·위조·`su` 누락·refresh 토큰). 401 의 `WWW-Authenticate: Bearer` 는 전역 핸들러가 붙인다 |
| `require_superuser` | 주체가 슈퍼유저인지 본다 | 403 FORBIDDEN |
| `CurrentPrincipal` / `SuperuserPrincipal` | 위 두 의존성의 `Annotated` 별칭 — 핸들러 인자 타입으로 쓴다 | — |
| `OwnershipPolicy` | 서비스가 생성자로 받아 수정·삭제 전에 `ensure_can_modify(owner_id, principal)` 를 부른다. `owner_id` 가 `None` 이면 슈퍼유저만 | 403 FORBIDDEN |

**접근 수준 선언과 기본 거부**(`app/core/security/access.py`, access-policy). 뷰는 경로 데코레이터의 `dependencies=[...]` 에 수준을 하나 적는다.

| 선언 | 실체 | 쓰는 곳 |
|---|---|---|
| `Public` | 아무것도 하지 않는 표식 의존성 | 안전한 메서드(GET·HEAD·OPTIONS) 공개 |
| `PublicWrite` | 아무것도 하지 않는 표식 의존성(다른 함수) | 인증 없는 쓰기를 명시적으로 연다 — auth register·login·refresh·logout |
| `LoginRequired` | `Depends(get_current_principal)` — 인자 `CurrentPrincipal` 도 같은 선언으로 본다 | 401 |
| `SuperuserRequired` | `Depends(require_superuser)` — 인자 `SuperuserPrincipal` 도 같은 선언으로 본다 | 401 · 403 |

`create_app()` 의 마지막 단계(라우터·health·docs·admin 설치 뒤)에서 `AccessPolicyGuard().verify(app)` 가 서빙되는 모든 `APIRoute`
(FastAPI 0.141 의 `_IncludedRouter` 중첩을 `effective_route_contexts()` 로 펼친 것, `include_in_schema=False` 포함)의 의존성 트리를
재귀로 훑는다. 선언 없음 · 서로 다른 수준 동시 선언 · 쓰기 메서드에 `Public` · 안전한 메서드에 `PublicWrite` 가 하나라도 있으면
위반 목록 전체를 담은 `ImproperlyConfigured` 로 기동을 멈춘다. `require_superuser` 는 안에서 `get_current_principal` 을 쓰므로
슈퍼유저가 있으면 슈퍼유저 하나로 본다. 라우터 단위 `dependencies` 도 트리에 들어가므로 인정되지만 예시는 뷰 단위로 통일했다.
FastAPI 가 붙이는 문서 경로(Starlette `Route`)와 `Mount`(`/admin` — 자체 세션 인증)는 대상이 아니다. 앱이 직접 등록한
Scalar `/docs` 는 `APIRoute` 라 `Public` 을 선언한다.

| 기능 | 공개 | 인증 | 소유자 또는 슈퍼유저 | 슈퍼유저 |
|---|---|---|---|---|
| blog · sns · reply | 목록·단건 조회 | 생성(작성자 `author_id`·`author` 는 서버가 주체로 채운다 — 본문 값은 무시) | 수정·삭제(존재 확인 404 가 먼저) | — |
| catalog | 목록·단건 조회 | — | — | 생성·수정·삭제 |
| reports | — | — | — | 일별 매출 |
| home | — | — | — | 접속 로그 조회 5종(뷰마다 `SuperuserRequired`) |
| user | — | — | 단건 조회·수정(본인 — **권한 판정이 존재 확인보다 먼저**라 남의 ID 는 있든 없든 403) | 목록·생성(비밀번호 필수, `is_superuser` 지정 가능)·삭제, `is_active`·`is_superuser` 변경 |
| auth | register·login·refresh·logout | `/me` | — | — |

- 비활성화(`is_active` True→False)·강등(`is_superuser` True→False)·비밀번호 변경·삭제는 그 사용자의 refresh family 와 `/admin` 관리 세션을 모두 폐기한다(커밋 전).
  무엇을 지울지는 `revocation_for_change`(`app/core/security/revocation.py`, §8)가 변경 전 값과 비교해 정한다. 강등 시 refresh 폐기는 service-hardening 부터의
  동작(`test_demotion_revokes_refresh_families`)이고, 관리 화면도 같은 규칙을 쓴다(admin-session-hardening ADR-010 — 관리 화면 경로 = API 경로). refresh 회전은
  DB 를 다시 읽지만(비활성 거부·새 권한으로 발급) 기존 동작을 유지한다.
  이미 발급된 access 는 만료(기본 15분)까지 유효하다 — 즉시 폐기 목록은 두지 않는다(§11.3).
- `author_id` 가 없는 행(인가 리비전 `a3c9e8f1b274` 이전 데이터)은 슈퍼유저만 수정·삭제한다.
- 정본은 뷰 선언이다. "모든 오퍼레이션이 분류됐는가" 는 기동 검사가 막고, `tests/test_authorization_policy.py` 의 표는 예시 정책이
  의도한 수준인지 가드의 판정과 대조하는 회귀용이다(OpenAPI `security` 와도 교차 확인한다).
- 첫 관리자는 `uv run python -m scripts.create_superuser --username <이름> --email <메일>` 로 만든다(이미 있으면 승격, 비밀번호는 `--set-password` 일 때만 바꾼다).
  사용법은 README 「첫 관리자 만들기」.

---

## 8. 관리 화면 (SQLAdmin)

설계·흐름도·쿠키 구조·위협 모델·문제 해결은 [관리 화면 인증 가이드](workflows/admin-authentication.html)에 있다. 여기는 요약이다.

- `ADMIN_DISABLED=false`(기본)일 때만 `create_admin()` 이 `/admin` 을 마운트하고 설치 앱의 `admin_views` 를 등록한다. `DEBUG` 와 독립이다.
  `ADMIN_DISABLED=true` 면 마운트·sqladmin import·세션 미들웨어·인증 백엔드가 모두 없고, 앱의 어떤 응답에도 `/admin` 이 나오지 않는다
  (`tests/core/test_admin_disabled.py`). 예전 `ADMIN` 설정이 남아 있으면 기동이 멈춘다(§3.2).
- ModelView 는 모델과 같은 기능 폴더의 `admin.py` 가 소유한다(중앙 취합 파일 없음). 모델이 있는 앱은 `admin.py` 를 가져야 한다(`tests/core/test_admin_wiring.py`).
  `User` 의 `hashed_password` 는 목록·상세·폼·내보내기 어디에도 나오지 않고 `User` 생성은 막혀 있다(`tests/core/test_admin_views.py`).
- **활성 슈퍼유저 로그인이 필요하다.** `AdminAuthBackend`(`app/core/security/admin_auth.py`)가 SQLAdmin `AuthenticationBackend` 를 구현한다.
  - 로그인: 폼 username/password/csrf_token → **CSRF 토큰 확인**(`AdminCsrfMiddleware` — 아래, 없거나 다르면 403 으로 로그인 화면을 다시 그리고
    레이트 리밋·자격 확인을 하지 않는다) → 레이트 리밋(`AUTH_LOGIN_*` 한도 재사용, 키 접두사 `admin-login:` 으로 API 와 분리, ip·ip+username) →
    자격 확인 → 활성·슈퍼유저면 `request.session.clear()` 후 사용자 id 저장 + 새 CSRF 토큰 + `RedisSessionMiddleware.rotate()`(응답 직전 새 세션 ID 발급,
    이전 Redis 키 삭제 — 세션 고정 방지). 실패는 사유 없이 400, 한도 초과는 로그인 화면을 429 + `Retry-After` 로 다시 그린다.
  - 매 요청: 세션의 id 로 **DB 를 다시 확인**해 활성·슈퍼유저가 아니면 세션을 비우고 로그인 화면으로 보낸다(아래 즉시 폐기와 이중 방어).
  - 로그아웃: **POST 전용**(`require_post_logout` 이 sqladmin 의 GET `/admin/logout` 라우트를 POST 라우트로 바꾼다 — GET 은 405) + CSRF 토큰.
    세션을 비우면 미들웨어가 Redis 키를 지우고 쿠키를 지운다 — 복사해 둔 쿠키도 그 순간 무효다.
  - 자격 확인은 core 가 사용자 모델을 모르므로 `AuthConfig.ready()` 가 `app/core/security/admin_credentials.py` 의 훅에 등록한
    `UserAdminCredentials`(`app/features/auth/admin_credentials.py`, `background_session` + `PasswordHasher`, API 로그인과 같은 `verify_credentials`)가 한다.
    등록한 앱이 없으면 관리 화면을 열지 않고 기동을 멈춘다.
- **세션은 Redis 서버 세션이다**(`app/core/security/admin_session.py`, admin-session-hardening ADR-001). 쿠키 `admin_session` 에는 `secrets.token_urlsafe(32)`
  세션 ID 만 있고(path `/admin`, SameSite=Strict, HttpOnly, staging/production 에서 Secure, Max-Age = 절대 만료), 내용은 Redis 에 있다.
  - `AdminSessionStore` 가 저장·조회·삭제·사용자별 폐기를, ASGI `RedisSessionMiddleware` 가 `scope["session"]` 에 dict 를 채우고 응답 직전에 저장·회전·삭제한다
    (`request.session` 인터페이스 그대로).
  - Redis 키 `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, 세션 ID)}` → JSON `{"data", "user_id", "created_at"}`. TTL = min(미사용 만료, 절대 만료까지 남은 초),
    요청마다 다시 건다(내용이 바뀌면 SET, 아니면 EXPIRE). 사용자별 인덱스 `admin:user_sessions:{user_id}`(SET, TTL = 절대 만료).
  - 만료: 절대 `ADMIN_SESSION_MAX_AGE_SECONDS`(기본 8시간, 연장 불가 — 읽을 때 `created_at` 으로도 검사), 미사용 `ADMIN_SESSION_IDLE_SECONDS`(기본 30분).
    쿠키의 ID 가 Redis 에 없으면(만료·폐기·위조) 빈 세션이고 쿠키를 지운다(`Max-Age=0`).
  - `SESSION_SECRET_KEY` 는 세션 ID → Redis 키 HMAC 키다 — Redis 키가 새도 쿠키를 만들 수 없고, 키를 바꾸면 모든 관리 세션이 무효다.
  - **Redis 장애는 fail-closed**: 세션을 읽지 못하면(lifespan 밖이라 클라이언트가 없는 경우 포함) 관리 화면은 503 이고 앱에 닿지 않는다. 응답 직전 저장 실패(쿠키 없는 첫 요청의 세션 생성 등)도 앱이 만든 응답 대신 같은 503 이다 — 응답 시작 전이라 바꿀 수 있다(integration-e2e ADR-012 결정 6).
  - 미들웨어 순서는 `RedisSessionMiddleware`(바깥) → `AdminCsrfMiddleware`(안쪽)이고 **SQLAdmin 하위 앱에만** 있다 — 메인 앱에는 세션 미들웨어가 없고
    API 인증(JWT Bearer)은 세션을 보지 않는다(`tests/core/test_admin_login_flow.py`).
- **즉시 폐기**(ADR-005·ADR-008·ADR-010): 판정 한 곳 — `revocation_for_change(before, changes)`(`app/core/security/revocation.py`)가 변경 **전** 값과 비교해
  `Revocation(admin_sessions, refresh)` 를 돌려주고, 삭제는 `revocation.REVOKE_ON_DELETE`, 비밀번호 변경 스크립트는 `revocation.REVOKE_ON_PASSWORD_CHANGE`(둘 다 두 집합 모두)다.
  `UserSessionRevoker.revoke(user_id, revocation)` 는 판정대로 refresh family(`RefreshTokenStore.revoke_user`)·관리 세션(`AdminSessionStore.revoke_user`)을 지운다.

  | 변경(변경 전 값과 비교) | 관리 세션 | refresh family |
  |---|---|---|
  | 비활성화(`is_active` True→False) | 지운다 | 지운다 |
  | 슈퍼유저 해제(`is_superuser` True→False) | 지운다 | 지운다 |
  | 비밀번호 해시 변경 | 지운다 | 지운다 |
  | 삭제 | 지운다 | 지운다 |
  | 그 밖(이름·이메일 등), 이미 꺼진 값을 다시 끔 | 유지 | 유지 |

  지금은 두 집합이 같지만 판정은 두 집합을 따로 돌려준다 — 한쪽만 바꿀 일이 생겨도 조건은 이 함수 한 곳에만 있다. 원칙은 관리 화면 경로 = API 경로(`UserService`)다.

  - API: `UserService`(`app/features/user/services/user_service.py`)가 수정·삭제 때 판정해 부른다. 생성자는 `revoker` 하나를 받고, provider 는
    `get_user_session_revoker`(`app/core/security/dependencies.py`)다. 관리 화면이 꺼져 있으면 관리 세션 저장소가 `None` 이라 refresh 쪽만 지운다.
  - 관리 화면: `UserAdmin`(`app/features/user/admin.py`)의 커밋 **전** 훅이 같은 판정으로 `revoker_from_scope(request.scope)` 를 부른다 — `on_model_change`
    (생성 제외)·`on_model_delete`(`revocation.REVOKE_ON_DELETE`). 자기 자신을 강등·비활성화하면 현재 세션도 지워져 다음 요청에서 로그인 화면이 나온다(의도).
  - **폐기는 커밋 전이다(fail-closed)**: sqladmin 0.32 의 `_queries._update_async`·`_delete_async` 가 `on_*` 훅을 세션 안에서 커밋 전에 부르고, API 는 핸들러가
    나중에 커밋한다. Redis 폐기가 실패하면 예외가 커밋을 막는다 — 관리 화면 수정은 400 오류 화면 + DB 변경 없음, 삭제는 목록 `error=` + 행 유지.
    반대로 폐기 뒤 커밋이 다른 이유로 실패하면 세션만 지워진다(다시 로그인하면 된다). 폐기와 커밋 사이에 다시 로그인한 세션은 매 요청 DB 확인이 막는다(R-005).
  - 스크립트: `scripts/create_superuser.py --set-password` 는 별도 프로세스라 커밋 뒤 `revoke_sessions_in_redis` 로 관리 세션과 refresh 를 지운다
    (`revocation.REVOKE_ON_PASSWORD_CHANGE`). Redis 실패면 종료 코드 1(`비밀번호는 바뀌었지만 세션을 지우지 못했습니다`)이다.
- **CSRF**(ADR-002): `AdminCsrfMiddleware`(`app/core/security/admin_auth.py`)가 `/admin` 아래 POST·PUT·PATCH·DELETE 전부(로그인 포함 — 검사는 여기 하나)에서
  헤더 `X-CSRF-Token`, 없으면 폼 필드 `csrf_token` 을 세션 토큰(`AdminCsrf`)과 `hmac.compare_digest` 로 비교한다. 폼은 본문을 한 번 버퍼링해 파싱하고
  같은 본문을 다운스트림에 다시 흘려 준다. 버퍼링 상한은 10 MiB(`admin_auth.py` 의 상수 — 설정이 아니다) — `Content-Length` 로 먼저, 없거나 거짓이면 읽는 도중
  누적 크기로 판정해 413, 필드 하나가 1 MiB 를 넘으면 400 이다(500·연결 끊김 없음, integration-e2e ADR-012 결정 7). 실패는 403 이다 — 로그인은 로그인 화면, 로그인한 세션은 관리 화면 `error.html`, 로그인 전 요청은 문구만.
  로그는 WARNING `[AdminCsrf] 토큰 불일치 METHOD PATH`. 레이트 리밋·자격 확인보다 먼저라 위조 요청이 카운터를 올리지 못한다.
- 로그인 화면은 `app/templates/admin/sqladmin/login.html`(Bootstrap 5.3.8 CSS, SRI)이 sqladmin 기본 템플릿을 덮어쓴다 — `templates_dir` 의 로더가 패키지 템플릿보다 먼저다.
  폼은 `csrf_token(request)`(백엔드가 템플릿에 건 전역 함수 — 세션에 토큰이 없으면 `secrets.token_urlsafe(32)` 로 만든다)를 hidden 입력으로 싣는다.
  로그인 이후 화면은 `app/templates/admin/sqladmin/base.html` 이 sqladmin 원본(`sqladmin_original/base.html`)을 **확장**해 `<meta name="csrf-token">` 을 싣고,
  인라인 스크립트가 같은 출처 POST 폼(생성·수정)에 hidden `csrf_token` 을, 같은 출처 XHR·`fetch`(삭제·일괄 삭제·가져오기)에 `X-CSRF-Token` 을 붙이며,
  로그아웃 링크 클릭을 토큰 실은 POST 폼 제출로 바꾼다. JS 가 꺼져 있으면 로그아웃은 405 다. 원본 대조 테스트(`tests/core/test_admin_csrf.py`)가
  sqladmin 업그레이드로 원본 블록·로그아웃 링크·`main.js` 요청 방식·로그아웃 라우트가 바뀌면 실패한다. 사용자 정의 `@action`(GET)은 보호 밖이다(이 저장소는 안 쓴다).
- 목록의 시각 컬럼 필터는 `LocalDateFilter`(`app/core/admin_filters.py`)다. sqladmin 의 연산 필터는 `UTCDateTime` 을 날짜로 알아보지 못해 문자열을
  바인딩하고 목록이 500 이 된다. 이 필터는 `YYYY-MM-DD` 를 `TIME_ZONE` 의 날짜로 읽어 지역 0시를 UTC 순간으로 바꾼 범위로 거른다 —
  같은 날 `[D, D+1)`·이후(포함) `>= D`·이전(미포함) `< D`·**기간** `S~E`(양 끝 포함 `[S, E+1)`, 한쪽만이면 열린 구간), 빠른 선택(오늘·최근 7일·최근 30일 —
  최근 N일은 오늘을 포함한 기간). 화면은 시작일·종료일 날짜 입력 둘을 제출 직전 스크립트가 값 하나로 합친다(`app/templates/admin/sqladmin/filters/local_date_filter.html`).
  형식이 틀리거나 역순이면 필터 없이 목록을 보여 준다(WARNING `[admin] 날짜 필터 기간 무시`). `created_at` 이 있는 모든 ModelView 가 단다(`tests/core/test_admin_pages.py`).
- 기본이 "켜짐" 인 것은 받자마자 DB 를 들여다보게 하려는 **개발 우선 결정**(2026-08-12)이다. 배포 환경에서도 켤 수 있다(로그인이 막는다).

---

## 9. Celery

```python
def discover_task_modules(installed_apps):          # 새 Apps() 를 run_ready=False 로 채운다
    registry = Apps()
    registry.populate(installed_apps, run_ready=False)
    return registry.task_modules()                   # 앱별 <앱>.tasks 중 존재하는 것

celery_app = Celery("project", broker=redis_settings.REDIS_URL, backend=redis_settings.REDIS_URL,
                    include=discover_task_modules(INSTALLED_APPS))
# JSON serializer 만 허용, task_track_started, enable_utc=True, timezone=TIME_ZONE(일정 해석용), beat_schedule={}
```

- 태스크는 **기능 폴더의 `tasks.py`**(선택, `AppConfig.tasks_module`)에 `@celery_app.task` 로 정의한다. 예: `app/features/home/tasks.py` 의
  `home.aggregate_access_stats` — `background_session()` 으로 세션을 열고, 서비스는 HTTP 경로와 같은 home provider
  `build_user_access_log_service(session)` 로 조립한다(service-hardening ADR-012).
- 워커 `include` 는 `config.INSTALLED_APPS` 로 만든다. `app/celery` 는 어떤 기능도 import 하지 않는다(`tests/test_layering_and_openapi.py::test_celery_does_not_depend_on_features`).
  목록에서 앱을 빼면 그 앱의 태스크·모델도 워커에서 빠진다. 같은 registry 가 2단계(models)까지 돌므로 워커에서도 모든 설치 앱의 mapper 가 등록된다.
  `ready()` 는 돌리지 않는다 — 접속 로그 sink 결선은 API 프로세스 전용이다.
- 발견은 `importlib.util.find_spec` 으로 **존재만** 본다. 태스크 module 은 `celery_app` 을 import 하므로, 발견 단계에서 import 하면 순환 import 다.
  태스크 module 내부의 import 오류는 워커가 include 를 import 할 때 드러난다.
- 동기 태스크 안의 코루틴은 `app/celery/task.py` 의 `run_async()` 가 **worker 프로세스당 영속 event loop** 에서 실행한다.
- worker 종료: `app/celery/lifecycle.py` 가 `worker_process_shutdown` 신호에서 살아 있는 loop 로 `dispose_engine()` → `shutdown_asyncgens()` → loop close → 전역 참조 해제.
- **주기 실행(beat)**: 일정도 기능의 `tasks.py` 가 `celery_app.add_periodic_task(...)` 로 등록한다 — beat 는 기동 때 워커와 같은 `include` 로
  태스크 module 을 불러온 뒤 `beat_schedule` 을 읽으므로, 중앙 Celery 앱은 기능을 import 하지 않는다. 현재 일정은 home 의
  `home.purge_expired_access_logs`(매일 03:30, `timezone=TIME_ZONE` 기준) 하나다. 실행: `uv run celery -A app.celery.app beat --loglevel=info`
  (worker 와 별도 프로세스, **한 개만** — 여러 개면 같은 일정이 중복 실행된다).
- API 기동은 worker·beat 를 띄우지 않고, API lifespan 은 worker 의 broker 연결·loop 를 정리하지 않는다(소유권이 다른 프로세스).
- 태스크에는 살아 있는 세션·Service·Request 를 넘기지 말고 JSON 직렬화 가능한 id·값만 넘긴다. 재시도·멱등 정책은 태스크별로 정한다.

---

## 10. Alembic 마이그레이션

`migrations/env.py` 는 runtime 과 **같은 registry 구현**으로 모델을 모은다. 새 앱을 추가해도 이 파일은 고치지 않는다.

```python
fileConfig(config.config_file_name, disable_existing_loggers=False)   # 앱 로거를 끄지 않는다
Apps().populate(INSTALLED_APPS, run_ready=False)                      # ready() 부수효과 없음
target_metadata = Base.metadata
config.set_main_option(                                              # URL → 문자열, % 는 %% 로
    "sqlalchemy.url",
    db_settings.ALEMBIC_URL.render_as_string(hide_password=False).replace("%", "%%"),
)
```

- `target_metadata` 는 전역 `Base.metadata` 다. 같은 프로세스에서 미설치 모델을 먼저 import 하면 metadata 에 남으므로, registry 소유 모델만으로 완전히 필터링하는 구조는 아니다(Alembic CLI 의 깨끗한 프로세스에서는 설치 앱 모델만 들어간다).
- URL: `ALEMBIC_DATABASE_URL` 이 있으면 그 값을 `make_url()` 로 읽고(로컬·CI·SQLite), 없으면 primary URL 의 drivername 만 `mysql+pymysql` 로 바꾼다. DSN 은 모두 `sqlalchemy.engine.URL` 로 조립하므로 비밀번호의 `@ : / # ? %` 가 구분자로 읽히지 않는다. ConfigParser 보간 때문에 `%` 는 `%%` 로 넘긴다. **migration 은 항상 writer** 에서 실행한다.
- Alembic 은 FastAPI lifespan 에 들어가지 않으므로 Redis ping 을 하지 않는다. 서버 기동이 자동 upgrade 를 하지도 않는다.
- **배포 전**: `e5a7c2d9f310` 은 기존 MySQL 시각 값이 `+09:00` 으로 저장됐다고 가정한다 — 다른 시간대로 운영했다면 적용 전에 리비전의
  `LEGACY_OFFSET` 상수를 바꾸고, 적용 전에 백업한다(값을 UPDATE 문으로 다시 쓴다).
- revision 체인: `f4adf0ae24ea` baseline → `b2f1a9c0d3e4` user hashed_password → `c7d3e91b5a20` catalog_products → `d1f8c4a70b93` sales_orders → `e5a7c2d9f310` 시각 UTC·`DATETIME(6)`(MySQL 만 변환, 기존 KST 벽시계를 `CONVERT_TZ(col, '+09:00', '+00:00')` 로 UTC 로 옮긴다. SQLite 는 no-op) → `a3c9e8f1b274` `users.is_superuser`·blog/sns/reply `author_id`(head).
- 검증: `tests/core/test_migration_chain.py`(체인·스키마 = metadata), CI 의 단일 head 검사·SQLite `upgrade head` + `alembic check`, MySQL job 의 upgrade → downgrade -1 → 재-upgrade → check.

---

## 11. 운영·보안과 알려진 제한

### 11.1 배포 체크리스트 — 사람이 확인할 것

| # | 확인 | 빠뜨리면 |
|---|---|---|
| 1 | `DEBUG=false` (그리고 `LOG_LEVEL` 을 `DEBUG` 로 두지 않는다) | `/docs`·`/openapi.json` 공개, 시작 시 `create_all` 실행으로 스키마 관리 주체가 둘로 갈린다. production/staging 에서는 기동이 거부된다(§3.2) |
| 2 | 관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true`. 쓴다면 HTTPS 로만 접근(staging/production 쿠키는 `Secure`) | 켜 둔 `/admin` 은 로그인 화면을 공개한다(로그인은 필요하다). 예전 `ADMIN` 줄이 남아 있으면 기동이 멈춘다 |
| 3 | 외부 노출이 필요 없으면 `SERVER_HOST=127.0.0.1` | 기본 `0.0.0.0` — **앱은 이 조합을 막지 않는다.** 관리 화면을 내부망으로만 쓰려면 프록시에서 `/admin` 을 제한한다 |
| 4 | 비밀값 교체: `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY`(서로 다른 `secrets.token_urlsafe(48)` 값, 세션 키는 `/admin` 세션 ID → Redis 키 HMAC)·`MYSQL_PASSWORD`·`REDIS_PASSWORD` | 세 비밀키가 placeholder·32자 미만이거나 access·refresh 가 같으면 기동이 거부된다(test 외 모든 ENV). `MYSQL_PASSWORD` 는 빈 값·placeholder 를, `REDIS_PASSWORD` 는 값이 있을 때만 placeholder 를 거부한다(§3.2) — 그 밖의 약한 비밀번호는 앱이 판정하지 않는다 |
| 5 | CORS 는 실제 frontend origin 만 | `CORS_ALLOW_ORIGINS=["*"]` 와 `CORS_ALLOW_CREDENTIALS=true` 조합은 설정 로드가 거부한다 |
| 6 | Redis 는 **7.0 이상**, 인증·사설망 | startup 필수 자원이자 Celery broker·`/admin` 세션 저장소(Redis 를 쓸 수 없으면 관리 화면은 503). 7.0 미만이면 기동이 거부된다(`EXPIRE NX`). INFO 를 막은 관리형 Redis 는 확인을 건너뛰므로 버전을 직접 확인한다 |
| 7 | `DB_WORKER_PROCESSES`·`DB_MAX_SERVER_CONNECTIONS` 를 실제 값으로 | 트래픽이 몰릴 때만 "Too many connections" 로 드러난다 |
| 8 | 오케스트레이터가 `/health` 를 liveness, `/ready` 를 readiness 로 연결 | DB 흔들림에 프로세스 재시작 |
| 9 | 로그 보존·회전 정책과 민감값(Authorization·JWT·비밀번호·자격증명·과도한 요청 본문) 비기록 | — |
| 10 | 프록시 뒤 배포면 `TRUSTED_PROXY_HOPS` 를 **앞단 프록시 단 수**로 | 0 으로 두면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋(API·`/admin`)이 전체 사용자를 한 사람으로 취급한다(한 사람이 한도를 채우면 전원이 429). 크게 잡으면 위조된 `X-Forwarded-For` 를 믿어 IP 위조가 가능하다(service-hardening R-013) |
| 11 | 첫 관리자를 `scripts/create_superuser.py` 로 만들고(대화형 또는 `--password-stdin`), 관리 API 가 일반 토큰에 403 인지 확인 | 슈퍼유저가 없으면 관리 API 도 `/admin` 로그인도 쓸 수 없다. 리비전 `a3c9e8f1b274` 는 아무도 자동 승격하지 않는다 |
| 12 | KST→UTC 리비전 `e5a7c2d9f310` 적용 전 백업, 기존 값의 시간대가 `+09:00` 이 아니면 `LEGACY_OFFSET` 수정 | 모든 시각이 오프셋 차이만큼 어긋난 채 저장된다(§10) |
| 13 | `/admin` 은 슈퍼유저 로그인이 필요하다 — 세션은 Redis 서버 세션, `SESSION_SECRET_KEY` 는 세션 ID → Redis 키 HMAC 키. `ADMIN_SESSION_MAX_AGE_SECONDS`(절대)·`ADMIN_SESSION_IDLE_SECONDS`(미사용)를 정책에 맞춘다([README 세션·토큰 만료](../../README.md#세션토큰-만료)) | 키를 바꾸면 모든 관리 세션이 끊긴다(다시 로그인). Redis 를 읽을 수 있는 사람은 세션 내용(사용자 id·CSRF 토큰)을 본다 — Redis 접근을 통제한다 (쿠키는 HMAC 때문에 Redis 키로 만들 수 없다, admin-session-hardening R-008) |
| 14 | `ACCESS_LOG_RETENTION_DAYS` 를 개인정보 정책에 맞추고(기본 365일), Celery worker 와 **beat 한 개**를 띄운다 | beat 가 없으면 보존 삭제가 돌지 않아 접속 로그가 무기한 쌓인다(§6·§9) |

### 11.2 배포 절차와 확인

```bash
uv run alembic current            # 현재 리비전
uv run alembic upgrade head       # writer 에서 적용 (ALEMBIC_DATABASE_URL 로 DSN 분리 가능)
# 되돌리기: uv run alembic downgrade -1  (MySQL CI job 이 downgrade -1 → 재-upgrade 를 검증한다)
```

배포 후:

```bash
curl -s https://<host>/health                                            # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/ready            # 200 (DB·Redis 준비), 아니면 503
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/docs             # DEBUG=false 면 404
curl -s -o /dev/null -w '%{http_code}\n' https://<host>/admin/           # 302(로그인 화면으로), ADMIN_DISABLED=true 면 404
```

API 와 worker 의 코드·환경 버전을 맞춘다. 무중단 migration 순서·백업/복구 시험은 배포 인프라에서 별도로 승인한다(이 저장소는 이미지 빌드·배포를 다루지 않는다).

### 11.3 알려진 제한 (구현되지 않은 것)

전제로 삼지 않는다.

- **API 인가의 세분**: 슈퍼유저/일반 2단계뿐이다(역할·권한 테이블 없음). `Principal` 은 토큰 claims 로 만들므로 강등·비활성화는 refresh 폐기로
  다음 회전부터 막히고, 이미 발급된 access 는 만료까지 이전 권한을 가진다.
- **관리 화면 인증의 범위**: 슈퍼유저 한 등급만 들어간다(관리 화면 안의 세분 권한 없음). 상태를 바꾸는 관리 요청은 모두 CSRF 토큰을 요구하지만
  sqladmin 사용자 정의 `@action`(GET 라우트)은 보호 밖이다 — 이 저장소는 쓰지 않는다(admin-session-hardening R-001). 관리 화면과 API 는
  같은 판정(`revocation_for_change`)으로 같은 집합을 커밋 전에 폐기한다(R-007 해소). 같은 경로를 메서드별 라우트로 나눈 경우 405 의 `Allow` 가 불완전하다
  (사용자 결정으로 현행 유지, R-002). 익명 로그인 화면 방문도 Redis 세션(미사용 30분)을 만든다(R-003).
- **access 토큰 즉시 폐기**: 블랙리스트 없음 — 짧은 수명(15분)과 refresh 폐기(logout·재사용 탐지·비활성화·강등·비밀번호 변경·삭제)로 대신한다.
- **접속 로그 신뢰 경계**: `ip_address` 는 `TRUSTED_PROXY_HOPS` 가 실제 프록시 홉 수와 같을 때만 정확하다 — 값이 실제보다 크면 위조된 XFF 값을 믿는다.
  `forwarded_for`·`real_ip` 열은 헤더 원문이라 위조될 수 있다. Referer·User-Agent·`session_id` 쿠키 원문과 (민감 키를 가린) query string 이 저장된다
  (사용자 결정). 보존 기간은 `ACCESS_LOG_RETENTION_DAYS`(기본 365일)이고 beat 가 떠 있어야 삭제된다(§6). 개인정보 정책을 배포 측에서 정한다.
- **접속 로그 내구성**: best-effort(상한 초과 drop, 종료 drain 5초). drop 과 drain timeout 로그를 모니터링한다.
- **레이트 리밋**: 인증 엔드포인트(로그인·가입)에만 있다(§7). 그 밖의 요청 한도는 리버스 프록시나 API gateway 에서 건다.
- **자동 앱 탐색**: 없음(설계 원칙).
- **미사용 설정**: 없다. 메일·업로드 설정과 SESSION_EXPIRE_SECONDS(config-cleanup), API 버전 설정(config-cleanup-2)은 지웠다(`.env` 에 남아도 무시된다). 로그 포맷·콘솔 스위치는 로깅 구성에 연결했다(§5). 새 설정이 읽히지 않으면 `tests/core/test_settings_contract.py` 가 막는다.
- **검증하지 않은 것**: Raw 집계의 실행 계획·실제 replica 지연·부하 한계(운영급 데이터 필요), 실제 배포 플랫폼의 secret store·TLS·프록시 ACL.

---

## 12. 변경 이력

아래는 과거 기록이다. 옛 이름·옛 경로가 나오는 것이 정상이며, 현재 사용법은 본문을 따른다.

| 날짜 | 변경 내용 |
|---|---|
| 2026-10-22 | **HTML 가이드 사이트**(docs-guide-site): `docs/guides/index.html` 허브 아래 부팅·아키텍처·API·설정·요청 처리·인증·시퀀스·기능 8편·개발·테스트·운영 HTML 을 더하고 검수 지적을 코드대로 고쳤다. 내용 계약은 `tests/test_docs_guide_site.py`. |
| 2026-10-21 | **가이드 검수 반영**(docs/guide-fixes): 안내서·ARCHITECTURE·DEVELOPMENT·README 의 틀린 값과 누락을 코드에 맞췄다 — 조립 8단계, `/ready` 의 DB·Redis, 리비전 head `a3c9e8f1b274`, 배포 안전 검사 범위, 오류 경로(Redis 503·처리기 없는 예외 500·422) (`docs/crp/groups/docs-guide-review/`) |
| 2026-10-21 | **e2e-policy-2 · 문서 구조 개편**: OpenAPI 422 를 실제 `ErrorResponse` 로 광고, 처리기 없는 예외를 `answer_unhandled_exception` 미들웨어가 500 으로 끝냄(연결 유지), 모든 401 에 `WWW-Authenticate: Bearer`, `create_superuser` 의 명령줄 비밀번호 폐기, 인증 조회 primary, 관리 화면 503, CSRF 상한. `aiomysql[rsa]` 로 `cryptography` 선언 통일. 가이드를 `docs/guides/`(index.html·`workflows/`)로 재배치 (`docs/crp/groups/integration-e2e/`) |
| 2026-10-21 | **integration-e2e**: 실제 uvicorn·MySQL·Redis·Celery 를 띄우는 전수 통합 테스트(`e2e` 마커)와 CI e2e job, Redis 연결 오류 → 503(`redis_unavailable_handler`), 사용자 결정 3건 (`docs/crp/groups/integration-e2e/`) |
| 2026-10-19 | **logging-overhaul**: 앱·`python main.py`·`uvicorn main:app` CLI·Celery 워커가 같은 dictConfig·형식을 쓴다(uvicorn 로거는 root 로 전파, Celery `--logfile` 존중). 헤더 판별을 한 함수로(외부 라이브러리는 로거 이름 표), 포맷 필수 필드 검사, `LOG_APP_LEVELS`(헤더별 레벨 필터), 파일을 프로세스별(`app.log`·`error.log`·`celery.log`·`celery-error.log`·`celery-beat*.log`)로, 날짜(UTC 자정)+크기 회전과 `LOG_RETENTION_DAYS`. `LOG_APP_FILENAME`·`LOG_ERROR_FILENAME`·`LOG_BACKUP_COUNT` 삭제(남아도 무시). DSN 계정명도 가리고 `LOG_REDACTED_SETTINGS` 의 값 원문을 가린다(§5) |
| 2026-10-19 | **config-cleanup-2**: `API_VERSION`·`ApiSettings` 를 지웠다(`.env` 에 남아도 무시). `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`·`LOG_CONSOLE_ENABLED` 를 로깅 구성에 연결했다 — 앱·`python main.py` 의 uvicorn·Celery 워커(`setup_logging` 수신자)가 같은 값을 따른다. 기본값은 기존 하드코딩 형식과 같아 기본 출력은 그대로다. 잘못된 포맷은 설정 로드에서 거부, 출력이 모두 꺼지면 stderr 경고 한 줄. 설정 계약 테스트의 예외 목록을 없앴다(§3.2·§5) |
| 2026-10-19 | **config-cleanup**: 읽는 곳이 없던 `SMTPSettings`(`smtp_settings`)·`UploadSettings`(`upload_settings`)·`SESSION_EXPIRE_SECONDS` 를 지웠다(배포 안전 검사의 `SMTP_PASSWORD` 항목 포함). 남은 `.env` 줄은 `extra="ignore"` 로 무시된다. 세션·토큰 만료는 README 표 한 곳으로 모았고, 설정 필드가 운영 코드에서 읽히는지 보는 계약 테스트를 더했다 |
| 2026-10-19 | **admin-session-hardening (판정을 한 함수로 — 집합은 `UserService` 와 같다)**: 폐기 판정을 `revocation_for_change`·`revocation.REVOKE_ON_DELETE`·`revocation.REVOKE_ON_PASSWORD_CHANGE` 한 곳으로 모았다 — API·관리 화면·`create_superuser --set-password` 가 같은 판정을 쓴다. 집합은 `UserService` 가 원래 지우던 것과 같다(비활성화·강등·삭제 = refresh + 관리 세션, service-hardening 동작 유지)에 비밀번호 변경(둘 다)을 더했다. 비밀번호 변경 스크립트는 관리 세션과 refresh 를 함께 지운다(`revoke_sessions_in_redis`). 폐기는 커밋 전(fail-closed, §7.1·§8, ADR-010) |
| 2026-10-19 | **admin-session-hardening**: `/admin` 세션을 서명 쿠키(starlette `SessionMiddleware` + itsdangerous)에서 Redis 서버 세션(`AdminSessionStore`·`RedisSessionMiddleware`, 쿠키에는 세션 ID 만, 절대·미사용 만료 `ADMIN_SESSION_*`)으로 옮겼다 — 로그아웃·비활성화·강등·삭제·비밀번호 변경 시 즉시 폐기(`UserSessionRevoker` — API·`UserAdmin` 이 같은 폐기 집합 refresh + 관리 세션을 커밋 전에, `create_superuser --set-password` 는 관리 세션), Redis 장애 시 관리 화면 503. 로그인 이후 모든 상태 변경 요청에 CSRF(`AdminCsrfMiddleware`, 덮어쓴 `sqladmin/base.html`), 로그아웃 POST 전용(GET 405). `LocalDateFilter` 에 기간(`S~E`) 연산. `itsdangerous` 직접 의존 제거. 405 `Allow` 불완전은 사용자 결정으로 현행 유지(§8·§11) |
| 2026-10-19 | **security-ops-hardening**: 모든 엔진에 `hide_parameters=True`(엔진 옵션 정본 `session.ENGINE_SAFETY_OPTIONS`, §4.3) — DB 오류·로그에 바인드 값이 남지 않는다. 접속 로그 보존 기간 `ACCESS_LOG_RETENTION_DAYS`(기본 365일)와 매일 03:30 Celery beat 삭제(배치 5,000행, §6·§9). `/admin` 로그인 폼 CSRF 토큰(synchronizer token, 레이트 리밋보다 먼저 확인, §8). 관리 목록 `created_at` 날짜 필터 `LocalDateFilter`(§8). access 토큰 15분과 권한 회수 지연은 사용자 결정으로 유지 (`docs/crp/groups/security-ops-hardening/`). |
| 2026-10-13 | **log-redaction-fixes**: 로그 메시지·traceback·`stack_info` 의 비밀값 가리기(LogRecord factory — uvicorn CLI·Celery 포함, §5), Starlette `HTTPException` 핸들러가 `headers` 를 보존(405 `Allow`), Redis 최소 버전 7.0 정의와 기동 확인(§3.4), 커버리지 하한 기본 0(NFR-08). 접속 로그의 `session_id`·Referer·XFF 원문 저장은 사용자 결정으로 유지 (`docs/crp/groups/log-redaction-fixes/`). |
| 2026-10-12 | **admin-login**: `/admin` 에 슈퍼유저 세션 로그인(`AdminAuthBackend`, Bootstrap 로그인 화면, `admin_session` 서명 쿠키, 매 요청 DB 재확인)을 붙였다. 예전 무인증 승인 플래그와 배포 환경의 관리 화면 거부 규칙을 없앴고, `ADMIN` 을 `ADMIN_DISABLED`(true=끔, 흔적 없음)로 교체했다 — 예전 이름이 남아 있으면 기동이 멈춘다. `itsdangerous` 의존성 추가. 별도 [관리 화면 인증 가이드](workflows/admin-authentication.html) (`docs/crp/groups/admin-login/`). |
| 2026-10-12 | **service-hardening**: DSN `URL.create`, 잠금 읽기 writer 고정, 결정적 정렬, 신뢰 홉 기반 클라이언트 IP, UTC·마이크로초 저장, Redis 필수와 `/ready`, 기능별 Celery 태스크, 인증 코어(Argon2·토큰 claims·refresh 회전·레이트 리밋), 인가(`Principal`·`OwnershipPolicy`·슈퍼유저·`scripts/create_superuser.py`, §7.1) (`docs/crp/groups/service-hardening/`). |
| 2026-09-21 ~ 2026-10-02 | **읽기 전용 강제를 라우터와 분리 + 게이트·문서 위생**: 읽기 전용 세션의 쓰기 차단을 `get_bind()` 안에서 `Session` 전역 이벤트(`before_flush`·`do_orm_execute`)로 옮겨 `DB_ROUTER_ENABLED` 와 무관하게 항상 동작하게 했다 — 이전에는 **기본 설정(라우터 off)에서 차단이 통째로 없었다**(§4.4, `tests/core/test_read_only_guard.py`). `ValidationException` 을 `HTTP_422_UNPROCESSABLE_CONTENT` 로 옮겼다(값은 그대로 422, starlette 1.x 폐기 예고). 게이트에 `pip-audit` 단계를 넣어 9단계가 됐고, 게이트를 가리키는 문서 포인터를 번호에서 **스텝 이름**으로 바꿨다(번호는 단계가 끼면 밀린다). `filterwarnings` 를 `error::` 로 올리고 파일 핸들 누수를 없앴다. `redis 6.4.0`·`uvicorn 0.54.0` 상향, pyjwt 권고 10건 해소. 문서가 인용한 비밀값이 배포 안전 검사에 걸리는지 보는 `tests/test_docs_secret_examples.py` 를 신설했다. |
| 2026-09-17 | **HTML 안내서 복원 + 정합성 점검**: 재구성에서 지운 `server-lifecycle-guide.html`·`feature-development-guide.html` 을 되살려 현재 코드·Markdown 과 맞췄다(다른 저장소 비교 제거, 부록 설정표를 `config.py` 에서 재생성). README 「문서 안내」를 `문서 / 역할 / 언제 보나` 표로 바꾸고 두 안내서를 넣었다. 코드 설명 정정: `API_DESCRIPTION`(다른 프로젝트 제목·UnitOfWork 제거), `pyproject.toml` 이름·설명, `/api/v1/catalog/products` 설명(`active_only=false` 는 정렬 없음), 미사용 설정(`ApiSettings`·`SessionSettings`·`SMTPSettings`·`UploadSettings`·`LOG_CONSOLE_ENABLED`·로그 포맷 3종) 표기, `ENV` 가 `/health` 에 포함된다는 잘못된 주석. 문서 검사에 HTML(코드 경로·`data-source`·링크·앵커·꺾쇠 이스케이프)과 Markdown 앵커 검사를 추가했다. 같은 날 후속: 모든 쓰기 핸들러를 **응답 DTO 검증 → commit** 순서로 통일했다(이전에는 commit 후 검증이라 DTO 실패 시 데이터가 남았다, `tests/test_validate_before_commit.py`). Python 규칙을 `>=3.13`·ruff `py313`·mypy `3.13` 으로 올렸다. |
| 2026-09-17 | **문서 재구성**: 진입·아키텍처·개발 세 문서로 통합했다. `docs/guides/QUICKSTART.md` 는 README 로, `docs/project-guide/v1.1/`(10편)·`docs/django-style-app-registry/`(3편)·HTML 안내서 2편(`server-lifecycle-guide.html`·`feature-development-guide.html`)은 이 문서와 `docs/guides/DEVELOPMENT.md` 로 흡수한 뒤 삭제했다. 삭제된 통합 계획서의 요구 ID 의미(§2.8)와 운영 준비 계획·배포 문서의 여전히 참인 항목(§11)을 코드와 대조해 되살렸다. 정정: 운영 Admin 차단은 존재한다(ACK 없으면 기동 거부), 공개 API 는 22 경로 / 37 오퍼레이션, 파일 로그는 staging/production 에서만, `exists()` 는 PK 인자. |
| 2026-09-17 | **가이드 문서 위치 이동 + 현행화**: `docs/ARCHITECTURE.md`·`docs/QUICKSTART.md` 를 `docs/guides/` 로 옮기고 HTML 안내서 2종과 함께 현재 작업 트리 기준으로 대조했다. startup 필수 Redis `ping()` 과 종료 순서(background → Redis → DB), read-only 차단 범위, Alembic URL 결정 경로, 생성기의 태그 선언 단계, 테스트 마커·게이트 명령을 정정·보강했다. 같은 날 착수 명세 3종을 `docs/specs/orm-raw-repository/` 로 복원했다(코드 주석 인용 대상). |
| 2026-08-25 | **골격 목적 기준 검수 + 문서 정리**: 완료된 착수 명세 5종과 폐기된 가이드 버전(`project-guide/v1.0/`)을 삭제했다. 문서가 없는 기능을 있다고 서술한 것들을 정정했다(`require_admin`·`AppRegistry.discover()` 부재, `/ready` 실재, Raw 계층 실재). 생성기 골격에 `operation_id` 를 넣어 만든 즉시 OpenAPI 계약 검사를 통과하게 했다. 기록: `docs/crp/groups/skeleton-purpose-audit/`. |
| 2026-08-20 | 학습 경로 정비 — `project-guide/v1.1` 신설, 진입 문서와 심화 문서를 연결하고 검사로 잠갔다(`docs/crp/groups/learning-path/`). |
| 2026-08-19 | ORM/Raw 두 Repository 계열과 예제 2종(`catalog`·`reports`) 추가(`docs/crp/groups/orm-raw-repository/`). |
| 2026-08-13 | **레이트 리밋 제거**: `app/core/rate_limit.py`·`slowapi`·`RATE_LIMIT_*` 설정·`auth` 라우트 데코레이터 삭제. 요청 한도는 리버스 프록시나 API gateway 에서 건다. |
| 2026-08-12 | **Django app registry 이식**: 기능이 더 진전된 구현 기준선 위에 `app/core/apps/`(`AppConfig`·`Apps`·`wiring`)와 `app/core/bootstrap.create_app()` 을 추가했다. 설치 SSOT 가 `config.INSTALLED_APPS` 로 일원화되어 `main.py` 의 `include_router` 나열, 중앙 admin 취합 파일(`app/features/admin.py`·`ADMIN_VIEWS`), 디렉터리 스캔 모델 수집(`models_registry`)을 모두 대체했다. 기능 `__init__.py` 는 가벼운 marker 가 되고 home sink 등록은 `HomeConfig.ready()` 로 이동했다. |
| 2026-08-11 | **`app/features/` 명칭 확정 + SQLAdmin 소유권을 기능으로 이전**: `app/domains` → `app/features`. ModelView 는 모델과 같은 폴더의 `admin.py` 가 소유한다(과거 `getattr(module, "admin_views", [])` 관용 수집은 빈 `admin.py` 를 무신호로 건너뛰어 복원하지 않음). 같은 날 §4 문서 드리프트(의존성 `yield` 후 커밋 서술)를 핸들러 커밋으로 정정하고, `tests/features/` 잔류분을 `app/features/<name>/tests/` 로 통합했다. 한때 Django 배선을 걷어내고 명시 `include_router`·중앙 `ADMIN_VIEWS` 로 돌렸으나 다음 날 registry 로 복귀했다. |
| 2026-07-01 | 표준 FastAPI 배선으로 전환: `AppRegistry`/`create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py` 가 `router` 공개 + `main.py` 가 명시 `include_router`. |
| 2026-06-23 | 기능 모델 레지스트리 아키텍처로 전환, 이 문서 최초 작성. 자동 발견 제거, `app/apps.py` 수동 등록 SSOT 로 전환. |
