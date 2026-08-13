# Django식 수동 앱 등록 재구축 계획

## 1. 문서 정보

- 작성일: 2026-08-12
- 대상 저장소: `fastapi-project-structure-django-passive-style`
- 기준 저장소: `../fastapi-default-project-structure`
- 기준 저장소 기준점: `main` / `a980b71`
- 대상 저장소 참조점: `main` / `85153fb`
- 산출물 성격: 분석, 기획, 설계 및 개발·통합 작업 계획
- 이번 작업 범위: 문서 작성만 수행하며 브랜치 생성, 코드 복사, 구현, 커밋 및 푸시는 수행하지 않는다.

## 2. 최종 목표

이 프로젝트는 `fastapi-default-project-structure`의 최신 구조와 기능을 그대로 기반선으로 삼고, 여기에 Django의 앱 registry 동작을 FastAPI에 맞게 이식한 개발용 프로젝트 기본 구조를 제공한다.

목표는 단순히 `INSTALLED_APPS`라는 이름의 목록을 추가하는 것이 아니다. 다음 동작을 하나의 일관된 설치 계약으로 제공해야 한다.

1. 앱 설치 여부와 순서를 `INSTALLED_APPS`에서 명시적으로 결정한다.
2. Python package 경로 또는 `AppConfig` class 경로로 앱을 등록한다.
3. 등록 항목을 `AppConfig` 인스턴스로 정규화한다.
4. 등록 순서에 따라 앱 package, models, `ready()`를 단계적으로 처리한다.
5. 중복 name·label, 존재하지 않는 package, 잘못된 설정 class, 내부 import 오류를 시작 단계에서 구분해 실패시킨다.
6. 완성된 registry를 런타임, Alembic, Router, SQLAdmin 및 테스트가 공동으로 사용한다.
7. 앱 디렉터리 생성만으로 설치되지 않으며 반드시 목록에 추가해야 활성화된다.

FastAPI에 존재하지 않는 Django ORM, URLConf, signal framework, template loader, management command 전체를 복제하는 것은 목표가 아니다. 이 계획에서 “Django와 동일한 동작”은 **Django app loading과 registry lifecycle의 공개 의미를 보존**한다는 뜻이며, Router·SQLAdmin 결선은 FastAPI 전용 확장으로 정의한다.

## 3. 근거와 현황 분석

### 3.1 Django 기준 동작

Django 6.0 공식 문서는 앱 registry를 설정과 introspection을 보관하는 중앙 registry로 정의한다. `INSTALLED_APPS`에는 application module 경로나 configuration class 경로를 넣을 수 있고, 앱은 목록 순서대로 다음 세 단계에서 초기화된다.

