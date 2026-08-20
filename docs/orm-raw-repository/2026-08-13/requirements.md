# ORM/Raw Repository 고도화 요구 명세서

## 1. 문서 정보

| 항목 | 값 |
|---|---|
| 문서 목적 | ORM 및 Raw SQL 데이터 접근 방식의 구조·동작·품질 요구사항 정의 |
| 적용 프로젝트 | `fastapi-project-structure-django-passive-style` |
| 기준 구조 | `config.INSTALLED_APPS` 기반 수동 App Registry 및 Dependency → Service → Repository 흐름 |
| 관련 계획서 | `docs/orm-raw-repository/2026-08-13/development-plan.md` |
| 관련 지침서 | `docs/orm-raw-repository/2026-08-13/workflow-guide.md` |
| 상태 | 개발 착수 전 요구사항 기준선 |
| 코드 검토 기준 | 2026-08-13 passive-style 작업 트리, 307개 테스트 수집 기준 |
| 구현 피드백 기준 | 2026-08-18 `fastapi-default-project-structure` `db49e9c` 및 CRP F-001~F-018 |

## 2. 목표

본 작업은 현재 프로젝트의 FastAPI 워크플로우를 유지하면서 다음 두 데이터 접근 방식을
일관된 구조로 제공해야 한다.

1. SQLAlchemy ORM 모델 기반 CRUD 및 도메인 조회
2. SQLAlchemy `text()` 기반 Raw SQL 조회 및 변경

두 방식은 Repository 구현만 달라야 하며 다음 항목은 동일해야 한다.

- Dependency Injection과 객체 조립
- Service 유스케이스 실행
- read-only/writer DB session 선택
- 트랜잭션 경계
- Pydantic 입력·응답 검증
- 버전별 라우터 구성과 App Registry adapter의 최종 취합
- OpenAPI/Scalar 문서 품질
- 예외 처리, 테스트 및 정적 검사 기준

## 3. 용어

| 용어 | 정의 |
|---|---|
| View | FastAPI path operation 함수. HTTP 계약과 유스케이스 호출을 담당한다. |
| Dependency | FastAPI `Depends`로 세션과 Service를 생성·조립하는 함수다. |
| Service | 비즈니스 규칙과 유스케이스 순서를 담당한다. |
| Repository | ORM 또는 Raw SQL 데이터 접근을 담당한다. |
| ORM Base | `CRUDBase`와 이를 상속하는 `BaseRepository` 계층이다. |
| Raw Base | `RawCRUDBase`와 이를 상속하는 `RawRepositoryBase` 계층이다. |
| DTO | 외부 요청·응답 계약을 표현하는 Pydantic 모델이다. |
| 쓰기 View | DB 상태를 변경하는 POST/PUT/PATCH/DELETE path operation이다. |
| 조회 View | DB 상태를 변경하지 않는 GET/HEAD path operation이다. |

## 4. 요구사항 해석 및 보강 결정

### 4.1 View에서 비즈니스 코드 실행

원 요구사항의 “비즈니스 코드는 View에서 실행한다”는 다음 의미로 확정한다.

> View는 Dependency로 주입받은 Service의 비즈니스 유스케이스를 호출하여 실행한다.
> 비즈니스 규칙 자체는 Service에 작성하고 SQL은 Repository에 작성한다.

View에 직접 작성할 수 있는 코드는 다음으로 제한한다.

- HTTP 파라미터와 요청 본문 수신
- Service 유스케이스 호출
- 쓰기 성공 후 응답 전 commit 호출
- 반환값의 Pydantic 응답 변환
- HTTP 상태와 OpenAPI 메타데이터 선언

### 4.2 공통 모델 상속

모든 ORM 모델은 `Base` 계층을 사용해야 하지만 모든 테이블에 동일한 컬럼을 강제하지
않는다. 공통 필드는 작은 mixin으로 조합한다.

- 일반 변경 가능 엔티티: UUID PK + created/updated timestamp
- 생성 후 불변 로그: UUID PK + created timestamp
- 외부 시스템 PK 사용 테이블: 해당 PK 정책을 명시적으로 예외 처리

### 4.3 Scalar 문서의 계약 출처

ORM 모델은 DB 매핑 계약이며 Scalar API 문서의 직접 계약이 아니다. Scalar 문서는
FastAPI View와 Pydantic DTO가 생성한 OpenAPI schema를 기준으로 한다.

- ORM 응답: ORM 객체 → `from_attributes=True` Pydantic 응답 DTO
- Raw 응답: `RowMapping` → 명시적 `dict` 변환 → Pydantic 응답 DTO
- ORM 컬럼 comment는 Pydantic 설명을 대체하지 않는다.

### 4.4 Raw SQL 사용 원칙

Raw SQL은 ORM을 우회하기 위한 일반 기본값이 아니다. 다음 상황에서 선택한다.

- 복잡한 집계, 윈도 함수, CTE 또는 DB 최적화 쿼리
- ORM 표현보다 SQL 계약이 더 명확한 리포트
- 실행 계획을 기준으로 관리해야 하는 성능 민감 조회
- 기존 DB의 저장 프로시저 또는 DB 전용 기능 연계

일반 단일 테이블 CRUD는 ORM Repository를 우선한다.

### 4.5 JWT 인증 적용 범위

프로젝트의 기본 인증 방식은 JWT를 전제로 하지만 이번 ORM/Raw Repository 및 lifecycle
고도화 작업에는 JWT 인증 기능의 신규 적용이나 확장을 포함하지 않는다. 현재 인증 동작은
호환성 기준선으로만 보호한다.

Access/refresh token 정책, rotation, revoke/logout, 권한 모델과 보안 저장 방식은 별도의
후속 요구 명세에서 정의한다.

### 4.6 Redis 적용 범위

API용 Redis client, cache, session 저장소와 readiness 연계는 이번 작업에 포함하지 않고 JWT와
마찬가지로 후속 요구 명세로 분리한다. 기존 Celery broker/backend의 Redis 설정과 동작은
변경하지 않는다.

## 5. 우선순위

| 등급 | 의미 |
|---|---|
| P0 | 구현 및 배포 전에 반드시 충족해야 하는 구조·보안·정합 요구사항 |
| P1 | 이번 고도화 범위에서 반드시 제공해야 하는 기능·테스트 요구사항 |
| P2 | 호환성을 유지하면서 점진적으로 적용할 품질 개선 요구사항 |

## 6. 아키텍처 요구사항

### AR-001 공통 계층 흐름 [P0]

ORM과 Raw View는 모두 다음 호출 흐름을 준수해야 한다.

```text
View -> Dependency -> Service -> Repository -> AsyncSession
```

수용 기준:

- View가 `AsyncSession`을 직접 주입받지 않는다.
- View와 Service가 `session.execute()`를 직접 호출하지 않는다.
- Repository가 FastAPI `Request`, `Response`, `Depends`를 import하지 않는다.

### AR-002 공통 모듈 위치 [P0]

모든 기능에서 재사용하는 DB, middleware, model base, repository base, service base와 태그
메타데이터는 `app/core` 아래에 둬야 한다.

수용 기준:

- 기능 간 상대 기능 import로 공통 코드를 공유하지 않는다.
- 도메인 SQL과 도메인 규칙을 `app/core`에 두지 않는다.

### AR-003 ORM/Raw Base 분리 [P0]

ORM Base와 Raw Base는 각각 독립적인 상속 계층이어야 한다.

```text
BaseRepository -> CRUDBase
RawRepositoryBase -> RawCRUDBase
```

수용 기준:

- `RawRepositoryBase`가 `BaseRepository`를 상속하지 않는다.
- 하나의 Base 클래스가 ORM 모델과 Raw row를 동시에 반환하지 않는다.
- 공유되는 것은 `AsyncSession`, 공통 예외와 로깅 정책뿐이다.

### AR-004 App Registry 기반 명시적 라우터 취합 [P0]

라우터는 디렉터리를 자동 스캔하거나 `main.py`에 기능별 import를 나열하지 않고 다음 순서로
명시 취합해야 한다.

