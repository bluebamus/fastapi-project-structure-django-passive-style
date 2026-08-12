# Django app registry 호환 범위

## 1. 이 문서가 답하는 질문

"Django식" 이라는 표현이 **어디까지 실제 호환이고 어디부터 단순 영감인지** 를 구분한다.
이 구분이 없으면 Django 경험자가 없는 기능을 있다고 가정하거나, 있는 기능을 직접 다시
만든다.

기준 문서: [Django 6.0 — Applications](https://docs.djangoproject.com/en/6.0/ref/applications/)

provenance:

- 구현 기준선: `fastapi-default-project-structure` `a980b71`
- passive 참조점: `fastapi-project-structure-django-passive-style` `85153fb`

## 2. 세 가지 등급

| 등급 | 의미 |
|---|---|
| **동일** | Django 의 공개 의미를 그대로 보존한다. 이름·순서·실패 조건이 같다. |
| **확장** | Django 에는 없는 이 프로젝트 전용 동작. FastAPI/SQLAlchemy 결선이 여기 속한다. |
| **비지원** | 구현하지 않는다. Django 코드를 그대로 옮기면 동작하지 않는다. |

## 3. 동일 — app loading lifecycle

| 항목 | Django | 이 프로젝트 |
|---|---|---|
| 설치 목록 | `settings.INSTALLED_APPS` | `config.INSTALLED_APPS` |
| 항목 형식 | package 경로 또는 `AppConfig` class 경로 | 동일 |
| 기본 config 선택 | `<package>.apps` 검사 — 0개면 기본 `AppConfig`, 1개면 그것, 복수면 `default=True` 하나 | 동일 |
| 정규화 결과 | `AppConfig` 인스턴스 (`name`·`label`·`verbose_name`·`path`·`module`) | 동일 |
| `label` 기본값 | `name` 의 마지막 조각, 유효한 Python identifier | 동일 |
| `verbose_name` 기본값 | label 의 title 표현 | 동일 |
| 초기화 단계 | ① config/root package → ② models → ③ `ready()` | 동일 |
| 단계 진행 방식 | phase 단위(앱별로 섞이지 않음) | 동일 |
| 순서 | `INSTALLED_APPS` 순서 | 동일 |
| 준비 상태 | `apps_ready` · `models_ready` · `ready` | 동일 |
| 고유성 | `name` 과 `label` 각각 유일 | 동일 |
| 조회 API | `get_app_configs()` · `get_app_config(label)` · `is_installed(name)` · `get_models()` · `get_model(app_label, model_name)` | 동일 (`get_model` 은 대소문자 무시) |
| 미준비 조회 | 명시적 예외 | `AppRegistryNotReady` |
| 조회 실패 | `LookupError` | `AppLookupError` (`LookupError` 서브클래스) |
| 재진입 | 금지 | `RuntimeError` |
| 중복 populate | no-op | 동일 |

### 3.1 예외 이름 대응

| Django | 이 프로젝트 |
|---|---|
| `django.core.exceptions.ImproperlyConfigured` | `app.core.apps.exceptions.ImproperlyConfigured` |
| `django.core.exceptions.AppRegistryNotReady` | `app.core.apps.exceptions.AppRegistryNotReady` |
| `LookupError` | `app.core.apps.exceptions.AppLookupError` |

## 4. 확장 — 이 프로젝트 전용

Django 에는 없다. **Django 기능이라고 부르지 않는다.**

| 항목 | 동작 |
|---|---|
| Router 결선 | `AppConfig.router_module`(기본 `api.routers.router`)의 `<label>_router` 를 `router_prefix`(기본 `/api`)로 마운트 |
| Admin 결선 | `AppConfig.admin_module`(기본 `admin`)의 `admin_views` 를 SQLAdmin 에 등록 |
| Model 수집 | SQLAlchemy declarative 매핑 class 중 `__module__` 이 앱 package 하위인 것 |
| Alembic 통합 | `migrations/env.py` 가 같은 registry 를 `run_ready=False` 로 채운다 |
| `create_app()` | 설치 앱·registry·Admin 활성화를 주입받는 factory |
| route 충돌 검사 | 두 앱이 같은 method+path 를 등록하면 기동 실패 |
| 선택 module 구분 | module 부재는 허용, module 내부 import 실패는 기동 실패 |

`app/core/apps/wiring.py` 가 이 확장을 담당한다. `config.py`·`registry.py` 는 FastAPI 도
SQLAdmin 도 SQLAlchemy 도 import 하지 않는다.

## 5. 비지원 — 구현하지 않는다

| Django 기능 | 대체 |
|---|---|
| Django ORM (`models.Model`, QuerySet, manager) | SQLAlchemy 2.0 async |
| Django migration engine | Alembic |
| URLConf (`urls.py`, `path()`, `reverse()`) | FastAPI `APIRouter` |
| signals (`post_save` 등) | 명시적 Service 호출 |
| template / static 자동 탐색 | 없음 (API 전용) |
| management command 프레임워크 | `scripts/` 의 개별 스크립트 |
| `AppConfig.default_auto_field` | SQLAlchemy 모델이 직접 선언 |
| `apps.get_containing_app_config(object_name)` | 없음 |
| app 별 `INSTALLED_APPS` 조건부 구성(settings 분기) | 없음 — 목록은 코드 리뷰 대상 |
| 앱 제거 시 데이터 migration 자동 생성 | 없음 (§7 참고) |

## 6. `ready()` 의 제약

Django 는 `ready()` 에서 DB 접근을 **권장하지 않는다**. 이 프로젝트는 그것을 계약으로
못박는다.

허용:

- 모듈 전역 변수 결선 (예: access-log sink 등록)
- 다른 앱의 model 조회 (`apps.get_model(...)`)

금지 (SEC-05):

- DB 쿼리·커밋
- network 호출
- subprocess 실행
- secret 출력

이유는 migration 과 CLI 도 이 hook 을 실행할 수 있기 때문이다. `alembic upgrade` 가
외부 시스템에 연결을 만들면 배포 절차가 예측 불가능해진다.

`migrations/env.py` 는 아예 `run_ready=False` 로 population 해 hook 자체를 건너뛴다.
config·models 단계는 runtime 과 **같은 구현** 을 공유한다.

회귀 가드: `tests/core/apps/test_installed_apps.py::test_ready_hooks_perform_no_io`
(구현을 AST 로 읽는다 — 실행 검사는 "이번엔 안 했다" 까지만 말해준다.)

## 7. 앱 비활성화·제거 시 주의

**목록에서 빼도 테이블은 지워지지 않는다.**

앱을 `INSTALLED_APPS` 에서 제거하면:

1. route 가 사라진다 (즉시)
2. Admin view 가 사라진다 (즉시)
3. `ready()` 가 실행되지 않는다 (즉시)
4. 그 앱의 model 이 `Base.metadata` 에서 빠진다 → **`alembic revision --autogenerate` 가
   `DROP TABLE` 을 제안한다**

4번이 위험하다. 데이터를 보존해야 한다면 생성된 마이그레이션을 그대로 적용하지 말고,
의도적으로 편집하거나 앱을 목록에 남긴 채 route 만 비활성화할지 검토한다.

제거 절차 권장:

```text
1. 앱을 목록에서 뺀다 → 테스트 실행 → route/Admin 이 사라졌는지 확인
2. alembic revision --autogenerate 로 제안된 diff 를 **읽는다**
3. 데이터가 필요 없으면 그대로, 필요하면 편집하거나 별도 보존 절차를 만든다
4. alembic upgrade head
```

## 8. 요구사항 대응표

| 이 문서의 절 | 요구사항 |
|---|---|
| §3 동일 | FR-02·FR-03·FR-05, CR-01~CR-07, NFR-01·NFR-02·NFR-04·NFR-05 |
| §4 확장 | FR-04·FR-06·FR-07, CR-08, NFR-06 |
| §5 비지원 | 통합 계획 §4.2 제외 범위 |
| §6 `ready()` 제약 | FR-08, SEC-05 |
| §7 제거 주의 | BC-05, 통합 계획 §11 위험표 |