공식 기준 문서: [Django 6.0 — Applications](https://docs.djangoproject.com/en/6.0/ref/applications/)

1. application configuration과 root package import
2. 각 앱의 models import
3. 각 `AppConfig.ready()` 호출

또한 app `name`과 `label`은 프로젝트 내에서 유일해야 하며, registry가 완성된 뒤 `get_app_configs()`, `get_app_config()`, `is_installed()` 같은 조회 API를 제공한다.

계획 구현은 이 공개 계약을 기준으로 하되 SQLAlchemy 모델과 FastAPI Router를 사용한다.

### 3.2 기준 저장소의 현재 구조

`fastapi-default-project-structure` `a980b71`은 현재 다음 방식으로 조립된다.

- `main.py`가 `auth`, `home`, `blog`, `reply`, `sns`, `user`를 직접 import한다.
- 각 Router를 `app.include_router(..., prefix="/api")`로 직접 등록한다.
- `app/core/db/models_registry.py`가 `app/features/*`를 파일 시스템에서 스캔해 모델을 import한다.
- `app/features/admin.py`가 기능별 `admin_views`를 직접 import해 `ADMIN_VIEWS`를 구성한다.
- Alembic도 자동 모델 스캔 함수에 의존한다.
- `auth`, validation, 최신 응답 직렬화, 테스트와 CI 계약 등 대상 저장소보다 진전된 기능이 있다.

즉, 기준 저장소는 기능이 풍부하고 현재 개발 기준선으로 적합하지만 앱의 설치 여부를 한 목록에서 통제하지는 않는다.

### 3.3 대상 저장소 main의 재사용 가치

`fastapi-project-structure-django-passive-style` `85153fb`에는 다음 참조 구현이 있다.

- `config.INSTALLED_APPS`
- `app/core/registry.py`
- `app/core/bootstrap.py`의 `create_app()` factory
- Registry 기반 Alembic metadata 구성
- `scripts/new_app.py`와 수동 등록 안내
- Router, Models, Admin 선택 모듈의 부재와 내부 import 실패를 구분하는 검사
- 등록 순서, 누락 package, 중복 항목 및 결선 결과에 대한 구조 테스트

그러나 현재 구현은 짧은 앱 이름을 `app.features.<name>`로 변환하는 컨벤션 중심 방식이다. Django와 비교하면 다음 계약이 빠져 있다.

| 항목 | 대상 main 현재 상태 | 목표 상태 |
|---|---|---|
| `INSTALLED_APPS` 항목 | `"home"` 같은 짧은 이름 | package 경로와 `AppConfig` class 경로 |
| 앱 설정 객체 | `AppModule` dataclass | Django 의미에 맞춘 `AppConfig` |
| 구성 자동 선택 | 없음 | `<package>.apps`의 기본 config 선택 |
| 고유성 | 짧은 이름 중복만 검사 | `name`과 `label` 각각 검사 |
| 초기화 단계 | package import 후 models import | config/root package → models → `ready()` |
| 상태 | 설치 목록만 보관 | `apps_ready`, `models_ready`, `ready` |
| lifecycle 보호 | 매 호출 재구성 가능 | thread-safe, idempotent, non-reentrant populate |
| 조회 API | `enabled_apps` | `get_app_configs`, `get_app_config`, `is_installed` |
| 앱 후처리 | `__init__.py` 부수효과 | 명시적인 `ready()` hook |

따라서 대상 main의 코드는 이식 재료이지 최종 명세 자체는 아니다.

### 3.4 두 저장소를 다루는 원칙

새 브랜치의 파일 내용은 기준 저장소에서 시작한다. 대상 main에서 통째로 덮어쓰는 파일 집합을 만들지 않는다.

```text
기준 저장소 a980b71의 전체 tracked tree
  + Django-compatible AppConfig / Apps registry
  + FastAPI Router·SQLAdmin adapter
  + registry를 사용하는 app factory와 Alembic
  + startapp형 generator와 구조 계약 테스트
  = 새 passive-style 구현
```

이 방식은 “default 프로젝트에 수동 앱 기능만 추가한다”는 목적을 지키며, 대상 main에만 있는 과거 공통 코드 변경이 기준 저장소의 최신 기능을 되돌리는 일을 막는다.

## 4. 범위

### 4.1 포함 범위

- 기준 저장소 tracked tree를 새 구현 브랜치의 기준선으로 복제
- Django식 `INSTALLED_APPS` 항목 해석
- `AppConfig`와 중앙 `Apps` registry
- 3단계 population과 `ready()` hook
- 앱·model introspection API의 FastAPI/SQLAlchemy 대응 범위
- Registry 기반 Router, SQLAlchemy model, SQLAdmin 등록
- Registry 기반 Alembic metadata 구성
- `create_app()` factory와 startup 결선
- Django `startapp`에 대응하는 앱 scaffold command
- 구조, lifecycle, 회귀, migration 및 품질 테스트
- 목적·사용법·호환 범위를 설명하는 문서
- 작업 브랜치 검증 후 대상 저장소 `main`으로 통합하고 push하는 절차

### 4.2 제외 범위

- Django 자체를 dependency로 추가
- Django ORM, migration engine, URLConf, signals, template/static discovery 복제
- `fastapi-default-project-structure` 저장소 자체 수정
- 디렉터리 스캔만으로 앱을 자동 활성화하는 active-style 동작
- 앱별 비즈니스 API의 재설계
- 앱 제거에 따른 데이터 migration 자동 생성
- 현재 요청에서 실제 브랜치 생성, 코드 구현, merge, commit 또는 push

## 5. 요구사항 정의

### 5.1 요구사항 작성 규칙

이 절은 개발자가 추가 해석 없이 테스트와 구현 작업으로 옮길 수 있는 실행 명세다.

- `FR-*`: 프로젝트가 제공해야 하는 기능
- `CR-*`: Django application registry와 대응해야 하는 동작
- `NFR-*`: 결정성, 안정성, 오류 가시성 및 유지보수성
- `BC-*`: `fastapi-default-project-structure` 기준 기능의 하위 호환성
- `SEC-*`: 초기화·Admin·파일 생성·기준선 복사 과정의 보안 요구사항
- `AC-*`: 구현 완료 여부를 판정하는 검증 가능한 인수 조건

요구사항 문장에서 “해야 한다”는 필수 항목을 뜻한다. `AC-*`가 연결되지 않은 기능 요구사항은 완료 처리할 수 없으며, 구현 중 요구사항을 변경하면 이 절과 추적성 표를 먼저 갱신한다.

### 5.2 기능 요구사항 (`FR-*`)

| ID | 요구사항 |
|---|---|
| FR-01 | 설치 앱의 유일한 진실 공급원은 `config.INSTALLED_APPS`여야 하며, 앱 디렉터리의 존재만으로 활성화되어서는 안 된다. |
| FR-02 | `INSTALLED_APPS`는 application package 경로와 explicit `AppConfig` class 경로를 모두 입력으로 받아야 한다. |
| FR-03 | 각 등록 항목은 `name`, `label`, `verbose_name`, `path`, root module을 가진 하나의 `AppConfig` 인스턴스로 정규화되어야 한다. |
| FR-04 | Registry는 설치된 앱의 Router, Models, Admin 구성요소를 앱 설정에 따라 결선해야 하며, 구성요소가 없는 앱도 허용해야 한다. |
| FR-05 | Registry는 `get_app_configs()`, `get_app_config(label)`, `is_installed(name)`, `get_models()`, `get_model(app_label, model_name)` 조회 API를 제공해야 한다. |
| FR-06 | SQLAlchemy model import와 Alembic `target_metadata` 구성은 동일한 설치 앱 목록과 Registry 구현을 사용해야 한다. |
| FR-07 | FastAPI 애플리케이션은 `create_app()` factory에서 Registry population, 공통 middleware, 예외 처리, Router 및 조건부 Admin을 순서대로 조립해야 한다. |
| FR-08 | 각 앱은 `AppConfig.ready()`를 통해 models 준비 후 실행할 초기화 hook을 선언할 수 있어야 한다. |
| FR-09 | 신규 앱 생성기는 `apps.py`, `<PascalName>Config`, Router entrypoint 및 선택된 계층 골격을 생성해야 한다. |
| FR-10 | 신규 앱 생성기는 설정 파일을 자동 수정하지 않고, 사용자가 `INSTALLED_APPS`에 붙여 넣을 explicit config class 경로를 출력해야 한다. |

### 5.3 Django 대응·호환 요구사항 (`CR-*`)

| ID | 요구사항 |
|---|---|
| CR-01 | package 경로가 등록되면 `<package>.apps`를 검사해 Django와 같은 기본 `AppConfig` 선택 규칙을 적용해야 한다. config가 없으면 기본 `AppConfig`를 만들고, 하나면 선택하며, 여러 개면 유일한 `default=True` config만 선택한다. |
| CR-02 | explicit config class 경로가 등록되면 해당 class가 `AppConfig` subclass인지 확인하고 그 `name`의 root package를 import해야 한다. |
| CR-03 | 모든 앱은 `INSTALLED_APPS` 순서대로 1단계 config/root package, 2단계 models, 3단계 `ready()` 순서로 population되어야 한다. |
| CR-04 | `AppConfig.name`과 `AppConfig.label`은 각각 프로젝트 안에서 유일해야 하며 label은 유효한 Python identifier여야 한다. |
| CR-05 | `apps_ready`, `models_ready`, `ready`는 각 population 단계가 전체 앱에 대해 끝난 뒤에만 `True`가 되어야 한다. |
| CR-06 | 준비되지 않은 Registry 조회는 준비 상태 계약에 따라 명시적인 예외를 발생시켜야 하며, `get_app_config()`와 `get_model()`은 조회 실패를 조용히 `None`으로 바꾸지 않아야 한다. |
| CR-07 | `ready()`는 models가 준비된 후 목록 순서대로 호출되어야 하며 정상적인 동일 Registry 재호출에서는 앱별 한 번만 실행되어야 한다. |
| CR-08 | FastAPI Router와 SQLAdmin 결선은 Django 호환 core lifecycle 이후 실행되는 adapter 동작으로 취급하며 Django 자체 기능이라고 표현하지 않아야 한다. |

### 5.4 비기능 요구사항 (`NFR-*`)

| ID | 요구사항 |
|---|---|
| NFR-01 | 동일한 설정과 코드에 대해 앱, model, hook, Router 및 Admin 등록 순서는 매 실행마다 결정적이어야 한다. 파일 시스템 열거 순서에 의존해서는 안 된다. |
| NFR-02 | `populate()`는 thread-safe하고 idempotent해야 하며, population 중 reentrant 호출은 즉시 명시적 오류로 거부해야 한다. |
| NFR-03 | package 또는 선택 모듈 자체의 부재와 그 모듈 내부 dependency import 실패를 구분해야 하며 내부 오류의 type, cause 및 traceback을 보존해야 한다. |
| NFR-04 | population 실패 후 partially-ready 상태나 부분 cache가 전역 Registry에 남아 후속 실행이 성공한 것처럼 보여서는 안 된다. |
| NFR-05 | 전역 기본 Registry를 제공하되 테스트와 app factory는 독립 `Apps` 인스턴스를 주입하여 상태를 격리할 수 있어야 한다. |
| NFR-06 | Registry core는 FastAPI와 SQLAdmin에 의존하지 않아야 하며 framework adapter와 lifecycle core를 분리해야 한다. |
| NFR-07 | 오류 메시지는 잘못된 entry, app name 또는 label, 시도한 dotted path와 사용자가 수정할 설정 위치를 포함해야 한다. |
| NFR-08 | 신규 Registry와 adapter 코드의 branch coverage는 90% 이상, 프로젝트 전체 coverage는 85% 이상이어야 한다. |

### 5.5 기존 기능 보존 요구사항 (`BC-*`)

| ID | 요구사항 |
|---|---|
| BC-01 | 기준 저장소 `a980b71`의 공개 route inventory는 수동 앱 등록으로 의도적으로 비활성화한 fixture를 제외하고 그대로 유지되어야 한다. |
| BC-02 | `auth` 기능과 OAuth2/JWT 동작은 설치 앱으로 전환된 뒤에도 기존 API 계약과 테스트를 유지해야 한다. |
| BC-03 | CORS, user-info/access-log middleware, 공통 예외 응답, health 및 Scalar docs 동작을 보존해야 한다. |
| BC-04 | SQLAlchemy async session, primary/replica routing, transaction boundary 및 Celery bridge 동작을 보존해야 한다. |
| BC-05 | 기존 Alembic revision chain과 단일 head를 유지하며 기존 schema를 의도 없이 삭제하거나 재생성해서는 안 된다. |
| BC-06 | 기준 저장소의 Ruff, format, MyPy, Bandit, Pytest 및 CI 검사를 약화하거나 우회해서는 안 된다. |
| BC-07 | `fastapi-default-project-structure` 저장소는 읽기 전용 기준으로 사용하고 그 working tree나 Git 이력을 수정해서는 안 된다. |

### 5.6 보안 요구사항 (`SEC-*`)

| ID | 요구사항 |
|---|---|
| SEC-01 | SQLAdmin과 앱별 `admin.py`는 `ADMIN=True`이고 허용된 환경일 때만 import·생성·등록되어야 한다. `ADMIN=False`에서는 `sqladmin` 및 앱 Admin module이 Registry 결선 때문에 eager-load되어서는 안 된다. |
| SEC-02 | Registry는 allowlist인 `INSTALLED_APPS`만 import해야 하며 `app/features/*` directory scan으로 임의 package를 실행해서는 안 된다. |
| SEC-03 | 앱 생성기는 정규화한 대상 경로가 `app/features`의 resolve된 경계 안에 있는지 검사하고 `..`, 절대 경로, separator, symlink를 이용한 경로 이탈을 거부해야 한다. |
| SEC-04 | 앱 생성기는 기존 파일이나 디렉터리를 부분 overwrite하지 않아야 하며 실패 시 생성 중인 임시 결과를 정리해야 한다. |
| SEC-05 | `ready()`에서는 DB query, network call, subprocess 실행 및 secret 출력을 금지하고 process-local wiring만 허용해야 한다. |
| SEC-06 | 기준선 복사는 Git tracked 파일만 대상으로 하며 `.env`, credential, `.git`, `.venv`, cache, logs, media, coverage 및 local DB를 포함해서는 안 된다. |
| SEC-07 | app/config/router/admin module 내부의 import 실패를 선택 기능 부재로 위장해 startup을 계속해서는 안 된다. |

### 5.7 인수 조건 (`AC-*`)

| ID | 검증 가능한 인수 조건 | 검증 수단 |
|---|---|---|
| AC-01 | package entry와 explicit config class entry가 같은 `AppConfig`로 정규화되고, config 0개·1개·복수/default 조합 테스트가 모두 통과한다. | `tests/core/apps/test_config.py` |
| AC-02 | fixture의 event log가 모든 앱에 대해 `config → models → ready` 순서를 보이며 `INSTALLED_APPS` 순서와 일치한다. | `tests/core/apps/test_population_order.py` |
| AC-03 | 중복 name, 중복 label, 잘못된 label, 없는 package, 잘못된 config class가 각각 기대한 오류 type과 dotted path를 출력한다. | `tests/core/apps/test_registry_errors.py` |
| AC-04 | `populate()` 동시 호출 시 `ready()`가 한 번만 실행되고, 두 번째 정상 호출은 no-op이며, `ready()` 내부 재진입은 실패한다. | `tests/core/apps/test_registry_lifecycle.py` |
| AC-05 | optional Router·Models·Admin 부재는 허용되지만 각 module 내부의 `ModuleNotFoundError`는 원래 누락 dependency 이름과 함께 전파된다. | `tests/core/apps/test_optional_modules.py` |
| AC-06 | 미등록 fixture 앱은 route, `Base.metadata`, Admin view 및 `ready()` event 어디에도 나타나지 않는다. | `tests/core/apps/test_manual_registration.py` |
| AC-07 | `ADMIN=False` app 생성 시 `sqladmin`과 `app.features.*.admin`이 `sys.modules`에 새로 로드되지 않고 `/admin` route도 없다. | `tests/core/test_admin_lazy_loading.py` |
| AC-08 | `ADMIN=True`인 허용 환경에서는 설치 앱의 Admin view만 선언 순서대로 한 번씩 등록된다. | `tests/core/test_admin_wiring.py` |
| AC-09 | runtime과 Alembic이 수집한 등록 model 집합이 일치하고 `uv run alembic heads` 결과가 1개이며 `uv run alembic check`가 성공한다. | migration/schema parity test와 CLI |
| AC-10 | generator가 `apps.py`와 올바른 config class를 생성하고, 미등록 상태에서는 비활성이며 등록 후 활성화된다. | `tests/scripts/test_new_app.py` end-to-end test |
| AC-11 | generator 입력 `../escape`, 절대 경로, separator 포함 이름, symlink escape 및 기존 대상은 실패하고 `app/features` 밖에 파일을 만들거나 기존 파일을 바꾸지 않는다. | generator security tests와 임시 directory snapshot |
| AC-12 | 기준 저장소의 고정 route inventory, auth, middleware, transaction 및 Celery 회귀 테스트가 모두 통과한다. | 전체 Pytest suite |
| AC-13 | `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run bandit -ll -q -r app main.py config.py`가 모두 exit code 0이다. | CI와 로컬 품질 gate |
| AC-14 | `uv run python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85 -q -rsxX`가 성공하고 summary에 skipped, xfailed, xpassed, deselected가 없다. | CI와 로컬 test gate |
| AC-15 | 기준선 복사 전후 manifest 검사에서 허용된 docs 외 구현 기준선이 `a980b71` tracked tree와 일치하고 금지 산출물이 대상 Git index에 없다. | `git ls-files`, hash manifest 및 금지 path 검사 |
| AC-16 | 작업 브랜치와 main push 후 원격 HEAD가 예상 commit과 일치하고 GitHub Actions가 성공한다. | `git rev-parse`, remote ref 및 CI 결과 |

### 5.8 요구사항 추적성

| 요구사항 | 구현 단계 | 인수 조건 |
|---|---|---|
| FR-01 | Phase 3, 5 | AC-06 |
| FR-02 | Phase 2 | AC-01 |
| FR-03 | Phase 2 | AC-01, AC-03 |
| FR-04 | Phase 4, 5 | AC-05, AC-06, AC-08 |
| FR-05 | Phase 2, 4 | AC-01, AC-03, AC-06 |
| FR-06 | Phase 4 | AC-06, AC-09 |
| FR-07 | Phase 5 | AC-07, AC-08, AC-12 |
| FR-08 | Phase 3 | AC-02, AC-04 |
| FR-09 | Phase 6 | AC-10, AC-11 |
| FR-10 | Phase 6 | AC-10 |
| CR-01 | Phase 2 | AC-01 |
| CR-02 | Phase 2 | AC-01, AC-03 |
| CR-03 | Phase 2, 3 | AC-02 |
| CR-04 | Phase 2 | AC-03 |
| CR-05 | Phase 2 | AC-02, AC-04 |
| CR-06 | Phase 2, 4 | AC-03, AC-06 |
| CR-07 | Phase 2, 3 | AC-02, AC-04 |
| CR-08 | Phase 5, 8 | AC-07, AC-08 및 문서 검토 |
| NFR-01 | Phase 2, 5 | AC-02, AC-08 |
| NFR-02 | Phase 2 | AC-04 |
| NFR-03 | Phase 2 | AC-03, AC-05 |
| NFR-04 | Phase 2 | AC-04 |
| NFR-05 | Phase 2, 5 | AC-04, AC-06 |
| NFR-06 | Phase 2, 5 | AC-07, AC-08 및 dependency 검사 |
| NFR-07 | Phase 2 | AC-03, AC-05 |
| NFR-08 | Phase 7 | AC-14 |
| BC-01 | Phase 1, 5, 7 | AC-12 |
| BC-02 | Phase 3, 5, 7 | AC-12 |
| BC-03 | Phase 5, 7 | AC-12 |
| BC-04 | Phase 4, 5, 7 | AC-12 |
| BC-05 | Phase 4, 7 | AC-09 |
| BC-06 | Phase 1, 7 | AC-13, AC-14 |
| BC-07 | Phase 0, 1 | AC-15 |
| SEC-01 | Phase 5 | AC-07, AC-08 |
| SEC-02 | Phase 2, 5 | AC-06 |
| SEC-03 | Phase 6 | AC-11 |
| SEC-04 | Phase 6 | AC-11 |
| SEC-05 | Phase 3, 7 | AC-02, AC-04 및 hook source review |
| SEC-06 | Phase 0, 1 | AC-15 |
| SEC-07 | Phase 2, 7 | AC-03, AC-05 |
| 통합·배포 승인 | Phase 7, 8 및 main 통합 | AC-12, AC-13, AC-14, AC-15, AC-16 |

## 6. 설계

### 6.1 등록 형식

기본 설정은 Django처럼 dotted path를 사용한다.

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

`"app.features.blog"`도 허용한다. 이 경우 registry가 `app.features.blog.apps`를 확인해 기본 `AppConfig` subclass를 선택한다. 짧은 이름 `"blog"`는 모호한 프로젝트 전용 축약이므로 최종 공개 계약에서 제거한다.

### 6.2 `AppConfig`

신규 `app/core/apps/config.py`에 framework-neutral `AppConfig`를 둔다.

```python
class AppConfig:
    name: str
    label: str
    verbose_name: str
    path: Path
    default: bool | None
    router_module: str = "api.routers.router"
    router_attribute: str | None = None
    models_module: str = "models"
    admin_module: str = "admin"

    def import_models(self) -> None: ...
    def ready(self) -> None: ...
    def get_models(self) -> Iterable[type]: ...
    def get_model(self, model_name: str) -> type: ...
```

설계 규칙은 다음과 같다.

- `name`은 전체 Python package 경로다.
- `label` 기본값은 `name`의 마지막 component이며 유효한 Python identifier여야 한다.
- `verbose_name` 기본값은 label의 title 표현이다.
- `router_attribute` 기본값은 `<label>_router`다.
- Model 조회는 Django ORM registry를 흉내 내기 위해 새로운 ORM을 만들지 않고, SQLAlchemy `Base.metadata` 및 declarative mapper에서 해당 앱 module에 속한 class를 수집한다.
- `ready()`에서는 DB query를 금지하고 wiring·signal 성격의 초기화만 허용한다고 문서화한다.

### 6.3 `Apps` registry

신규 `app/core/apps/registry.py`가 다음 상태를 가진다.

```text
app_configs: dict[label, AppConfig]
apps_ready: bool
models_ready: bool
ready: bool
loading: bool
_lock: threading.RLock
```

`populate(installed_apps)`의 동작은 다음과 같다.

```text
Phase 1
  각 entry를 AppConfig.create(entry)로 정규화
  root package import
  name·label 중복 검사
  registry에 목록 순서대로 저장
  apps_ready = True

Phase 2
  각 config.import_models()
  app별 SQLAlchemy model cache 구성
  models_ready = True

Phase 3
  각 config.ready()
  ready = True
```

동일 registry에 대한 두 번째 `populate()`는 즉시 반환하고, population 도중 재호출은 `RuntimeError`를 발생시킨다. 실패 시 partially-ready registry를 전역에서 재사용하지 않도록 상태와 캐시를 정리한 뒤 원래 예외를 전파한다.

공개 API는 최소 다음을 제공한다.

- `get_app_configs()`
- `get_app_config(label)`
- `is_installed(app_name)`
- `get_models()`
- `get_model(app_label, model_name, require_ready=True)`

전역 기본 registry는 `app/core/apps/__init__.py`의 `apps`로 제공한다. 테스트와 app factory는 격리된 `Apps()` 인스턴스를 주입할 수 있어야 한다.

### 6.4 FastAPI adapter

Django lifecycle 자체와 FastAPI 결선을 분리한다.

```text
Apps.populate()
  ├─ 순수 registry lifecycle
  └─ app config와 models 준비

install_routers(fastapi_app, apps)
install_admin(admin, apps)
  └─ FastAPI/SQLAdmin adapter
```

Router와 Admin은 각 앱의 `AppConfig`가 선언한 module·attribute를 사용한다. module이 없는 앱은 해당 기능을 제공하지 않는 것으로 처리한다. module은 존재하지만 내부 dependency import가 실패하거나 예상 공개 이름이 잘못되면 startup을 실패시킨다.

라우터 prefix는 기본 `/api`이며 앱 config에서 변경할 수 있다. 등록 순서가 route 우선순위에 영향을 줄 수 있으므로 `INSTALLED_APPS` 순서를 그대로 보존한다.

### 6.5 애플리케이션 factory

기준 저장소의 `main.py` 조립 코드를 `app/core/bootstrap.py`의 `create_app()`으로 옮기되 동작을 잃지 않는다.

```python
def create_app(
    installed_apps: Sequence[str] | None = None,
    registry: Apps | None = None,
) -> FastAPI:
    ...
```

조립 순서는 다음과 같다.

1. 설정과 앱 목록 결정
2. registry population 완료
3. FastAPI 생성 및 기존 lifespan 연결
4. CORS, user info 및 exception handler 등록
5. registry 기반 Router 설치
6. health 및 Scalar docs 등록
7. 허용된 경우 registry 기반 SQLAdmin 설치

`main.py`는 `app = create_app()`과 로컬 uvicorn 실행만 남기는 얇은 진입점으로 만든다.

### 6.6 앱별 `apps.py`

모든 기본 앱은 `apps.py`를 가진다.

```python
from app.core.apps import AppConfig


class BlogConfig(AppConfig):
    name = "app.features.blog"
```

`HomeConfig.ready()`는 현재 home package import-time에 실행되는 access-log sink 등록을 담당한다. 다른 앱은 기본 hook을 사용한다. root `__init__.py`는 Router와 Models를 import하지 않는 가벼운 package marker로 정리해 3단계 초기화 순서를 보장한다.

### 6.7 Alembic

`migrations/env.py`는 더 이상 파일 시스템 자동 model scan을 호출하지 않는다.

```text
Apps().populate(INSTALLED_APPS)
  → 등록 앱 models만 Base.metadata에 포함
  → target_metadata = Base.metadata
```

운영 migration이 `ready()`의 runtime side effect를 요구하지 않도록 `populate_models()`와 전체 `populate()`의 사용 경계를 설계한다. 최종 선택은 다음 기준을 따른다.

- Django lifecycle 동일성을 우선하면 전체 population을 사용한다.
- `ready()`가 외부 연결을 만들 수 있어 migration 격리가 필요하면 `populate_models()`를 공개하지 않고 registry 내부의 `run_ready=False` 옵션을 Alembic adapter에서만 사용한다.
- 어느 경우든 app config와 models 단계는 runtime과 같은 구현을 공유해야 한다.

### 6.8 앱 생성기

`scripts/new_app.py`는 다음을 생성한다.

- `app/features/<name>/apps.py`
- 가벼운 `__init__.py`
- Router entrypoint와 기존 계층 골격
- 선택적인 models, admin skeleton
- 테스트 skeleton

생성기는 `config.py`를 자동 수정하지 않는다. 종료 메시지는 다음 class path를 정확히 출력한다.

```python
"app.features.orders.apps.OrdersConfig",
```

생성 직후 앱은 미설치 상태이며, 목록 추가 후에만 Router·Models·Admin·`ready()`가 활성화되어야 한다.

## 7. 브랜치 및 기준선 전략

### 7.1 사전 조건

현재 대상 저장소 working tree에는 아직 커밋되지 않은 문서 변경이 있다.

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/django-style-app-registry/PASSIVE-APP-PROJECT-DESIGN.md`
- `docs/django-style-app-registry/PRODUCTION-READINESS-DEVELOPMENT-PLAN.md`
- 이 계획서

구현 전에 이 문서들을 별도 docs commit으로 먼저 보존해야 한다. dirty tree에서 기준 저장소 복사를 시작하지 않는다.

또한 두 저장소가 각각 다음 상태인지 확인한다.

```text
fastapi-default-project-structure: main == origin/main == a980b71, clean
fastapi-project-structure-django-passive-style: main == origin/main == 85153fb + docs commit, clean
```

원격이 변경되었다면 fetch 후 새 commit hash로 이 계획서의 기준점을 갱신하고 차이를 다시 검토한다.

### 7.2 작업 브랜치

대상 저장소 `main`에서 다음 브랜치를 만든다.

```text
feature/rebase-default-django-app-registry
```

브랜치 생성 직후 대상 main의 tag 또는 backup branch를 남긴다.

```text
backup/pre-default-rebase-20260812
```

backup ref는 복구용이며 구현 commit에 포함하지 않는다.

### 7.3 기준 저장소 복사

기준 저장소의 **tracked 파일만** 대상 작업 브랜치로 복사한다. 다음은 복사하지 않는다.

- `.git/`
- `.venv/`
- cache와 test temp
- `logs/`, `media/`, local DB 및 coverage 산출물
- 기준 저장소의 local untracked 파일

복사 후 대상에만 남아 기준 tree에 없는 tracked 파일은 allowlist를 제외하고 제거한다. 초기 allowlist는 새 계획 문서와 프로젝트 목적을 설명하는 docs뿐이다. 이 단계의 결과는 “기준 저장소 `a980b71`의 tracked tree + 승인된 docs”와 같아야 한다.

복사 결과는 독립 commit으로 남긴다.

```text
chore: reset implementation baseline to fastapi-default-project-structure a980b71
```

### 7.4 대상 main 참조 방법

이후 구현은 대상 main에서 다음 파일의 아이디어와 테스트 사례만 선별해 옮긴다.

- `app/core/registry.py`
- `app/core/bootstrap.py`
- `config.py`의 `INSTALLED_APPS`
- `migrations/env.py`
- `scripts/new_app.py`
- `tests/core/test_registry_*`
- `tests/core/test_bootstrap.py`
- `tests/core/test_endpoint_inventory.py`
- `tests/scripts/test_new_app.py`

다음 공통 영역은 대상 main 버전으로 덮어쓰지 않고 기준 저장소 버전을 유지한다.

- 기능 앱의 API·Service·Repository·Schema·Model 구현
- `auth` 기능
- DB session/router
- middleware와 logging
- migration chain
- `pyproject.toml`, `uv.lock`, CI의 최신 default 계약

대상 main의 보안·운영 개선 중 기준 저장소에 아직 없는 항목이 발견되더라도, 앱 수동화 기능과 직접 연관되지 않으면 이번 브랜치에 포함하지 않고 별도 backlog로 기록한다.

## 8. 단계별 개발 작업 계획

### Phase 0. 문서 보존과 재현 가능한 기준선 확정

#### 작업

1. 현재 문서 변경을 검토하고 docs-only commit으로 저장한다.
2. 두 저장소의 branch, HEAD, remote tracking, dirty 상태를 기록한다.
3. 기준 저장소 tracked manifest와 SHA-256 manifest를 생성해 작업 기록에 남긴다.
4. 대상 main backup ref를 만든다.
5. 작업 브랜치를 생성한다.

#### 완료 조건

- 두 저장소의 기준 commit이 문서에 기록된 값과 일치한다.
- 대상 작업 브랜치 시작 전에 working tree가 깨끗하다.
- 기준 저장소의 local cache나 secret이 복사 대상에 포함되지 않는다.

### Phase 1. default tracked tree로 구현 기준선 교체

#### 작업

1. 기준 저장소의 tracked tree를 임시 staging directory로 export한다.
2. 대상 작업 브랜치의 구현 파일을 export 결과와 동기화한다.
3. `.git`, 승인된 docs, 저장소 고유 LICENSE/remote metadata는 보존 규칙에 따라 처리한다.
4. 기준 저장소와 대상 tree의 tracked manifest를 비교한다.
5. dependency lock을 임의 재생성하지 않고 기준 `uv.lock`을 그대로 사용한다.
6. 기준 저장소의 전체 품질 게이트를 실행한다.

#### 검증

```powershell
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run bandit -ll -q -r app main.py config.py
uv run python -m pytest -q -rsxX
uv run alembic heads
```

#### 완료 조건

- 승인된 docs를 제외한 구현 tree가 기준 저장소 tracked tree와 일치한다.
- 기준 저장소의 route inventory와 전체 테스트가 그대로 통과한다.
- 이 시점에는 passive registry 변경이 아직 없어 diff 원인이 명확하다.

### Phase 2. `AppConfig`와 Registry core 구현

#### 대상 파일

- `app/core/apps/__init__.py`
- `app/core/apps/config.py`
- `app/core/apps/registry.py`
- `app/core/apps/exceptions.py`
- `tests/core/apps/` fixture packages와 단위 테스트

#### 작업

1. Django 의미에 맞춘 `AppConfig.create(entry)`를 구현한다.
2. package 경로와 config class 경로를 구분한다.
3. `apps.py`의 0개·1개·복수 default config 선택 규칙을 구현한다.
4. name, label, path, module 검증과 중복 오류를 구현한다.
5. registry 상태 flag와 준비 상태 검사 메서드를 구현한다.
6. thread-safe, idempotent, non-reentrant `populate()`를 구현한다.
7. optional module 부재와 내부 import 실패를 구분한다.
8. 조회 API와 명확한 예외 메시지를 구현한다.

#### 테스트 우선 사례

- package entry가 단일 config를 선택한다.
- explicit config class entry가 선택된다.
- config가 없으면 기본 config가 생성된다.
- 여러 config 중 `default=True` 하나만 선택된다.
- 선택할 수 없는 복수 config는 실패한다.
- 중복 label과 중복 name은 각각 실패한다.
- 목록 순서가 보존된다.
- 없는 package와 내부 import 오류는 다른 예외가 된다.
- population 두 번째 호출은 `ready()`를 다시 호출하지 않는다.
- population 중 재진입은 실패한다.
- 동시 population은 한 번만 완료된다.

#### 완료 조건

- FR-02, FR-03, FR-05, CR-01부터 CR-07, NFR-01부터 NFR-07 및 SEC-02·SEC-07을 AC-01부터 AC-05로 검증한다.
- Registry core가 FastAPI와 SQLAdmin을 import하지 않는다.

### Phase 3. 기본 앱 `apps.py`와 lifecycle 전환

#### 대상 파일

- `app/features/*/apps.py`
- `app/features/*/__init__.py`
- `config.py`
- home sink 관련 파일과 테스트

#### 작업

1. home, blog, reply, sns, user, auth에 `AppConfig` subclass를 추가한다.
2. `INSTALLED_APPS`를 explicit dotted config path 목록으로 정의한다.
3. 각 feature `__init__.py`에서 Router·Model eager import를 제거한다.
4. home access-log sink 등록을 `HomeConfig.ready()`로 이동한다.
5. `ready()` 구현의 idempotency를 보장한다.
6. `ready()` hook에는 DB query, network, subprocess 또는 secret logging이 없음을 검토하고 테스트 가능한 금지 동작은 fixture로 차단한다.
7. 등록하지 않은 fixture 앱은 import·hook·model 부수효과가 없음을 검증한다.

#### 완료 조건

- FR-01·FR-08, CR-03·CR-05·CR-07 및 SEC-05를 AC-02·AC-04·AC-06으로 검증한다.
- `INSTALLED_APPS` 순서를 바꾸면 registry와 hook 순서가 함께 바뀐다.
- root package import 단계에서 models가 로드되지 않는다.

### Phase 4. SQLAlchemy model registry와 Alembic 통합

#### 대상 파일

- `app/core/apps/config.py`
- `app/core/apps/registry.py`
- `app/core/db/models_registry.py` 제거 또는 compatibility facade
- `migrations/env.py`
- model/migration 구조 테스트

#### 작업

1. 등록 앱별 models module import와 model class cache를 구현한다.
2. SQLAlchemy declarative model을 app label에 연결한다.
3. `get_models()`와 case-insensitive `get_model()`을 구현한다.
4. 기존 filesystem model scan을 registry 기반 수집으로 교체한다.
5. Alembic이 같은 `INSTALLED_APPS`를 사용하도록 변경한다.
6. 미등록 앱 model이 `Base.metadata`에 들어오지 않는 격리 테스트를 추가한다.
7. 기존 migration head 적용 후 metadata와 실제 schema parity를 확인한다.

#### 완료 조건

- FR-06과 BC-05를 AC-06·AC-09로 검증한다.
- runtime과 migration이 서로 다른 model import 경로를 갖지 않는다.
- 기준 저장소 migration chain은 손실되지 않는다.

### Phase 5. FastAPI Router·SQLAdmin adapter와 app factory 통합

#### 대상 파일

- `app/core/apps/wiring.py`
- `app/core/bootstrap.py`
- `main.py`
- `app/features/admin.py` 제거 또는 compatibility facade
- bootstrap, Router, Admin 구조 테스트

#### 작업

1. registry 결과만 읽는 `install_routers()`를 구현한다.
2. registry 결과만 읽는 `install_admin()`을 구현한다.
3. 기준 `main.py`의 모든 공통 조립 동작을 `create_app()`으로 옮긴다.
4. 모든 기존 middleware·exception handler를 보존한다.
5. `main.py`를 얇은 entrypoint로 바꾼다.
6. `create_app()`이 격리 registry와 app 목록을 주입받도록 한다.
7. route collision, 잘못된 router attribute, 내부 import failure를 fail-fast 처리한다.
8. `ADMIN=False` 경로에서 `sqladmin`과 앱별 `admin.py`를 import하지 않도록 Admin 결선 전체를 지연 import한다.

#### 완료 조건

- FR-04·FR-07, CR-08, BC-01부터 BC-04 및 SEC-01을 AC-06부터 AC-08·AC-12로 검증한다.
- 기준 저장소의 모든 공개 endpoint가 유지된다.
- `auth`가 `INSTALLED_APPS`에 등록되어 동작한다.
- 미등록 앱 Router와 Admin view는 노출되지 않는다.
- 같은 process에서 격리된 app factory 테스트가 서로 registry 상태를 오염시키지 않는다.

### Phase 6. `startapp`형 생성기 구현

#### 대상 파일

- `scripts/new_app.py`
- `tests/scripts/test_new_app.py`
- 생성 template fixture

#### 작업

1. 대상 main의 generator를 기준 저장소 구조에 맞게 재설계한다.
2. `apps.py`와 `<PascalName>Config`를 생성한다.
3. snake_case 이름과 Python identifier를 검증한다.
4. 입력에서 `..`, 절대 경로 및 `/`·`\` separator를 거부하고, 최종 대상의 resolve 결과가 resolve된 `app/features` 하위인지 확인한다.
5. symlink를 통과한 resolve 결과가 경계를 벗어나면 생성 전에 거부한다.
6. 기존 경로가 있으면 부분 overwrite 없이 실패시키고, 임시 staging 경로에서 전체 생성에 성공한 뒤에만 최종 위치로 이동한다.
7. `--with-models`, `--with-admin` 등 옵션별 결과를 테스트한다.
8. `INSTALLED_APPS`에 넣을 explicit class path를 출력한다.
9. 생성 전·등록 후의 활성화 차이를 end-to-end로 검증한다.

#### 완료 조건

- FR-09·FR-10과 SEC-03·SEC-04를 AC-10·AC-11로 검증한다.
- 생성기가 config를 몰래 변경하지 않는다.
- 생성 결과에 “자동 발견” 또는 “중앙 등록 불필요”라는 설명이 없다.

### Phase 7. 회귀·호환·실패 계약 검증

#### 테스트 묶음

1. Registry unit tests
2. 실제 앱 lifecycle tests
3. Router/Admin integration tests
4. SQLAlchemy metadata/Alembic tests
5. generator end-to-end tests
6. 기준 저장소 전체 regression suite
7. production configuration/security tests

#### 필수 불변 조건

- 기준 route inventory에서 의도하지 않은 삭제가 없다.
- `INSTALLED_APPS`에서 auth를 제거한 격리 app에는 auth route가 없다.
- 미등록 app directory는 존재해도 로드되지 않는다.
- 등록 순서가 registry, models, `ready()`, Router에 일관되게 반영된다.
- optional Router/Models/Admin이 없는 앱은 정상이다.
- optional module 내부 오류는 startup 실패다.
- app name·label 중복은 startup 실패다.
- `ready()`는 models 준비 전에 호출되지 않는다.
- Alembic head는 하나이고 schema drift가 없다.
- pytest summary에 skip, xfail, xpass, deselected가 없다.

#### 최종 품질 게이트

```powershell
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run bandit -ll -q -r app main.py config.py
uv run python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85 -q -rsxX
uv run alembic heads
uv run alembic upgrade head
uv run alembic check
```

SQLite test DB와 Alembic 임시 DB는 새 경로에서 시작하고 기존 개발 DB를 덮어쓰지 않는다.

### Phase 8. 문서 정합성 갱신

#### 대상 문서

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/django-style-app-registry/PASSIVE-APP-PROJECT-DESIGN.md`
- 신규 `docs/django-style-app-registry/DJANGO-APP-COMPATIBILITY.md`
- 필요 시 `docs/DEPLOYMENT.md`

#### 작업

1. 짧은 이름 등록 예제를 dotted config path로 교체한다.
2. Django와 동일하게 구현한 범위와 구현하지 않은 범위를 표로 명시한다.
3. 3단계 population, 준비 상태, `ready()` 제약을 설명한다.
4. 신규 앱 생성·등록·migration·검증 순서를 제공한다.
5. 앱 비활성화와 제거가 schema 삭제를 자동 수행하지 않음을 경고한다.
6. 기준 저장소 commit과 대상 참조 commit을 provenance로 남긴다.

#### 완료 조건

- 문서 예제의 import path와 실제 코드가 일치한다.
- 기존 “Django식” 표현이 단순 영감인지 lifecycle 호환인지 구분된다.
- 문서 내부 link와 코드 snippet 검사가 통과한다.

## 9. 커밋 계획

권장 commit은 다음과 같이 각 단계가 독립 검토·revert 가능하도록 나눈다.

1. `docs: define django-compatible manual app integration plan`
2. `chore: reset implementation baseline to fastapi-default-project-structure a980b71`
3. `test(apps): define django-compatible registry contracts`
4. `feat(apps): add AppConfig and three-phase registry population`
5. `refactor(features): declare installed apps with AppConfig classes`
6. `refactor(db): drive model metadata and alembic from app registry`
7. `refactor(bootstrap): wire routers and admin from installed apps`
8. `feat(scripts): add AppConfig-aware startapp scaffold`
9. `test: add passive app lifecycle and default regression gates`
10. `docs: document django app compatibility and registration workflow`

각 commit 전에 해당 범위의 테스트를 실행하고, 마지막 commit 전에 전체 품질 게이트를 실행한다. 구현 commit과 단순 formatting 대량 변경을 섞지 않는다.

## 10. main 통합 및 push 계획

### 10.1 작업 브랜치 push

전체 검증이 통과하면 작업 브랜치를 먼저 원격에 push한다.

```text
origin/feature/rebase-default-django-app-registry
```

push 전 확인 사항은 다음과 같다.

- `git status` clean
- 예상 commit만 존재
- 기준선 교체 commit에서 secret·cache·local artifact가 없음
- CI 전체 통과
- FR/CR/NFR/BC/SEC 전체 요구사항과 AC-01부터 AC-16까지 검증 증거 연결 완료

### 10.2 main 최신화와 통합

1. `origin/main`을 fetch한다.
2. 작업 시작 후 main이 바뀌었으면 작업 브랜치를 최신 main에 rebase하고 전체 검증을 다시 실행한다.
3. 변경이 없으면 대상 main에서 `--ff-only` merge를 사용한다.
4. fast-forward가 불가능하면 강제 push하지 않고 충돌 원인을 검토한다.
5. main merge 직후 전체 품질 게이트를 다시 실행한다.
6. `main`을 `origin/main`에 일반 push한다.

### 10.3 push 후 검증

- 원격 main HEAD가 로컬 merge commit과 일치한다.
- GitHub Actions가 성공한다.
- 원격 tree에 `.venv`, cache, logs, media, `.env`, coverage DB가 없다.
- README의 신규 앱 절차가 실제 generator 출력과 일치한다.
- release/tag는 별도 요청이 없으면 만들지 않는다.

### 10.4 복구 전략

- 작업 브랜치 통합 전: 브랜치를 폐기하고 docs commit이 포함된 main으로 복귀한다.
- main 통합 후 아직 push 전: merge 방식에 맞춰 안전하게 되돌리되 destructive reset은 사용하지 않는다.
- push 후: backup ref와 commit 경계를 사용해 `git revert`로 기준선 교체 및 기능 commit을 역순으로 되돌린다.
- migration이 배포된 이후에는 코드 revert만 하지 않고 forward migration 전략을 별도로 수립한다.

## 11. 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 기준 저장소 전체 복사로 대상 문서·설정 소실 | 프로젝트 목적과 기록 유실 | docs 선행 commit, tracked export, allowlist, manifest 비교 |
| 대상 main 공통 코드를 통째로 이식 | 최신 auth/API 회귀 | 앱 수동화 관련 파일·행동만 선별 이식, default 회귀 suite 고정 |
| `__init__.py` eager import 잔존 | 3단계 lifecycle 위반 | root package import 후 model module 미로딩 테스트 |
| 전역 registry 상태가 테스트를 오염 | 비결정적 테스트와 이중 `ready()` | injectable registry, idempotency, isolated factory fixture |
| `ready()`에서 DB·외부 I/O 수행 | CLI/migration 기동 부작용 | hook 정책 문서화, home sink만 wiring, I/O 금지 테스트/리뷰 |
| SQLAlchemy model을 잘못된 app에 귀속 | `get_model` 오동작 | class `__module__`과 config name 경계 검사, explicit override 지원 검토 |
| route order 변경 | 동일 path 처리 결과 변경 | `INSTALLED_APPS` 순서 보존 및 collision test |
| 앱 비활성화 시 migration metadata 축소 | Alembic이 table drop을 제안 | 등록 해제 절차와 migration 정책 문서화, `alembic check` 검토 gate |
| Django와 “완전 동일”하다는 오해 | 지원 범위 오판 | compatibility matrix로 동일·확장·비지원 항목 구분 |
| 원격 main 동시 변경 | merge 충돌 또는 누락 | push 직전 fetch/rebase, 전체 gate 재실행, force push 금지 |

## 12. 완료 정의

다음 조건을 모두 만족할 때 개발 작업이 완료된 것으로 판정한다.

1. 구현 tree가 `fastapi-default-project-structure`의 확장임을 manifest와 Git 이력으로 설명할 수 있다.
2. 기준 저장소의 기능과 공개 endpoint가 의도 없이 손실되지 않았다.
3. 모든 앱 활성화가 `INSTALLED_APPS` 하나로 통제된다.
4. package/config class 해석, `AppConfig`, 3단계 population, `ready()`와 registry 조회가 명세대로 동작한다.
5. Router·Models·Admin·Alembic이 동일 registry를 사용한다.
6. 미등록 앱은 어떤 결선에도 참여하지 않는다.
7. 신규 앱 생성기는 `apps.py`와 정확한 수동 등록 안내를 제공한다.
8. FR/CR/NFR/BC/SEC 전체 요구사항이 AC-01부터 AC-16 중 하나 이상에 연결되고 자동화된 검증 증거가 있다.
9. 정적 검사, 보안 검사, 전체 테스트, coverage, Alembic 검증 및 CI가 모두 통과한다.
10. 작업 브랜치가 검토 가능하게 push되고, 최신 main에 안전하게 통합된 뒤 원격 main CI가 성공한다.

## 13. 실행 순서 요약

```text
현재 docs 보존 commit
  → 두 저장소 commit/clean 상태 고정
  → 대상 main에서 작업 브랜치 생성
  → default a980b71 tracked tree 복사
  → 기준 regression green 확인
  → AppConfig/Apps registry 테스트 및 구현
  → 기본 앱 apps.py + ready() 전환
  → Models/Alembic 통합
  → Router/Admin/bootstrap 통합
  → startapp generator 구현
  → 전체 회귀·보안·migration 검증
  → 문서 정합성 갱신
  → 작업 브랜치 push 및 CI
  → 최신 main 반영 후 전체 재검증
  → main fast-forward 통합
  → origin/main push 및 원격 CI 확인
```

이 순서를 지키면 대상 main의 과거 구현을 기준 저장소 위에 무차별 덮어쓰지 않고, 검증된 수동 앱 lifecycle만 독립적으로 이식할 수 있다.