```text
v1/<view>.py -> api/routers/router.py -> AppConfig -> INSTALLED_APPS
  -> Apps.populate() -> install_routers() -> FastAPI
```

수용 기준:

- 각 기능은 `apps.py`에 `AppConfig` subclass를 제공한다.
- 기능 root `__init__.py`는 Router나 Model을 import하지 않는 가벼운 package marker로 유지한다.
- `config.INSTALLED_APPS`가 설치 앱과 순서의 유일한 진실 공급원이다.
- `AppConfig.router_module`, `router_attribute`, `router_prefix` 계약에 따라
  `app/core/apps/wiring.py::install_routers()`가 최종 등록한다.
- module이 없으면 선택 기능 부재로 처리하지만 module이 있는데 공개 attribute가 없거나 내부
  import가 실패하면 startup을 실패시킨다.
- 등록하지 않은 앱은 route, model metadata, Admin, `ready()` 어디에도 나타나지 않는다.
- 새 기능의 `INSTALLED_APPS` 등록 누락과 method/path 충돌을 테스트가 탐지한다.

### AR-005 Lifespan Resource Manager [P0]

애플리케이션 프로세스 수명 자원의 생성과 해제는
`app/core/resources.py`의 `manage_application_resources(app)` 한 곳에서 관리해야 한다.

수용 기준:

- `app/core/bootstrap.py`의 lifespan은 resource manager context를 호출하고 yield하는 조립만 담당한다.
- startup과 shutdown 로직이 기능 모듈 또는 여러 event handler에 분산되지 않는다.
- 실제 생성된 자원을 `app.state.resources`에서 명시적으로 참조할 수 있다.
- cleanup 완료 후 `app.state.resources`가 닫힌 자원을 참조하지 않는다.
- 기존 `Apps`/`AppConfig` registry를 유지하고 별도의 범용 plugin registry나 decorator
  framework를 추가하지 않는다.
- `create_app()`의 registry population은 lifespan 진입 전에 완료한다.

### AR-006 자원 소유권 [P0]

Resource Manager는 FastAPI API 프로세스가 생성하고 소유한 장기 수명 자원만 관리해야 한다.

수용 기준:

- DB writer, reader, background engine pool을 shutdown에서 dispose한다.
- DB engine 정의가 session 모듈에 남더라도 shutdown 소유자는 Resource Manager 하나다.
- 요청별 `AsyncSession`은 Dependency가 닫는다.
- Celery worker의 broker/backend 연결을 FastAPI lifespan이 닫지 않는다.
- shutdown에서 DB table drop을 실행하지 않는다.

### AR-007 Registry 소유 모델 기반 테이블 생성 조건 [P0]

startup은 `create_app()`이 이미 population한 **해당 app의 registry**가 수집한 모델의 테이블만
기준으로 자동 생성 여부를 결정해야 한다. `Base.metadata`는 프로세스 전역 객체라 먼저 import된
다른 앱의 테이블이 남을 수 있으므로 그 전체를 생성 대상으로 사용해서는 안 된다.

수용 기준:

- `app.state.app_registry.get_models()`에서 중복 제거한 `model.__table__` 목록이 0개이면 DB
  연결과 `create_all()`을 시도하지 않는다.
- 소유 table이 1개 이상이고 개발 자동 생성 정책이 활성화된 경우에만
  `Base.metadata.create_all(tables=owned_tables)`을 실행한다.
- 운영 환경에서는 모델이 있어도 `create_all()`을 실행하지 않고 Alembic을 사용한다.
- 모델 파일 존재 여부만으로 생성 여부를 판정하지 않는다.
- `manage_application_resources()`가 디렉터리를 스캔하거나 별도 `import_all_models()`를 호출하지 않는다.
- 동일 startup에서 registry population과 모델 import를 중복 실행하지 않는다.
- Alembic은 `Apps().populate(INSTALLED_APPS, run_ready=False)`로 런타임과 동일한 모델 집합을 본다.
- 기본 app을 먼저 생성한 뒤 빈 registry 또는 일부 앱 registry로 새 app을 만들어도 이전에
  import된 전역 metadata 테이블이 새 app의 개발 DB에 생성되지 않는다.

### AR-008 실패 안전 cleanup [P0]

정상 shutdown뿐 아니라 startup 중간 실패에서도 이미 생성된 자원을 정리해야 한다.

수용 기준:

- startup 전체가 `try/finally` 또는 동등한 async context manager cleanup으로 보호된다.
- 하나의 cleanup 실패 때문에 다른 자원 cleanup이 생략되지 않는다.
- 종료 순서는 background task drain, DB engine dispose이며, ADR-019 개정으로 Queue logging을
  도입한 경우 logging queue flush/listener stop을 마지막에 수행한다.
- 자원별 shutdown timeout이 존재한다.

### AR-009 Background task 완전 종료 [P0]

`BackgroundTaskRunner`는 shutdown timeout 후에도 task를 실행 상태로 남겨서는 안 된다.

수용 기준:

- timeout 전 완료된 task 결과를 회수한다.
- timeout 후 pending task에 `cancel()`을 호출한다.
- 취소한 task를 `asyncio.gather(..., return_exceptions=True)` 또는 동등한 방식으로 await한다.
- cancellation이 session context의 rollback/close를 실행할 기회를 보장한다.
- drain 완료 후 추적 task 집합이 비어 있다.
- 모든 task 종료 후 DB를 dispose하고, Queue logging을 도입한 경우 listener를 마지막에 닫는다.
- 내부 `drain()` 대기 시간은 바깥 cleanup timeout보다 짧아야 한다. 같은 5초를 사용하면 pending
  task를 cancel하고 gather하는 순간 바깥 timeout이 끊어 session의 `finally`가 실행되지 않을
  수 있으므로, 예를 들어 전체 5초 중 80%만 정상 대기에 쓰고 나머지를 cancel/await에 예약한다.
- 실제 timeout을 발생시킨 테스트가 취소된 task의 `finally`, session rollback/close와 최종
  task 집합 0개까지 확인한다.

### AR-010 Celery worker async 자원 종료 [P0]

Celery worker process가 소유한 영속 event loop와 DB pool은 worker shutdown signal에서
명시적으로 종료해야 한다.

수용 기준:

- Celery 동기 task wrapper 내부의 DB 호출은 기존 async Service/Repository를 사용한다.
- worker process별 event loop를 재사용한다.
- worker shutdown에서 DB engine/pool을 loop가 살아 있는 동안 dispose한다.
- `shutdown_asyncgens()` 실행 후 event loop를 close한다.
- 종료 후 global loop reference를 `None`으로 초기화한다.
- FastAPI lifespan과 Celery worker cleanup의 소유권이 섞이지 않는다.

## 7. ORM 모델 요구사항

### ORM-MDL-001 공통 Declarative Base [P0]

모든 ORM 모델은 `app/core/models/models_base.py`에서 정의한 `Base` 계층을 사용해야 한다.

수용 기준:

- 독립적인 `DeclarativeBase`가 기능 폴더에 존재하지 않는다.
- 모든 모델이 Alembic과 `Base.metadata`에 등록된다.

### ORM-MDL-002 공통 필드 mixin [P1]

UUID와 timestamp를 반복 선언하지 않고 공통 mixin을 사용해야 한다.

수용 기준:

- `UUIDPrimaryKeyMixin`, `CreatedAtMixin`, `UpdatedAtMixin`으로 책임을 분리한다.
- 변경 가능 엔티티는 세 Mixin 조합을, 불변 로그는 UUID와 created 조합만 사용한다.
- 기존 모델 전환 후 Alembic schema diff가 발생하지 않는다.
- 불변 로그 모델은 불필요한 `updated_at`을 강제받지 않는다.

### ORM-MDL-003 PK 타입 계약 [P1]

ORM Repository의 PK 타입 가정을 제네릭 계약으로 표현해야 한다.

수용 기준:

