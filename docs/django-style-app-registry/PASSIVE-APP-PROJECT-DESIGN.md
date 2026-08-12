# Django식 수동 앱 관리 FastAPI 프로젝트 설계 및 개발 내역

## 1. 문서 목적

이 문서는 `fastapi-project-structure-django-passive-style`의 존재 이유와 핵심 설계, 구현 방식, 개발 과정 및 확장 규칙을 설명한다.

이 프로젝트는 일반적인 FastAPI 애플리케이션 하나를 제공하는 것이 아니라, 여러 기능을 독립된 앱으로 나누고 Django의 `INSTALLED_APPS`처럼 필요한 앱을 명시적으로 추가·제거·정렬할 수 있게 만든 **개발용 기본 구조 템플릿**이다.

기반 구조는 Git 이력상 `fastapi-default-project-structure`에서 가져왔으며, 이후 FastAPI에 Django식 수동 앱 등록 개념을 도입하는 방향으로 확장되었다. 이 문서는 현재 저장소의 코드와 Git 이력을 기준으로 작성하며, 기반 저장소의 현재 상태를 직접 비교한 문서는 아니다.

## 2. 프로젝트의 핵심 목적

FastAPI는 라우터와 의존성을 자유롭게 구성할 수 있지만, 프로젝트가 커지면 다음 결정이 각 팀이나 기능마다 달라지기 쉽다.

- 어떤 기능이 애플리케이션에 설치되어 있는가?
- 기능 모듈은 어디에 위치하는가?
- 라우터, 모델, 관리자 화면은 어디에서 등록하는가?
- 기능별 비즈니스 로직과 데이터 접근을 어떻게 분리하는가?
- 요청 단위 트랜잭션은 누가 시작하고 완료하는가?
- 기능 앱을 추가하거나 제거할 때 중앙 부트스트랩 코드를 얼마나 수정해야 하는가?

이 프로젝트는 이에 대해 다음 답을 제공한다.

> 앱의 설치 여부와 순서는 명시적으로 관리하고, 설치된 앱 내부의 Router·Model·Admin 연결은 동일한 컨벤션으로 처리한다.

이를 통해 Django의 명시적인 앱 관리 방식과 FastAPI의 가벼운 의존성 주입·라우터 조합 방식을 함께 사용한다.

## 3. 설계 목표

### 3.1 명시적인 앱 구성

설치된 앱 목록은 [`config.py`](../../config.py)의 `INSTALLED_APPS` 한 곳에서 관리한다.

```python
INSTALLED_APPS: list[str] = [
    "home",
    "blog",
    "reply",
    "sns",
    "user",
]
```

파일 시스템을 검색해 모든 하위 디렉터리를 자동 활성화하지 않는다. 따라서 소스 디렉터리가 존재한다는 사실과 애플리케이션에 설치되었다는 사실을 분리할 수 있다.

이 방식이 제공하는 이점은 다음과 같다.

- 어떤 기능이 실행 대상인지 설정 한 곳에서 확인할 수 있다.
- 앱의 로드 순서를 목록 순서로 통제할 수 있다.
- 실험 중이거나 배포 대상이 아닌 앱 디렉터리를 비활성 상태로 둘 수 있다.
- 앱 제거가 중앙 부트스트랩 코드 수정으로 번지지 않는다.
- 환경별 앱 구성을 발전시킬 때 명확한 확장 지점을 제공한다.

### 3.2 명시성과 컨벤션의 역할 분리

이 프로젝트에서 “수동 등록”은 모든 구성요소를 일일이 등록한다는 의미가 아니다.

- 수동으로 결정하는 것: 설치할 앱의 이름과 순서
- 컨벤션으로 처리하는 것: 등록 앱의 Router, Model, Admin 결선

따라서 중앙 설정의 통제력은 유지하면서 반복적인 import 및 `include_router()` 코드를 줄인다.

### 3.3 기능 중심 구조

기능 앱은 `app/features/<name>/` 아래에 둔다. 기술 계층별 전역 폴더에 모든 Router나 Service를 모으지 않고, 하나의 기능에 필요한 코드를 같은 앱 경계 안에 배치한다.