- `BaseRepository[ModelT, PrimaryKeyT]`를 정식 타입 계약으로 사용한다.
- 기존 문자열 UUID Repository는 `BaseRepository[ModelT, str]`로 명시한다.
- Base가 문자열 `id`를 암묵적으로 가정하지 않는다.
- 외부 PK 모델의 예외 정책이 문서와 테스트에 명시된다.

### ORM-MDL-004 컬럼 계약 [P1]

모델은 DB 제약과 Python 타입을 일치시켜야 한다.

수용 기준:

- nullability, unique, index, FK와 `Mapped` 타입이 모순되지 않는다.
- DB에서 의미가 있는 컬럼에는 필요에 따라 comment를 제공한다.
- API 필드 설명은 Pydantic DTO에 별도로 정의한다.

## 8. ORM Repository 요구사항

### ORM-REP-001 CRUD primitive 책임 [P0]

`crud_base.py`는 ORM 영속성 primitive만 제공해야 한다.

필수 책임:

- session 저장
- PK 조회
- entity add/delete
- flush/refresh

금지 책임:

- commit/rollback
- HTTP 예외 생성
- eager loading과 도메인 전용 쿼리

### ORM-REP-002 안정적인 공개 CRUD [P1]

`repository_base.py`는 일반 모델에서 반복되는 최소 공개 CRUD를 제공해야 한다.

필수 API:

- create
- get by ID 및 not-found 변형
- pagination list
- count와 exists
- update by ID
- delete by ID

이 목록이 Base의 최소 정식 공개 API다. 기존 이름은 호환 wrapper로만 유지한다.

수용 기준:

- 공개 메서드 이름과 반환 타입이 타입 검사된다.
- 모든 ORM 기능 Repository가 이 Base를 상속한다.
- 기존 API 응답과 상태 코드가 유지된다.

### ORM-REP-003 입력 불변성 [P0]

Repository는 호출자가 전달한 `dict`를 변경해서는 안 된다.

수용 기준:

- create/bulk create/update 호출 후 원본 입력과 호출 전 값이 동일하다.
- ID 기본값은 모델 default 또는 복사된 데이터에서 처리한다.
- 입력 불변성 테스트가 존재한다.

### ORM-REP-004 존재 확인 최적화 [P2]

존재 확인은 전체 row count보다 SQL `EXISTS`를 사용해야 한다.

수용 기준:

- `exists`, `exists_by`가 boolean 존재 확인 SQL을 생성한다.
- 반환 타입은 항상 `bool`이다.

### ORM-REP-005 고급 쿼리 분리 [P1]

eager loading, join, partial column, batch와 같은 고급 쿼리는 실제 공통성이 확인된 경우만
Base에 둬야 한다.

수용 기준:

- 도메인 특화 관계명과 컬럼명이 Base에 없다.
- 문자열 관계·컬럼 접근을 신규 public API에서 확대하지 않는다.
- 기능별 쿼리는 해당 기능 Repository의 명시적 메서드가 소유한다.
- 두 개 이상의 실제 기능에서 같은 구현이 확인된 경우에만 별도 Mixin으로 추출한다.

### ORM-REP-006 예외 변환 일관성 [P0]

모든 create/update/delete/bulk 경로는 동일한 DB 예외 변환 정책을 사용해야 한다.

수용 기준:

- 무결성 충돌은 프로젝트 중복 또는 DB 예외로 변환된다.
- 예상하지 못한 SQLAlchemy 오류는 `DatabaseException`으로 변환된다.
- 원본 예외가 exception chaining으로 보존된다.
- Repository 실행 중 오류뿐 아니라 응답 전 `commit()`에서 발생한 무결성/SQLAlchemy 오류도
  같은 변환기를 거치며 2xx 응답으로 확정되지 않는다.
- 내부 로그는 `exc_info`와 안전한 operation/model/query 이름을 남기되 SQL 본문, bind params,
  DSN은 남기지 않는다.
- `AppException.detail`에는 model, 안전한 식별자, 공개 error code만 허용하며 `str(e)`,
  `str(e.orig)` 또는 DB driver 메시지를 넣지 않는다.

### ORM-REP-007 점진적 호환성 [P1]

기존 `BaseRepository` public 메서드는 사용처 조사 없이 즉시 삭제하지 않는다.

수용 기준:

- 메서드별 사용처 목록이 작성된다.
- 호환 wrapper → 호출부 전환 → 제거 순서로 변경한다.
- 전환 전 실제 수집된 전체 테스트 수와 API contract가 유지된다. 2026-08-13 검토 기준은
  307개이며 환경 의존 stderr 인코딩 실패 1건을 제외한 306개가 통과한다.

## 9. Raw Repository 요구사항

### RAW-REP-001 RawCRUDBase 제공 [P0]

`app/core/repositories/raw_crud_base.py`를 추가해야 한다.

필수 protected API:

- `_fetch_one(TextClause, params) -> RowMapping | None`
- `_fetch_all(TextClause, params) -> Sequence[RowMapping]`
- `_fetch_scalar(TextClause, params) -> object`
- `_execute(TextClause, params) -> int`

수용 기준:

- 문자열 SQL보다 `TextClause` 입력을 기본 계약으로 사용한다.
- 결과 형태별 테스트가 존재한다.
- commit/rollback을 수행하지 않는다.

### RAW-REP-002 RawRepositoryBase 제공 [P0]

`app/core/repositories/raw_repository_base.py`를 추가해야 한다.

필수 책임:

- RawCRUDBase primitive의 안정적인 public API 제공
- SQLAlchemy 예외의 프로젝트 예외 변환
- keyword-only `query_name`을 받는 쿼리 이름 중심 로깅
- 민감 파라미터 미노출

수용 기준:

- 기능 Raw Repository가 이 Base를 상속한다.
- 도메인 SQL은 Base가 아닌 기능 Repository에 존재한다.
- 기능 Repository가 `feature.use_case` 형식의 안정적인 `query_name` 상수를 전달한다.
- `query_name`은 사용자 입력에서 만들지 않고 코드 상수로 소유하며 허용 문자와 길이를
  검증해 로그 cardinality를 제한한다.
- Base는 `query_name`, 소요 시간과 성공/실패만 기록하고 SQL 본문과 params를 기록하지 않는다.

### RAW-REP-003 named parameter 강제 [P0]

모든 외부 값은 named bind parameter로 전달해야 한다.

허용 예:

```python
text("SELECT * FROM orders WHERE user_id = :user_id")
```

금지 예:

```python
text(f"SELECT * FROM orders WHERE user_id = '{user_id}'")
```

수용 기준:

- 사용자 입력을 SQL 문자열에 직접 보간한 코드가 없다.
- `text()` 인자에 f-string, `%`, `.format()` 또는 사용자 값 문자열 연결을 사용하는 코드를
  정적 검사로 탐지하고 대표 injection 입력을 동적 테스트한다.

### RAW-REP-004 식별자 allowlist [P0]

테이블명, 컬럼명, 정렬 방향처럼 bind parameter를 사용할 수 없는 식별자는 코드가 소유한
allowlist에서 선택해야 한다.

수용 기준:

- 요청값이 SQL 식별자로 직접 사용되지 않는다.
- 허용하지 않은 정렬 키와 방향은 validation error가 된다.

### RAW-REP-005 결과 타입 및 DTO 경계 [P0]

Raw Repository는 `RowMapping` 또는 scalar를 반환하고 Service가 Pydantic DTO로 검증해야
한다.

수용 기준:

- View가 `Row`, `RowMapping`, `CursorResult`를 직접 반환하지 않는다.
- Raw 결과 컬럼 alias와 DTO 필드가 일치한다.
- 누락 또는 잘못된 타입의 결과가 Pydantic 검증에서 탐지된다.

### RAW-REP-006 DB 방언 관리 [P1]

MySQL 전용 SQL은 명시적으로 관리하고 해당 DB에서 통합 검증해야 한다.

수용 기준:

- MySQL 전용 함수와 문법에 주석 또는 문서 표시가 있다.
- SQLite 테스트 통과만으로 MySQL SQL의 정확성을 승인하지 않는다.
- 최소 한 개의 MySQL 통합 테스트 또는 실행 계획 검증 절차가 있다.
- 현재 저장소에는 `compose.test.yaml`이 없으므로 먼저 추가하고, 이후 로컬과 CI가 동일한
  MySQL service 구성을 사용한다.
- `compose.test.yaml`은 MySQL 8.4, healthcheck, `utf8mb4`, test 전용 계정과 삭제 가능한
  tmpfs 또는 삭제 가능한 volume을 제공하고 운영 credential을 사용하지 않는다.
- MySQL 8.4 기본 `caching_sha2_password` 접속에 필요한 `cryptography` 의존성을 명시한다.
- 고정된 test credential을 사용하는 DB port는 외부 인터페이스에 공개하지 않고
  `127.0.0.1:${MYSQL_TEST_PORT:-3308}:3306`처럼 loopback에만 bind한다. CI에서 host port가
  필요하지 않으면 service network 안에서만 접근한다.
- host port는 `${MYSQL_TEST_PORT:-3308}`처럼 변경 가능해야 하며 시작 전에 Windows
  `Get-NetTCPConnection` 또는 Linux `ss -ltn`으로 점유 여부를 확인한다. 다른 MySQL로 조용히
  접속하는 것을 credential 오류로 오인하지 않도록 실제 container identity도 확인한다.
- `mysql` pytest marker로 SQLite 단위 테스트와 MySQL 방언/migration 테스트를 분리한다.
- 표준 검증 순서는 compose 시작·health 확인 → Alembic head upgrade → MySQL 테스트 → 신규
  revision downgrade/re-upgrade → compose 및 volume 정리다.
- schema 초기화는 ORM metadata table만 삭제하지 않고 `alembic_version`을 포함한 실제 table을
  모두 제거한다. migration chain은 반드시 완전히 빈 schema 전용 fixture에서 시작한다.

### RAW-REP-007 Raw DML 지원 [P1]

Raw update/delete/insert를 사용할 때도 ORM과 같은 트랜잭션 규칙을 적용해야 한다.

수용 기준:

- Raw Repository는 affected row count만 반환하고 commit하지 않는다.
- 쓰기 View가 응답 전에 한 번 commit한다.
- read-only session에서 ORM/Core DML뿐 아니라 `TextClause`의 INSERT/UPDATE/DELETE도 실행 전에
  차단된다. 현재 `app/core/db/router.py::_is_write()`는 `UpdateBase`와 flush만 판별하므로 이
  보강 전에는 Raw DML 안전성을 충족한 것으로 보지 않는다.
- 문자열 첫 token 검사만으로 보안을 확정하지 않는다. default 프로젝트의 구현은 일반 DML과
  `SELECT ... FOR UPDATE`를 보강했지만 CTE로 감싼 DML을 읽기로 오판하는 잔여 위험을 남겼다.
  passive-style에서는 Raw public API가 statement에 명시적인 read/write intent를 붙이고 router가
  이를 우선 사용한다. intent가 없는 `TextClause`는 reader로 보내지 않는 fail-closed 정책을 쓴다.
- `fetch_*`는 read intent, `execute`는 write intent를 강제하고 write intent는 read-only session에서
  실행 전에 거부한다. 이로써 CTE read는 허용하면서 CTE DML과 미분류 SQL의 replica 오라우팅을
  막는다.
- Raw Base가 private `_READ_ONLY` key를 직접 참조하지 않도록 `db/router.py`가
  `is_read_only_session(session)` 같은 공개 판별 helper를 제공한다.
- 잠금 읽기(`SELECT ... FOR UPDATE`)는 write intent로 간주해 writer에 고정한다.

## 10. Dependency 및 트랜잭션 요구사항

### TX-001 Dependency 조립 책임 [P0]

Dependency는 세션을 선택하고 Service와 Repository 객체를 조립해야 한다.

수용 기준:

- Dependency가 Service 유스케이스를 실행하지 않는다.
- Dependency가 commit하지 않는다.
- teardown commit 패턴을 사용하지 않는다.

### TX-002 조회 세션 [P0]

조회 View는 `get_read_only_db_session` 기반 read-only Service Dependency를 사용해야 한다.

수용 기준:

- GET/HEAD 경로가 `get_writer_db_session` 또는 `get_routed_db_session`을 사용하지 않는다.
  단, 강한 일관성이 필요한 승인된 예외는 사유와 함께 allowlist로 관리한다.
- 조회 경로의 commit 호출 횟수는 0회다.
- DB Router 활성화 시 reader로 라우팅된다.

### TX-003 쓰기 세션 [P0]

DB 변경 View와 조회 후 쓰기 유스케이스는 `get_writer_db_session` 기반 Service
Dependency를 사용해야 한다.

수용 기준:

- POST/PUT/PATCH/DELETE의 DB 쓰기가 read session으로 실행되지 않는다.
- 첫 SELECT부터 primary writer에 고정되어 replica lag의 영향을 받지 않는다.
- DB를 쓰지 않는 POST는 이유가 기록된 allowlist로 관리한다.

### TX-004 응답 전 commit [P0]

쓰기 성공은 View 본문에서 응답 반환 전에 정확히 한 번 commit해야 한다.

수용 기준:

- `await service.commit()`이 View의 성공 경로에 존재한다.
- commit 실패 시 클라이언트가 2xx를 받지 않는다.
- 예외 경로는 commit 0회다.
- Repository와 Dependency에 commit 호출이 없다.

### TX-005 DB session 명명 계약 [P0]

SQLAlchemy `AsyncSession`을 제공하거나 저장하는 애플리케이션 코드는 이름으로 DB 자원임을
명확히 표현해야 한다.

수용 기준:

- 정식 Dependency 이름은 `get_read_only_db_session`, `get_writer_db_session`,
  `get_routed_db_session`, `get_background_db_session`이다.
- 요청 밖 context manager는 `background_db_session`으로 명명한다.
- Dependency 인자와 Service/Repository 생성자 및 속성은 `db_session`을 사용한다.
- `session` 단독 이름은 SQLAlchemy 문맥이 명확한 제한된 내부 지역 변수에서만 허용한다.
- 기존 `get_read_session`, `get_write_session`, `get_session`, `get_background_session`은
  호출부 전환 기간에 deprecated alias로만 유지한다.
- 호환 별칭은 가능하면 직접 대입해 callable identity를 유지한다. wrapper가 필요하면 기존
  `app.dependency_overrides[old_callable]`가 조용히 무효화되지 않도록 override 회귀 테스트를
  추가하고 호출부를 한 단계에서 함께 전환한다.
- 기존 이름 제거 전 전체 호출부와 Dependency override 테스트가 새 이름으로 전환된다.

### ORM-REP-008 무변경 UPDATE 의미 보존 [P0]

MySQL은 `CLIENT_FOUND_ROWS`를 사용하지 않으면 기존 값과 동일한 UPDATE의 `rowcount`를 0으로
반환할 수 있다. 따라서 `rowcount == 0`만으로 대상이 없다고 판정해 404를 반환해서는 안 된다.

수용 기준:

- Service가 수정 전 존재를 확인했거나 Repository가 후속 조회로 존재를 확인한 경우,
  무변경 PATCH는 현재 엔티티를 성공 응답으로 반환한다.
- 실제 부재와 무변경을 분리한 회귀 테스트가 있으며 MySQL 통합 테스트에서도 검증한다.
- 동시 삭제 가능성이 있는 유스케이스는 트랜잭션 격리 또는 조건부 UPDATE 정책을 명시한다.

## 11. Service 및 View 요구사항

### SVC-001 비즈니스 규칙 위치 [P0]

검증된 요청을 이용한 도메인 상태 전환, 기간 규칙, 중복 정책과 유스케이스 순서는
Service에 위치해야 한다.

수용 기준:

- 동일 유스케이스를 HTTP 외 경로에서 재사용할 수 있다.
- View에 데이터 접근 분기나 복잡한 도메인 조건이 없다.

### VIEW-001 버전별 파일 구성 [P1]

`v1` 이하에 업무 단위 View 파일을 여러 개 둘 수 있어야 한다.