현재 설치된 앱은 다음과 같다.

| 앱 | 역할 | 대표 테이블 |
|---|---|---|
| `home` | 접근 로그 수집·조회 및 통계 | `user_access_logs` |
| `blog` | 블로그 게시물 CRUD 예제 | `blog_posts` |
| `reply` | 댓글 CRUD 예제 | `replies` |
| `sns` | SNS 게시물 CRUD 예제 | `sns_posts` |
| `user` | 사용자 CRUD 예제 | `users` |

이 앱들은 템플릿 사용자가 구조와 구현 패턴을 확인할 수 있는 참조 구현이기도 하다.

### 3.4 예측 가능한 계층과 트랜잭션

요청 처리는 다음 경로를 따른다.

```text
HTTP Request
  → Router
  → Depends(get_<name>_service)
  → Service
  → Repository
  → Async SQLAlchemy Session
  → Database
```

각 계층의 책임은 다음과 같다.

| 계층 | 책임 | 하지 않는 일 |
|---|---|---|
| Router | HTTP 입력 검증, Service 호출, 응답 변환 | 직접 ORM 쿼리, 임의 트랜잭션 처리 |
| Dependency | 세션 주입, Service 구성, 요청 성공 후 커밋 | 비즈니스 규칙 구현 |
| Service | 유스케이스와 비즈니스 규칙 | HTTP 응답 구성, 일반적인 커밋 |
| Repository | ORM 조회와 저장 캡슐화 | HTTP 처리, 비즈니스 정책 결정 |
| DB Session | 실제 트랜잭션과 연결 수명주기 | 기능 의미 해석 |

기능 Dependency는 Service를 `yield`한 뒤 정상 완료 시 `session.commit()`을 실행한다. 예외가 발생하면 세션 Dependency의 teardown에서 rollback한다. 별도의 도메인별 UnitOfWork 계층은 두지 않는다.

이 선택은 요청 수명주기와 트랜잭션 경계를 일치시키고, FastAPI의 generator dependency를 그대로 활용하기 위한 것이다.

## 4. 전체 구조

```text
main.py
  └─ app.core.bootstrap.create_app()
       ├─ config.INSTALLED_APPS
       ├─ AppRegistry.discover()
       ├─ AppRegistry.import_models()
       ├─ FastAPI 생성
       ├─ middleware 및 exception handler 등록
       ├─ AppRegistry.install_routers()
       ├─ health/docs 구성
       └─ 조건부 AppRegistry.install_admin()

app/
  ├─ core/       공통 실행 기반과 프레임워크 인프라
  ├─ features/   독립된 기능 앱
  ├─ celery/     중앙 비동기 작업 기반
  └─ utils/      공통 유틸리티와 인증 보조 기능
```

상위 수준의 의존 방향은 다음과 같다.

```text
features → core → utils
```

`core`가 특정 기능 앱을 직접 import하지 않도록 하는 것이 원칙이다. 기능 연결은 Registry와 컨벤션을 통해 이루어진다. 이 원칙은 기능 앱을 추가·제거할 때 core 수정 범위를 줄이고 템플릿의 재사용성을 보존한다.

## 5. 수동 등록과 Registry 결선

### 5.1 앱 목록의 단일 진실 공급원

[`config.py`](../../config.py)의 `INSTALLED_APPS`가 설치 앱의 단일 진실 공급원(SSOT)이다. [`AppRegistry.discover()`](../../app/core/registry.py)는 이 목록을 순서대로 읽고 각 이름을 다음 package로 변환한다.

```text
<name> → app.features.<name>
```

예를 들어 `"blog"`는 `app.features.blog`로 연결된다.

Registry는 다음 구성 오류를 시작 단계에서 확인한다.

- 동일한 앱 이름의 중복 등록
- 등록했지만 실제 package가 없는 앱
- 앱 package 내부의 깨진 import

선택적인 Router, Models, Admin 모듈이 없는 경우와, 해당 모듈 내부 import가 실패한 경우도 구분한다. 전자는 선택 기능 부재로 처리하고 후자는 구현 오류이므로 예외를 다시 발생시킨다.

### 5.2 Router 컨벤션