수용 기준:

- 하나의 View 파일이 과도하게 커지면 resource 또는 use case 단위로 분리한다.
- 각 View 파일은 자체 `APIRouter`를 제공한다.
- 같은 버전의 그룹 `router.py`가 일관된 prefix와 tag로 취합한다.

### VIEW-002 ORM/Raw 응답 동등성 [P1]

ORM과 Raw View는 데이터 소스가 달라도 동일한 HTTP 품질 기준을 제공해야 한다.

수용 기준:

- 명시적 `response_model`을 사용한다.
- validation, 오류 상태와 pagination 형식이 프로젝트 기준과 일치한다.
- 내부 ORM 클래스 또는 Raw row가 응답 계약에 노출되지 않는다.

## 12. Scalar/OpenAPI 요구사항

### DOC-001 View 메타데이터 [P0]

모든 공개 path operation은 다음 정보를 제공해야 한다.

- `summary`
- 충분한 `description`
- 프로젝트 전체에서 고유한 `operation_id`
- 성공 `response_model`
- 성공 상태 코드
- 알려진 오류 `responses`
- 적절한 tag

204 응답은 body와 response model을 갖지 않는다.

### DOC-002 파라미터 문서 [P1]

Path, Query, Header와 요청 body는 설명, 실제 validation 제약과 대표 예시를 제공해야 한다.

수용 기준:

- 문서 제약과 런타임 Pydantic/FastAPI 검증이 일치한다.
- UUID, 날짜, pagination과 enum에 대표 예시가 있다.

### DOC-003 Pydantic schema [P0]

모든 외부 요청과 응답은 Pydantic 모델로 정의해야 한다.

수용 기준:

- 입력/출력 모델이 분리된다.
- 외부 노출 필드에 `description`이 있다.
- 주요 DTO에 `json_schema_extra.examples`가 있다.
- 민감 필드가 응답 schema에 포함되지 않는다.

### DOC-004 태그 메타데이터 정합성 [P0]

`app/core/tags_metadata.py`와 실제 Router tag를 동기화해야 한다.

수용 기준:

- 실제 사용되는 모든 tag가 metadata에 존재한다.
- 사용하지 않는 오래된 tag는 제거하거나 사유가 명시된다.
- `Auth`와 신규 예제 기능 tag가 포함된다.
- 구현 완료 기능에 “미구현/예정” 설명이 남아 있지 않는다.

### DOC-005 OpenAPI 자동 검증 [P1]

OpenAPI schema에 대한 자동 정합성 테스트를 제공해야 한다.

수용 기준:

- operation ID 중복을 탐지한다.
- tag metadata 누락과 미사용을 탐지한다.
- 204를 제외한 성공 응답의 response schema 누락을 탐지한다.
- ORM 및 Raw 예제 DTO schema가 OpenAPI에 생성된다.
- 서로 다른 모듈의 동일한 Pydantic class 이름 때문에 schema key가 모듈 경로 형태(`__`)로
  노출되지 않는다. 공개 DTO class 이름은 프로젝트 전체에서 고유하게 관리한다.
- 검사 대상 operation/schema가 0개가 되어 규칙 테스트가 공허하게 통과하지 않도록 기존 route
  inventory와 참조 예제 DTO 집합을 별도로 고정한다.
- 각 규칙은 결함 상태를 의도적으로 주입했을 때 실패하는 fail-on-revert 검증을 거친다.

### DOC-006 Passive-style 기준 문서 정합성 [P0]

`README.md`, `docs/ARCHITECTURE.md`, `docs/QUICKSTART.md`의 현재 개발 절차는 실제 App
Registry 코드와 일치해야 한다.

수용 기준:

- 신규 기능은 `apps.py`와 `config.INSTALLED_APPS`로 설치하며 `main.py`를 수정하지 않는다.
- 기능 root `__init__.py`를 Router/Model 재노출 지점으로 설명하지 않는다.
- runtime과 Alembic 모델 수집은 동일한 `INSTALLED_APPS` registry를 사용한다고 설명한다.
- `import_all_models()`와 디렉터리 스캔을 현재 절차로 안내하지 않는다.
- 과거 구조를 다룬 변경 이력은 현재 절차와 명확히 구분한다.
- `tests/test_docs_consistency.py`가 위 필수·금지 계약을 자동 검증한다.

## 13. 시나리오 요구사항

### SCN-ORM-001 상품 CRUD 예제 [P1]

ORM workflow를 설명하는 완결된 상품 CRUD 예제를 제공해야 한다.

포함 범위:

- Product ORM 모델과 migration
- create/list/get/update/delete
- ORM Repository, Service, read-only/writer DB session Dependency
- `v1/products.py`와 그룹 Router
- Pydantic 요청/응답 및 Scalar 문서
- Repository, Service, API, transaction 테스트
- `catalog_products` 실제 Alembic migration과 upgrade/downgrade 검증

### SCN-RAW-001 일별 매출 리포트 예제 [P1]

Raw workflow를 설명하는 일별 매출 집계 예제를 제공해야 한다.

`sales_orders`는 이 저장소가 migration으로 소유하는 원본 테이블이므로 결과 DTO와 별개로
`SalesOrder` ORM **스키마 모델**을 `reports/models`에 두고 App Registry가 수집하게 한다.
Repository의 조회 결과는 계속 `RowMapping`과 Pydantic DTO를 사용하며 `SalesOrder`를 조회
결과 모델로 사용하지 않는다. 이렇게 해야 기존 registry-model/metadata 동등성 및 Alembic
schema drift 검사가 유지된다. 외부 시스템 소유 테이블을 조회하는 별도 사례라면 migration과
ORM 모델을 모두 만들지 않고 외부 schema를 drift 비교에서 제외하는 정책을 별도로 선언한다.

포함 범위:

- 프로젝트 소유 원본 테이블용 `SalesOrder` 스키마 모델과 결과 전용 DTO를 분리
- 조회는 ORM entity 대신 Raw 집계 SQL과 `RowMapping` 사용
- named date parameters
- `SalesReportRawRepository`, Report Service, read-only Dependency
- Pydantic Raw 결과 DTO
- `v1/sales_reports.py`와 그룹 Router
- SQL 결과 mapping, reader routing, API, OpenAPI 테스트
- Raw 원본 `sales_orders` 실제 Alembic migration
- 새로 추가할 `compose.test.yaml`을 공유하는 로컬 및 CI MySQL 통합 테스트

### SCN-RAW-002 Raw 쓰기 검증 예제 [P1]

운영 공개 API가 아니어도 테스트 fixture에서 Raw DML workflow를 검증해야 한다.

수용 기준:

- execute 결과 row count를 검증한다.
- 쓰기 commit 1회 및 실패 응답을 검증한다.
- read-only DML 차단을 검증한다.

## 14. 비기능 요구사항

### NFR-001 보안 [P0]

- SQL injection 방지 규칙을 위반하는 Raw SQL이 없어야 한다.
- 로그와 사용자 오류 응답에 비밀번호, 토큰, 전체 SQL 파라미터를 기록하지 않는다.
- Pydantic 응답에 비공개 ORM 필드가 포함되지 않는다.

### NFR-002 성능 [P1]

- 목록 API는 무제한 조회를 허용하지 않는다.
- pagination limit 상한을 둔다.
- pagination 목록은 호출자가 정렬을 주지 않아도 PK 등 유일하고 안정적인 기본 정렬을 적용해
  같은 데이터 집합에서 페이지 중복·누락이 발생하지 않게 한다.
- ORM 관계 조회는 N+1 방지 전략을 기능 Repository에 명시한다.
- Raw 집계 쿼리는 실제 DB 실행 계획을 검토한다.
- 존재 확인은 SQL `EXISTS`를 사용한다.

### NFR-003 타입 안전성 [P1]

- ORM 모델, PK, Repository 반환 타입을 제네릭으로 검사한다.
- Raw 결과가 외부로 나가기 전에 Pydantic validation을 거친다.
- `Any`와 무검증 `dict` 반환을 Base의 공개 계약에서 최소화한다.