등록 앱의 Router 진입점은 다음 규칙을 따른다.

```text
app/features/<name>/api/routers/router.py
  └─ <name>_router: APIRouter
```

Registry는 `<name>_router`를 읽어 `/api` prefix로 FastAPI에 설치한다. 앱 내부 Router가 버전 및 기능 prefix를 추가한다.

```text
/api + /v1/user + /users
  → /api/v1/user/users
```

이 구조는 전역 부트스트랩에서 각 기능 Router를 직접 import하지 않아도 신규 앱을 연결할 수 있게 한다.

### 5.3 Model 컨벤션

모델은 다음 package에서 노출한다.

```text
app/features/<name>/models/
```

`registry.import_models()`가 등록 앱의 models package를 import하면 SQLAlchemy 모델이 공통 `Base.metadata`에 포함된다. 같은 metadata는 다음 두 경로에서 사용한다.

- 개발 모드의 테이블 생성
- Alembic migration 및 autogenerate

따라서 `INSTALLED_APPS`에 등록된 앱 목록은 API 결선뿐 아니라 데이터베이스 스키마 수집 범위에도 영향을 준다.

### 5.4 Admin 컨벤션

SQLAdmin View가 필요한 앱은 다음 값을 노출한다.

```text
app/features/<name>/admin.py
  └─ admin_views: list[type]
```

Admin 기능이 활성화되면 Registry가 이 목록을 SQLAdmin에 등록한다. 현재 Admin은 기본 비활성화되어 있고 production 환경에서는 활성화를 거부하도록 설정 계약이 강화되어 있다.

관리자용 API는 Bearer token 기반 `require_admin` Dependency로 보호한다. `home` 접근 로그 API와 `user` API가 이 정책을 적용한 참조 구현이다.

### 5.5 선택적 import-time 연결

앱 package의 `__init__.py`는 필요한 경우 import-time 부수효과를 제공할 수 있다. `home` 앱의 접근 로그 sink 등록이 그 예다.

이 기능은 제한적으로 사용해야 한다. 일반 비즈니스 로직은 명시적인 Dependency 또는 Service 호출로 처리하고, 프레임워크와 기능 사이의 결선처럼 앱 로드 시 한 번 필요한 작업에만 사용한다.

## 6. 기능 앱 표준 구조

```text
app/features/<name>/
├─ __init__.py
├─ api/
│  └─ routers/
│     ├─ router.py
│     └─ v1/<name>.py
├─ dependencies/
│  └─ <name>_dependencies.py
├─ models/
│  └─ models.py
├─ repositories/
│  └─ <resource>_repository.py
├─ schemas/
│  └─ <name>_schema.py
├─ services/
│  └─ <name>_service.py
├─ admin.py
├─ exceptions.py
└─ tests/
```

모든 앱이 모든 선택 파일을 가져야 하는 것은 아니다. Router, Models, Admin은 필요에 따라 생략할 수 있지만, 존재한다면 위 컨벤션과 공개 이름을 따라야 한다.

## 7. 애플리케이션 생성 과정

[`main.py`](../../main.py)는 `create_app()`을 호출하는 얇은 진입점이다. 실제 조립은 [`app/core/bootstrap.py`](../../app/core/bootstrap.py)가 담당한다.

```text
1. AppRegistry가 INSTALLED_APPS를 읽는다.
2. 등록 앱 package를 import하고 유효성을 검사한다.
3. 등록 앱의 Models를 import해 Base.metadata를 완성한다.
4. FastAPI 인스턴스와 lifespan을 생성한다.
5. CORS와 사용자 정보 middleware를 설치한다.
6. 공통 exception handler를 설치한다.
7. 등록 앱의 Router를 순서대로 설치한다.
8. health endpoint와 개발용 API 문서를 구성한다.
9. 허용된 환경에서만 SQLAdmin View를 설치한다.
```

모델 import를 FastAPI 인스턴스 생성보다 먼저 수행하는 이유는 startup 테이블 처리와 migration metadata가 동일한 모델 집합을 사용하게 하기 위해서다.

## 8. 공통 기반 기능

### 8.1 설정 관리

Pydantic Settings를 사용해 애플리케이션, DB, CORS, Celery 등의 설정을 관리한다. 설정 우선순위는 시스템 환경 변수, `.env`, 코드 기본값 순이다.

잘못된 조합은 가능한 한 시작 시 검증한다. 예를 들어 wildcard CORS Origin과 credentials 허용 조합, production에서의 SQLAdmin 활성화 등을 설정 단계에서 차단한다.

### 8.2 데이터베이스

- SQLAlchemy 비동기 세션을 사용한다.
- 요청용 세션과 백그라운드 기록용 엔진·세션을 분리한다.
- 선택적인 primary/replica 읽기·쓰기 라우팅을 지원한다.
- 개발 모드에서는 `create_all`을 사용할 수 있다.
- 운영 모드에서는 Alembic migration을 사용한다.

Alembic 환경도 `AppRegistry.discover()`와 `import_models()`를 사용한다. 따라서 앱 등록 규칙이 런타임과 migration에서 동일하다.

### 8.3 접근 로그

`UserInfoMiddleware`는 요청과 응답 정보를 수집하고 별도의 background task runner를 통해 저장한다. 기능 모델을 core middleware가 직접 import하지 않도록 sink protocol을 사이에 둔다.

현재 구현은 다음 운영 요구 사항을 반영한다.

- background task 수 제한과 종료 시 drain
- drain timeout task의 취소 및 회수
- 신뢰 프록시 기반 전달 헤더 처리
- 민감 query parameter 마스킹
- session identifier의 원문 비저장
- 로그 보존 기간을 위한 설정과 정리 경로

### 8.4 Celery

Celery는 앱별 worker를 두지 않고 `app/celery/`에서 중앙 관리한다. 비동기 DB 작업은 워커 프로세스에서 재사용 가능한 이벤트 루프 bridge를 통해 실행해 event loop와 connection pool의 수명주기를 안정화한다.

### 8.5 공통 예외 처리

bootstrap은 애플리케이션 예외, 요청 검증 오류, Starlette HTTP 오류, 처리되지 않은 예외를 공통 응답 형식으로 변환한다. 기능 앱은 자체 예외 타입을 정의할 수 있지만 HTTP 응답 일관성은 core handler가 담당한다.

## 9. 신규 앱 추가 절차

### 9.1 스캐폴딩 생성

```powershell
uv run python -m scripts.new_app orders
```

Admin 파일까지 필요하면 다음 옵션을 사용한다.

```powershell
uv run python -m scripts.new_app orders --with-admin
```

생성기는 `app/features/orders/`의 기본 디렉터리와 Router·Dependency 골격을 만든다. 설정 파일은 자동으로 변경하지 않는다.

### 9.2 수동 등록

[`config.py`](../../config.py)에 앱 이름을 추가한다.

```python
INSTALLED_APPS: list[str] = [
    "home",
    "blog",
    "reply",
    "sns",
    "user",
    "orders",
]
```

이 단계가 Django식 passive 관리의 핵심이다. 디렉터리를 생성했지만 목록에 추가하지 않은 앱은 설치되지 않는다.

### 9.3 구성요소 구현

일반적인 구현 순서는 다음과 같다.

1. SQLAlchemy Model과 Pydantic Schema를 정의한다.
2. Repository에 데이터 접근 코드를 작성한다.
3. Service에 유스케이스와 비즈니스 규칙을 작성한다.
4. Dependency에서 Session과 Service를 구성하고 트랜잭션 경계를 둔다.
5. 버전별 Router에 endpoint를 작성한다.
6. 필요하면 `admin_views`를 추가한다.
7. migration을 생성하고 schema 차이가 없는지 확인한다.
8. 앱 단위 테스트와 Registry·endpoint inventory 테스트를 실행한다.

### 9.4 등록 확인

신규 앱은 최소한 다음 사항을 검증해야 한다.

- Registry가 `INSTALLED_APPS` 순서대로 앱을 발견한다.
- `<name>_router`가 예상 URL에 설치된다.
- 모델이 `Base.metadata`에 포함된다.
- Alembic head 적용 후 실제 테이블이 존재한다.
- Dependency 성공 시 commit, 실패 시 rollback된다.
- Admin이 있다면 `admin_views`가 정확한 모델을 등록한다.