### NFR-004 관측성 [P1]

- Repository 오류 로그에 기능, 모델 또는 쿼리 이름을 포함한다.
- Raw SQL 전체 값과 민감 파라미터는 기록하지 않는다.
- 필요 시 느린 쿼리 관측을 위한 실행 시간을 구조화 필드로 남긴다.

### NFR-005 호환성 [P0]

- 기존 공개 API 경로, 응답 schema와 상태 코드를 의도 없이 변경하지 않는다.
- 기존 DB schema는 명시적 migration 없이 바뀌지 않는다.
- 기존 Base Repository 호출부를 점진적으로 전환한다.

### NFR-006 가용성 및 readiness [P1]

- liveness와 readiness의 역할을 분리한다.
- `/health`는 프로세스 생존 여부를 반환한다.
- `/ready`는 writer DB에서 `SELECT 1`을 실행하며 timeout은 2초다.
- 준비 완료는 200, DB 오류 또는 timeout은 503을 반환한다.
- 503 응답에 DSN과 내부 DB 오류 내용을 노출하지 않는다.
- 선택 자원의 미사용 상태를 장애로 판정하지 않는다.
- 필수 자원 startup 실패는 fail-fast한다.

### NFR-007 자원 예산 [P1]

- worker 수와 writer/read/background pool 크기를 곱한 최대 연결 수를 산정한다.
- 현재 기본값 기준 worker당 상한은 writer 40 + reader당 40 + background 20이므로
  `workers × (40 + 40 × reader_count + 20)`으로 계산한다. 예를 들어 reader 1개와 worker
  4개면 최대 400개이며 DB 예약 연결과 다른 서비스 몫을 제외한 허용치보다 작아야 한다.
- DB 서버 최대 연결 수를 넘는 설정을 배포 전에 검수한다.
- pool 크기를 코드 상수로 숨기지 않고 설정으로 이동하고 Settings validation/배포 체크에서
  산정값과 운영 한도를 비교한다.
- multi-worker 환경에서 resource manager가 worker별로 실행됨을 문서화한다.

### NFR-008 lifecycle 관측성 [P1]

- startup/shutdown 단계와 소요 시간을 구조화 로그로 기록한다.
- 발견한 모델 모듈 수와 metadata table 수를 기록한다.
- 자원별 생성·close 성공과 실패를 기록한다.
- DSN password와 secret은 로그에 기록하지 않는다.

### NFR-009 Event loop 비차단 [P0]

비동기 선택지가 있는 I/O와 장시간 CPU 작업은 요청 event loop에서 직접 실행하지 않아야
한다.

수용 기준:

- 모든 공개 FastAPI path operation이 `async def`다.
- DB I/O는 `AsyncEngine`/`AsyncSession`과 async driver를 사용한다.
- bcrypt 같은 고비용 동기 CPU 작업은 `asyncio.to_thread()` 또는 worker로 격리한다.
- Queue 기반 logging 전환은 `app/utils/logs/config.py`의 기존 ADR-019(운영 회전 파일 유지)와
  충돌하므로 ADR을 먼저 개정한 경우에만 수행한다.
- ADR 개정 시 worker별 최대 10,000건의 bounded `QueueHandler`/`QueueListener`를 사용하고
  production/staging 출력·보관 책임을 stdout/stderr 외부 collector로 이전한다.
- ADR 개정 시 Docker, Kubernetes 또는 운영 agent가 저장과 rotation을 담당한다.
- ADR 개정 시 DEBUG/INFO/WARNING은 queue 포화 시 drop하고 counter를 증가시킨다.
- ADR 개정 시 ERROR/CRITICAL은 queue 포화 시 최소 stderr fallback을 사용한다.
- ADR 개정 시 console 및 uvicorn logging도 같은 queue 출력 경로로 통합한다.
- 동기 HTTP client, `time.sleep`, 동기 subprocess, 직접 파일 I/O를 async 함수에서 사용하지
  않는다.
- 짧은 User-Agent/JWT/Pydantic 연산은 측정 근거가 있는 한 동기 실행을 허용한다.
- SQLAlchemy `AsyncConnection.run_sync()`는 동기 DB driver 사용으로 판정하지 않는다.

### NFR-010 SQL 및 migration 로깅 기밀성 [P0]

Repository가 안전하게 로그를 남겨도 SQLAlchemy·aiomysql·aiosqlite·PyMySQL 같은 하위 로거가
DEBUG/INFO에서 SQL 본문과 바인딩 값을 기록할 수 있다. 기본 `DEBUG=true`인 개발 환경도
보안 예외가 아니다.

수용 기준:

- SQL/driver 로거의 SQL 본문·bind 값 출력은 기본 비활성이고 명시적인 개발용 opt-in에서만
  허용한다. production/staging에서 opt-in이 활성화되면 startup을 실패시키거나 강제로
  비활성화한다. opt-in 경고에는 실제 개인정보·token을 사용하지 않는다.
- ADR-019의 `RotatingFileHandler`를 유지하면서 console/file/error 출력 경로 모두에 동일한
  SQL-noise/redaction 정책을 적용한다.
- 단순 logger 이름 단위 테스트뿐 아니라 실제 query에 secret canary를 bind해 모든 application
  handler와 캡처 로그에 도달하지 않는지 end-to-end로 검증한다.
- WARNING/ERROR를 보존하더라도 SQL 본문·params가 포함된 record는 redaction하거나 안전한
  요약으로 바꾼다. 장애 관측을 이유로 원문을 통과시키지 않는다.
- Repository와 전역 예외 처리기의 application logger도 DB 예외 객체를 `%s`, `exc_info` 또는
  traceback으로 포맷하면서 SQL·params를 다시 노출할 수 있다. 테스트는 `LogRecord.getMessage()`만
  보지 않고 각 ADR-019 formatter/handler가 만든 최종 문자열까지 검사한다.
- 처리되지 않은 500 응답은 DEBUG 여부와 관계없이 `str(exc)`나 traceback을 외부 detail로 반환하지
  않는다. 개발 진단 정보는 redaction을 거친 서버 로그에서만 확인한다.
- Alembic `fileConfig`는 `disable_existing_loggers=False`를 사용해 같은 프로세스에서 migration
  실행 후에도 application/Raw Repository 로그가 살아 있어야 한다.

### NFR-011 운영 보안 기본값 [P0]

현재 passive-style은 인증 없는 SQLAdmin을 제공하며 `.env.example`은 `ADMIN=true`다. 또한
예제 CORS 값은 credentials 허용과 wildcard origin을 함께 제시해 Settings validation과
충돌한다. 템플릿 사용자가 예제 설정을 복사했을 때 위험하거나 기동 불가능한 상태가 되지
않아야 한다.

수용 기준:

- production/staging의 `ADMIN` 기본값은 false이며, 인증/프록시 접근제어 없이 public bind와
  함께 활성화되지 않는다. 개발에서만 사용할 때도 “인증 없음”을 문서와 startup 경고에 표시한다.
- catalog/reports 참조 API가 인증 없는 예제라는 점을 명시하고 실제 업무 기능으로 승격할 때
  인증·인가 위협 모델을 다시 검토한다.
- `.env.example`은 `CORS_ALLOW_CREDENTIALS=true`와 `CORS_ALLOW_ORIGINS=["*"]`를 동시에 제공하지
  않으며, 예제 파일을 실제 Settings로 로드하는 테스트가 통과한다.
- DSN, password, token과 test credential은 운영 예시·로그·오류 응답에 사용하지 않는다.

### NFR-012 검증 범위와 잔여 위험 공개 [P1]

- MySQL 통합 테스트가 로컬에서 skip될 수 있더라도 CI 병합 게이트에서는 skip을 실패로 본다.
- 부하/실행계획, 실제 replica 지연, 실제 Celery worker, Scalar 브라우저 렌더링처럼 실행하지
  않은 검증은 완료 보고서의 잔여 위험에 명시한다.
- “전체 green”은 실행된 테스트만 의미하며, 인프라 미가용으로 실행되지 않은 테스트 수를
  별도로 보고한다.