## 10. 개발 내역과 설계의 발전

다음 내역은 저장소 Git 이력에 나타난 주요 설계 변화를 목적 중심으로 정리한 것이다.

### 10.1 기반 구조 도입과 passive-style 정체성 확립

- 2026-06-30: `fastapi-default-project-structure`를 기반으로 passive-style 저장소를 구성했다.
- 2026-07-01: README를 Django `INSTALLED_APPS`형 수동 등록 구조에 맞게 정리했다.
- 프로젝트 이름과 설명에서 기존 default 구조의 잔여 표현을 제거했다.

이 단계에서 “앱 목록은 명시적으로 관리하고 내부 결선은 컨벤션으로 처리한다”는 저장소의 중심 목적이 확립되었다.

### 10.2 실행 안정성과 계층 책임 정리

- 누락된 공통 로그 유틸리티를 복구했다.
- Celery의 이벤트 루프 재사용과 background 로그 task의 상한·drain을 구현했다.
- 실제 코드에 존재하지 않던 UnitOfWork 설명을 제거했다.
- 트랜잭션 경계를 기능 Dependency로 명확히 했다.
- 공통 모델 mixin, pagination utility, Repository update 동작을 정비했다.

이 단계는 문서상의 이상적인 구조보다 실제 코드의 책임과 동작을 기준으로 아키텍처를 정리한 과정이다.

### 10.3 품질 기반 구축

- MyPy 오류를 해소하고 타입 검사를 프로젝트 기준으로 채택했다.
- Ruff formatting과 lint, Bandit, Pytest를 CI 품질 게이트로 추가했다.
- endpoint, Repository, 앱 결선에 관한 테스트 범위를 확대했다.

### 10.4 데이터베이스와 관리 기능 확장

- primary/replica 읽기·쓰기 DB Router와 설정 일원화를 추가했다.
- 전체 기능 모델에 SQLAdmin ModelView를 추가했다.
- 비밀번호 hash와 같은 민감 컬럼이 Admin에 노출되지 않도록 검증했다.

### 10.5 도메인 명칭을 기능 중심으로 정리

- 2026-08-11: `app/domains`를 `app/features`로 변경했다.

`features`라는 이름은 이 저장소가 엄격한 Domain-Driven Design 프레임워크를 강제하기보다, 독립적으로 설치 가능한 기능 앱 구조를 제공한다는 목적을 더 정확히 표현한다.

### 10.6 passive 등록의 실패 처리 강화

- 선택 모듈 부재와 내부 import 실패를 구분했다.
- 잘못된 앱 이름과 중복 등록을 명시적으로 거부했다.
- 신규 앱 생성기가 `INSTALLED_APPS` 수동 등록 단계를 정확히 안내하도록 수정했다.

이 변경들은 silent failure를 줄이고 수동 등록의 장점인 명확성을 코드 수준에서도 보장한다.

### 10.7 운영 안전성 강화

- CORS 설정의 잘못된 조합을 시작 단계에서 차단했다.
- timeout된 background task를 정리하도록 종료 수명주기를 보강했다.
- SQLAdmin을 기본 비활성화하고 production 활성화를 금지했다.
- 접근 로그 및 사용자 API에 관리자 권한 검사를 적용했다.
- 전체 기능 테이블을 Alembic baseline과 schema parity 테스트에 반영했다.
- 신뢰 프록시와 접근 로그 개인정보 처리를 강화했다.
- endpoint inventory, migration check, coverage threshold를 CI 계약으로 추가했다.

이 단계에서 프로젝트는 개발 구조 예제를 넘어, 잘못된 기본 설정과 누락된 앱 결선을 자동 검출하는 템플릿으로 발전했다.

## 11. 테스트가 보장하는 구조적 계약

테스트는 개별 CRUD 성공뿐 아니라 프로젝트 구조의 불변 조건을 검증한다.