## 15. 테스트 및 품질 게이트

### TEST-001 Base 단위 테스트 [P0]

ORM Base:

- CRUD primitive
- 입력 불변성
- PK 타입 및 not-found
- 예외 변환

Raw Base:

- one/all/scalar/execute 반환
- 빈 결과
- named parameter
- 예외 변환
- commit 미수행

테스트 전용 ORM 모델은 애플리케이션 `Base`가 아닌 격리된 `DeclarativeBase`에 등록한다.
그렇지 않으면 테스트 import만으로 공유 metadata에 유령 테이블이 추가되어 schema snapshot과
migration drift 검사가 순서 의존적으로 실패한다. 공통 Mixin은 격리 Base에서도 재사용해
필드 계약을 함께 검증한다.

### TEST-002 계층 및 트랜잭션 테스트 [P0]

- View가 올바른 Dependency를 사용한다.
- 조회는 writer session과 commit을 사용하지 않는다.
- 쓰기는 writer session과 응답 전 commit을 사용한다.
- Repository 및 Dependency commit을 탐지한다.
- 신규 예제를 `INSTALLED_APPS`에서 제외하면 route, model metadata, 선언된 Admin과
  `AppConfig.ready()` 효과가 모두 비활성인지 검증한다.
- 신규 예제를 등록하면 route/model/`ready()`가 활성화되고, `admin.py`를 선언한 기능만 Admin이
  활성화되며, 중복 method/path가 거부되는지 검증한다.
- read-only session에서 ORM flush, Core DML, `TextClause` DML을 각각 차단하고 routed/writer
  session에서는 허용하는지 검증한다.
- deprecated Dependency alias와 정식 이름 어느 쪽을 override해도 전환 기간의 대상 route가
  테스트 DB session을 사용하며 실제 DB로 새지 않는지 검증한다.

### TEST-003 API 통합 테스트 [P0]

- ORM/Raw 성공 응답
- 입력 validation 422
- not-found/conflict/DB 오류
- commit 실패가 2xx가 아님
- Pydantic 응답 계약

### TEST-004 전체 품질 게이트 [P0]