| 계약 | 검증 내용 |
|---|---|
| 수동 등록 | `INSTALLED_APPS` 순서 보존, 누락 package 오류, 중복 거부 |
| 컨벤션 결선 | Router·Models·Admin 공개 이름과 Registry 설치 결과 |
| 오류 투명성 | 선택 모듈 부재와 내부 import 실패 구분 |
| API 구성 | 등록 앱별 endpoint inventory 유지 |
| DB 스키마 | Alembic migration과 등록 모델 metadata의 일치 |
| Admin 보안 | 기본 비활성화, production 금지, 민감 컬럼 비노출 |
| 관리자 API | 토큰 누락·오류·성공에 따른 인증 결과 |
| 설정 | DB Router와 CORS 등 환경 설정의 fail-fast 동작 |
| 코드 품질 | Ruff, format, MyPy, Bandit, Pytest, coverage 기준 |

이 테스트들은 템플릿 사용자가 기능 앱을 추가하거나 core를 수정할 때 passive-style의 핵심 규칙이 조용히 깨지는 것을 방지한다.

## 12. 의도적으로 선택하지 않은 방식

### 12.1 디렉터리 자동 스캔

이 저장소는 `app/features/*`를 순회해 모든 앱을 자동 활성화하지 않는다. 자동 스캔은 앱 생성만으로 즉시 연결되는 편의가 있지만, 설치 범위와 순서가 파일 시스템 상태에 암묵적으로 의존한다.

자동 스캔 방식은 별도의 active-style 변형이 담당하며, 이 저장소는 passive-style의 명시성을 유지한다.

### 12.2 도메인별 UnitOfWork

현재 구조는 FastAPI Dependency와 SQLAlchemy Session을 트랜잭션 경계로 사용한다. 별도의 UnitOfWork abstraction을 추가하지 않는다.

하나의 요청에서 여러 aggregate 또는 외부 시스템을 복잡하게 조율해야 하는 프로젝트라면 UnitOfWork를 추가할 수 있지만, 기본 템플릿에서는 계층 수와 학습 비용을 줄이는 쪽을 선택했다.

### 12.3 기능 간 강한 결합

기능 앱의 독립성과 탈착성을 위해 기능 간 직접 import, FK, relationship을 기본 예제의 중심으로 삼지 않는다. 실제 제품 요구에 따라 관계를 추가할 수 있지만, 그 경우 앱 제거 가능성과 migration 순서를 함께 설계해야 한다.

## 13. 확장 시 지켜야 할 원칙

- 앱 설치 여부는 `INSTALLED_APPS`에서만 결정한다.
- core에 특정 기능 앱 import를 추가하지 않는다.
- Router의 직접 ORM 사용을 피한다.
- Service와 Repository에서 요청 단위 commit을 수행하지 않는다.
- 선택 모듈 내부 오류를 무시하지 않는다.
- 신규 모델은 migration과 schema parity 테스트를 함께 추가한다.
- 관리자·운영 데이터 endpoint는 명시적인 인증 Dependency를 사용한다.
- 기능을 제거할 때 Router뿐 아니라 Model, Admin, migration 영향도 함께 확인한다.
- 문서와 코드가 충돌하면 코드를 검증한 뒤 문서를 갱신한다.

## 14. 프로젝트의 최종 성격

이 프로젝트는 다음 세 가지를 결합한 FastAPI 개발용 기본 구조다.

1. **Django식 명시적 앱 관리**
   - 설치 앱과 순서를 `INSTALLED_APPS`로 통제한다.

2. **FastAPI식 조립과 의존성 주입**
   - Router와 generator Dependency를 활용해 HTTP 처리와 트랜잭션을 구성한다.

3. **기능별 계층 분리**
   - 기능 앱 내부에서 Router, Dependency, Service, Repository, Model을 일관된 구조로 유지한다.

핵심 가치는 자동화 자체가 아니라 **명시적인 선택과 반복 가능한 결선의 균형**이다. 앱을 사용할지는 개발자가 결정하고, 사용하기로 한 앱을 FastAPI 애플리케이션에 연결하는 반복 작업은 Registry와 컨벤션이 담당한다.

이 원칙이 이 저장소를 단순 CRUD 예제가 아니라, 여러 기능을 장기간 추가·제거·관리할 수 있는 프로젝트 시작점으로 만든다.