다음 명령이 모두 성공해야 한다.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
```

Windows CLI 회귀 테스트의 자식 Python은 `-X utf8`로 실행하고 부모는
`encoding="utf-8"`, `errors="strict"`를 유지한다. 종료 코드 `2`, 한글 오류 메시지와 생성
부작용 없음이 모두 검증되어야 하며 변경 착수 기준선은 307/307 통과다.

### TEST-005 Lifespan 자원 관리 [P0]

- 모델 0개이면 table create와 DB 연결 시도가 0회인지 검증한다.
- 모델이 있고 개발 자동 생성 정책이 켜져 있을 때 create가 1회인지 검증한다.
- 기본 registry 모델이 이미 전역 metadata에 import된 뒤에도 빈 registry app은 DB 연결 0회,
  일부 registry app은 그 registry 소유 테이블만 `tables=`로 전달하는지 검증한다.
- 운영 정책에서는 모델이 있어도 create가 0회인지 검증한다.
- startup 중 후속 자원 초기화 실패 시 앞서 준비된 자원이 해제되는지 검증한다. Queue logging을
  도입한 경우 listener 초기화 실패도 포함한다.
- 정상 shutdown의 drain/close/dispose 순서를 검증한다.
- cleanup 하나가 실패해도 나머지 cleanup이 실행되는지 검증한다.
- lifespan 재진입 후 task/engine reference 누수가 없는지 검증하고, Queue logging을 도입한 경우
  listener도 포함한다.
- shutdown 후 `app.state.resources`에 닫힌 자원 reference가 남지 않는지 검증한다.
- background task 5초, DB dispose 10초와 FastAPI 전체 20초 제한을 검증한다. Queue logging을
  도입한 경우 logging drain 5초 제한도 검증한다.
- Celery worker cleanup의 별도 10초 제한을 검증한다.

### TEST-006 비동기 runtime 회귀 [P0]

- 모든 공개 path operation이 async 함수인지 검사한다.
- async 함수에서 금지된 동기 I/O 호출을 정적 검사한다.
- ADR-019 개정 시 production/staging에 애플리케이션 file handler가 존재하지 않는지 검사한다.
- ADR-019 개정 시 worker별 queue 크기 10,000과 non-blocking `put_nowait()`를 검증한다.
- ADR-019 개정 시 저레벨 drop counter, rate limit 및 ERROR/CRITICAL stderr fallback을 검증한다.
- ADR-019 개정 시 listener startup, 정상 flush/stop, startup 실패 cleanup을 검증한다.
- drain timeout 시 pending task의 cancellation과 최종 task 집합 0개를 검증한다.
- Celery 연속 task가 동일한 살아 있는 loop를 재사용하는 기존 테스트를 유지한다.
- Celery worker shutdown 후 engine dispose, async generator shutdown, loop close를 검증한다.
- 이번 작업에서는 ADR-019를 유지하므로 기존 production/staging `RotatingFileHandler` 테스트가
  계속 통과해야 한다. Queue logging 관련 조건부 항목은 후속 ADR이 승인된 경우에만 활성화한다.

### TEST-007 오류 응답 기밀성 [P0]

- duplicate, FK, 일반 SQLAlchemy 오류와 commit 단계 오류 각각에 대해 HTTP 응답을 검증한다.
- 응답 JSON과 캡처 로그에 SQL 본문, bind 값, DSN, driver 원문이 없는지 secret canary로
  검증한다. 일반 500, Repository 변환, commit 실패, SQL/driver WARNING·ERROR를 모두 포함하고
  `getMessage()`뿐 아니라 실제 formatter가 만든 traceback 포함 최종 출력도 검사한다. 내부 원인은
  exception chaining으로 보존하되 로그에 남길 때는 안전한 예외 타입과 operation만 사용한다.
- DEBUG 모드에서도 일반 500 응답의 `detail`이 `str(exc)`를 포함하지 않는지 검증한다.
- Raw `query_name`에 사용자 입력, 허용하지 않은 문자 또는 과도한 길이를 전달하면 실행 전에
  거부되는지 검증한다.

### TEST-008 결정적 검수 게이트 [P0]

- pytest, ruff check, ruff format check, mypy, Bandit(MEDIUM 이상), 계층 불변식과 기존 공개 API
  불변 검사를 하나의 재현 가능한 게이트로 실행한다.
- Windows에서 게이트 stdout/stderr와 모든 자식 Python을 UTF-8로 고정한다. 실패 내용을
  출력할 때 인코딩 예외로 게이트 자체가 죽어 실제 결함을 가리지 않아야 한다.
- Bandit을 포함한 외부 도구의 text reporter도 UTF-8을 보장하거나 JSON 결과를 파싱한다. reporter
  인코딩 실패를 보안 검사 통과로 간주하지 않는다.
- pytest/mypy/Ruff의 temp·cache 경로는 실행별 고유 디렉터리를 사용하고 `finally`에서 정리한다.
  고정 `.pytest_tmp`/`.mypy_tmp` 재사용으로 병렬 세션이나 이전 권한이 다음 검수를 깨뜨리지 않는다.
- 실패 보고는 `stdout`과 `stderr`를 모두 보존한다. stdout이 비어 있지 않다는 이유로 실제 traceback이
  있는 stderr를 버리지 않으며, tool exit code와 실패 원인을 함께 출력한다.
- 문자열 검색 대신 AST로 상속·commit·직접 session execute 같은 계층 위반을 검사해 docstring과
  주석을 오탐하지 않는다.
- OpenAPI/계층/보안 규칙은 결함 상태를 주입했을 때 해당 검사가 실제 실패하는 fail-on-revert
  증거를 남긴다.
- 문서가 참조하는 파일 경로, 심볼, 환경변수가 실제 코드에 존재하는지 기계 검사한다.
- 전체 결과에는 실행 test 수, MySQL 실행/skip 수와 미검사 범위를 함께 기록한다.

## 16. 마이그레이션 요구사항

### MIG-001 기준선 확보 [P0]

변경 전에 다음 기준선을 확보해야 한다.

- Windows 자식 Python을 `-X utf8`로 실행한 전체 테스트 307/307 통과 결과
- ORM Base 공개 메서드와 사용처
- 현재 OpenAPI schema
- 현재 Alembic head 및 metadata/schema 비교

### MIG-002 단계적 적용 [P0]

다음 순서로 구현해야 한다.

1. Windows CLI 인코딩 기준선 복구와 307/307 전체 테스트 통과
2. ADR-019 유지 및 Queue logging 후속 분리 기록
3. README/ARCHITECTURE/QUICKSTART 정합성 복구와 문서 회귀 테스트 추가
4. Lifespan resource manager, registry 소유 table 분기 및 `/ready` 구현
5. DB session Dependency 새 이름 추가 및 callable identity를 보존한 호출부 전환
6. 모델 mixin 계약과 schema 불변 검증
7. ORM Base 내부 개선 및 호환 wrapper
8. 기존 기능 Repository 전환
9. Raw Base 추가
10. `compose.test.yaml`과 MySQL CI 검증 경로 구축
11. ORM/Raw 예제 기능 추가
12. Scalar/OpenAPI 보강
13. 오래된 session/Repository 호환 이름 제거

기존 이름과 wrapper의 호환 기간은 릴리스 횟수가 아니라 단계 완료 조건으로 관리한다. 새
API 추가, 전체 호출부 전환, 사용처 0건 확인, 전체 품질 게이트 통과를 각각 독립 커밋으로
완료한 뒤 마지막 독립 단계에서만 제거한다.

### MIG-003 롤백 가능성 [P1]

각 단계는 독립 커밋으로 구성하고 API·DB schema 변경 여부를 명시해야 한다.

수용 기준:

- Raw Base 추가가 기존 ORM 동작과 결합되지 않는다.
- 모델 mixin 전환은 schema diff가 없으면 코드 단위로 되돌릴 수 있다.
- 호환 메서드는 모든 호출부 전환 전에 제거하지 않는다.

## 17. 제외 범위

다음은 본 작업의 요구사항이 아니다.

- View에서 직접 SQL 실행
- Service에서 SQL 문자열 생성
- Repository 내부 commit
- 자동 라우터 또는 Repository discovery
- ORM과 Raw 계층을 하나의 만능 Base로 통합
- Raw 결과를 검증 없는 dict로 외부 반환
- 모든 도메인 쿼리를 `app/core`로 이동
- API Gateway 또는 캐시 계층 도입
- 요청하지 않은 공개 API 호환성 파괴
- shutdown 시 DB table 삭제
- API Redis client/cache 및 Redis를 readiness 필수 조건으로 추가하는 작업
- Celery worker 자원을 FastAPI lifespan에서 제어
- 모든 짧은 CPU 연산을 무조건 thread pool로 넘기는 변경
- JWT access/refresh token 정책, rotation, revoke/logout 또는 권한 체계 구현

## 18. 요구사항 추적표

| 구현 단계 | 주요 요구사항 |
|---|---|
| Phase 0 기준선 | AR-001~004, MIG-001, NFR-005, NFR-010~011, ORM-REP-007, DOC-006, TEST-004, TEST-008 |
| Phase 1 Async Runtime/Lifespan | AR-005~010, TX-005, NFR-006~009, TEST-005~006 |
| Phase 2 모델 기반 | ORM-MDL-001~004, MIG-002 |
| Phase 3 ORM Repository | ORM-REP-001~007, TX-001~004, SVC-001, NFR-010, TEST-001~002, TEST-007 |
| Phase 4 Raw Base | RAW-REP-001~007, NFR-001~004, NFR-010, TEST-007 |
| Phase 5 예제 | SCN-ORM-001, SCN-RAW-001~002, VIEW-001~002 |
| Phase 6 Scalar | DOC-001~006 |
| Phase 7 최종 검수 | NFR-012, TEST-003~004, TEST-008, MIG-003 |

## 19. 완료 정의

다음 조건을 모두 만족해야 작업 완료로 판정한다.

- [ ] ORM과 Raw가 동일한 계층 호출 흐름을 사용한다.
- [ ] 모든 ORM Repository가 ORM Base 계층을 사용한다.
- [ ] 모든 Raw Repository가 Raw Base 계층을 사용한다.
- [ ] 모델 공통 필드 정책이 mixin으로 적용되고 DB schema가 의도 없이 바뀌지 않는다.
- [ ] 모델이 없으면 startup이 DB table 생성을 위한 연결을 시도하지 않으며 부분 registry는
  자신이 소유한 table만 생성한다.
- [ ] resource manager가 startup 실패와 shutdown에서 모든 소유 자원을 해제한다.
- [ ] background task drain → DB engine dispose 순서가 보장된다.
- [ ] 기존 ADR-019의 production/staging `RotatingFileHandler` 동작과 테스트가 유지된다.
- [ ] drain timeout 후 pending task가 취소·await되어 추적 집합에 남지 않는다.
- [ ] Celery worker 종료 시 async DB pool과 event loop가 정상 해제된다.
- [ ] View, Dependency, Service, Repository의 책임 위반이 없다.
- [ ] read-only/writer DB session 및 commit 경계가 `TextClause` DML까지 자동 테스트로 보호된다.
- [ ] DEBUG 일반 500을 포함한 DB 오류 응답과 최종 formatter 로그가 SQL, params, DSN과 driver
  원문을 노출하지 않는다.
- [ ] `/health`와 writer DB 기반 `/ready`가 분리되고 readiness 실패는 안전한 503이다.
- [ ] Raw SQL이 named binding과 식별자 allowlist 규칙을 준수한다.
- [ ] ORM/Raw 외부 응답이 모두 Pydantic DTO로 검증된다.
- [ ] ORM 상품 CRUD와 Raw 매출 리포트 예제가 완결되어 있다.
- [ ] Scalar에서 요청·응답·오류·파라미터·태그 문서가 정확하다.
- [ ] operation ID와 tag metadata 정합성 테스트가 통과한다.
- [ ] Windows 및 CI에서 기준 테스트 307/307이 통과한다.
- [ ] 로컬과 CI가 동일한 `compose.test.yaml`로 MySQL migration/Raw SQL을 검증하고, 고정 test
  credential의 host port는 loopback에만 bind한다.
- [ ] README/ARCHITECTURE/QUICKSTART가 passive-style registry 계약과 일치한다.
- [ ] 전체 pytest, Ruff, format check, mypy와 Bandit MEDIUM 이상 게이트가 통과한다.

## 20. 확정 정책

1. UUID, created, updated 책임은 작은 Mixin으로 분리한다.
2. ORM Repository는 `BaseRepository[ModelT, PrimaryKeyT]`를 정식 계약으로 사용한다.
3. Base에는 최소 CRUD만 두고 고급 쿼리는 기능 Repository로 이동한다.
4. OpenAPI는 규칙 기반 검증을 중심으로 하고 핵심 schema만 snapshot한다.
5. `/ready`는 writer DB `SELECT 1`, 2초 timeout, 성공 200, 실패 503을 사용한다.
6. FastAPI shutdown은 task 5초, DB 10초, 전체 20초를 사용하며 Queue logging 도입 시
   logging 5초 제한을 추가한다.
7. Celery worker cleanup timeout은 별도 10초다.
8. ADR-019 개정 시 logging은 worker별 10,000건 queue와 stdout/stderr 외부 collector 방식을 사용한다.
9. ADR-019 개정 시 queue 포화 시 저레벨 로그는 drop하고 ERROR/CRITICAL은 제한된 stderr fallback을 사용한다.
10. `INSTALLED_APPS`와 App Registry 계약은 본 작업에서 제거하거나 우회하지 않는다.
11. 이번 ORM/Raw 고도화에서는 ADR-019와 기존 `RotatingFileHandler` 동작을 유지한다.
12. Queue logging과 운영 파일 handler 제거는 별도 후속 ADR 승인을 선행 조건으로 한다.
