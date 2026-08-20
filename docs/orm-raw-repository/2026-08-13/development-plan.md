# ORM/Raw Repository 고도화 설계 및 개발 작업 계획서

## 1. 목적

이 문서는 현재 프로젝트의 FastAPI 워크플로우를 유지하면서 다음 두 데이터 접근 방식을
동등한 품질로 지원하기 위한 설계와 실행 순서를 정의한다.

- SQLAlchemy ORM 모델을 사용하는 일반 CRUD
- SQL 문자열과 바인드 파라미터를 사용하는 Raw SQL 조회/변경

두 방식은 데이터 접근 구현만 달라야 한다. 라우터 취합, Dependency Injection, Service
유스케이스, 트랜잭션 경계, Pydantic 응답, OpenAPI/Scalar 문서화와 테스트 기준은 동일하다.

이 계획은 2026-08-13 passive-style 코드베이스를 기준으로 검증·보정했고, 2026-08-18에는
고도화가 완료된 `fastapi-default-project-structure`의 `db49e9c` 및 CRP 결함 원장 F-001~F-018을
추가 대조했다. default-style의 구현을 그대로 복사하지 않고 검증된 교훈을 현재 App Registry
조립 방식과 ADR-019 파일 로깅 정책에 맞게 이식한다. 기존
`INSTALLED_APPS`/`AppConfig`/`Apps` 계약을 보존한다.

## 2. 현재 코드 기준 검토 결과

### 2.1 이미 충족하는 원칙

| 원칙 | 현재 상태 | 근거 |
|---|---|---|
| 공통 인프라는 `app/core`에 둔다 | 충족 | `db`, `middlewares`, `models`, `repositories`, `services` |
| ORM 저장소가 공통 Base를 사용한다 | 충족 | 모델 보유 기능의 Repository 5개가 모두 `BaseRepository` 상속 |
| 기능별 Dependency에서 세션과 Service를 조립한다 | 충족 | `get_<feature>_service`, `get_<feature>_service_readonly` |
| 버전별 View를 그룹 라우터가 취합한다 | 충족 | `api/routers/v1/*.py` → `api/routers/router.py` |
| 설치 앱의 라우터를 registry adapter가 최종 취합한다 | 충족 | `INSTALLED_APPS` → `Apps.populate()` → `install_routers()` |
| 쓰기 커밋은 응답 전 View에서 완료한다 | 충족 | `await service.commit()` 및 회귀 테스트 |
| 조회는 reader 세션을 사용한다 | 충족 | 현재 `get_read_session` 및 라우트 배선 테스트 |
| 공개 API View는 비동기 함수다 | 충족 | 검사한 path operation 31개가 모두 `async def` |
| DB I/O는 비동기 driver/session을 사용한다 | 충족 | `AsyncEngine`, `AsyncSession`, aiomysql |
| 고비용 비밀번호 해싱은 event loop 밖에서 실행한다 | 충족 | bcrypt 전체 호출을 `asyncio.to_thread()`로 격리 |

### 2.2 보강해야 하는 항목

1. `repository_base.py`가 980줄(2026-08-13 검토 기준)이며 서로 다른 책임이 한 클래스에 집중되어 있다.
   기본 CRUD, eager loading, 부분 컬럼, join, batch, bulk, upsert를 분류하고 공개 계약을
   줄여야 한다.
2. `crud_base.py`는 네 개의 protected 메서드만 제공한다. 이름은 CRUD Base이지만 실제
   공개 CRUD 계약은 대부분 `BaseRepository`에 있어 책임 경계가 불명확하다.
3. `BaseRepository.create()`가 전달받은 `dict`에 `id`를 직접 추가한다. 호출자 데이터의
   변경을 피하고 모델 기본값에 ID 생성을 맡겨야 한다.
4. 제네릭 Base가 모든 모델에 문자열 `id`가 있다고 가정한다. 이 불변식을 타입과 모델
   상속 정책으로 명확히 강제하거나, PK 추상화를 도입해야 한다.
5. 관계와 컬럼을 문자열로 받는 고급 API는 오타를 실행 시점에만 발견한다. 기능별
   Repository가 SQLAlchemy 속성을 사용하도록 공개 API를 좁히는 편이 안전하다.
6. `exists`가 `COUNT(*)`를 사용한다. 존재 확인에는 SQL `EXISTS`가 의도와 성능에 더 맞다.
7. Bulk/update/delete의 DB 예외 변환 정책이 메서드마다 일관되지 않다.
8. 모든 기능 모델이 `Base`를 상속하지만 `UUIDMixin`, `TimestampMixin`을 실제로 사용하지
   않고 `id`, `created_at`을 반복 정의한다. `models_base.py`가 공통 모델 정책의 SSOT가
   되지 못하고 있다.
9. Raw SQL용 공통 실행 계층, 결과 타입, 예외 변환, 파라미터 바인딩 규칙과 테스트가 없다.
10. `tags_metadata.py`에는 구현 완료 기능이 여전히 “미구현/예정”으로 설명되고 `Auth`
    태그가 없다. 실제 라우터 태그와의 정합성 테스트가 필요하다.
11. 다수 Pydantic 필드에 설명은 있으나 요청/응답 예시와 상태 코드 문서 기준은 일관되지
    않다.
12. production/staging 파일 로그가 `RotatingFileHandler`에서 요청 event loop thread의
    동기 파일 write/flush/rotation으로 실행된다. console 출력도 동일한 동기 handler다.
13. `BackgroundTaskRunner.drain()`은 timeout 후 pending task를 취소하거나 다시 await하지
    않아 DB engine dispose 이후에도 task가 실행될 수 있다.
14. Celery worker의 영속 event loop와 background DB engine pool은 worker 종료 signal에서
    dispose/close되지 않는다. FastAPI lifespan은 Celery worker에서 실행되지 않는다.
15. 이 문서는 default-style에서 복사되어 App Registry, `AppConfig`, `INSTALLED_APPS`,
    `bootstrap.create_app()` 계약을 반영하지 못했다. 구현 전에 모든 조립 예시를 passive-style로
    보정해야 한다.
16. 현재 저장소에는 문서가 전제한 `compose.test.yaml`이 없다. MySQL 방언 검증을 시작하기
    전에 재현 가능한 compose 환경과 CI 실행 경로를 새로 정의해야 한다.
17. 운영 회전 파일 logging 제거는 기존 `app/utils/logs/config.py`의 ADR-019와 충돌한다.
    Queue logging은 ADR 개정 없이는 구현 범위로 확정할 수 없다.
18. `README.md`와 `docs/ARCHITECTURE.md` 일부 tree·변경 이력에는 `feature/__init__.py`의
    Router/Model 재노출과 `import_all_models()` 같은 이전 default-style 설명이 남아 있다.
    최종 문서 단계에서 현재 registry 계약과 일치하도록 함께 정리해야 한다.
19. `create_app()`은 격리 registry를 주입할 수 있지만 현재 `create_db_tables()`는 전역
    `apps`/`INSTALLED_APPS`를 다시 population하고 전역 `Base.metadata` 전체를 생성한다.
    한 프로세스에서 먼저 import된 미등록 모델이 부분 registry 앱의 DB로 새는 구조다.
20. `DatabaseRouter._is_write()`는 flush와 `UpdateBase`만 쓰기로 판별한다. textual SQL인
    `TextClause` DML은 read-only 차단을 우회할 수 있어 계획의 Raw DML 수용 기준을 현재는
    만족하지 않는다.
21. `BaseRepository`의 여러 예외 경로가 `str(e)` 또는 `str(e.orig)`를
    `AppException.detail`에 넣고 글로벌 handler가 이를 응답한다. SQL, bind 값, driver 정보
    노출 가능성이 있어 공통 안전 변환기가 필요하다.
22. `BaseService.commit()`은 SQLAlchemy 예외를 그대로 전파한다. Repository flush 이후
    commit 시점에 발생하는 제약 위반도 같은 공개 오류 계약과 기밀성 정책으로 변환해야 한다.
23. migration이 소유하는 `sales_orders`에 대응 모델이 없으면 기존 metadata 동등성 및
    migration drift 테스트와 모순된다. Raw 집계 결과 DTO와 원본 테이블 스키마 모델을
    구분해야 한다.
24. 현재 DB pool 상한은 worker당 writer 40, reader당 40, background 20으로 하드코딩되어
    있다. reader 1개·worker 4개만으로 최대 400 연결이므로 배포 전 계산만으로는 부족하고
    설정화와 상한 검증이 필요하다.
25. 현재 `/health`만 존재하며 DB readiness는 구현되어 있지 않다. `/ready` 추가는 route
    inventory/OpenAPI 변경을 포함한 명시 작업이어야 한다.
26. default 프로젝트에서는 기본 `DEBUG=true`만으로 SQLAlchemy·driver DEBUG 로그에 실행 SQL과
    bind 값이 실제 유출됐다(F-008). passive-style도 third-party logger를 root handler로
    전파하면서 별도 SQL filter가 없어 같은 위험이 있다.
27. passive `migrations/env.py`의 `fileConfig()`는 기본 `disable_existing_loggers=True`다.
    같은 프로세스에서 Alembic을 실행하면 application logger가 조용히 비활성화될 수 있다(F-009).
28. background `drain()`과 바깥 cleanup에 같은 timeout을 주면 cancel/gather 직전에 외부 timeout이
    끊어 task `finally`와 session close가 실행되지 않을 수 있다(F-001). 정상 대기와 취소 회수
    시간을 분리해야 한다.
29. MySQL의 무변경 UPDATE는 `rowcount=0`일 수 있어 이를 곧바로 “대상 없음”으로 해석하면
    존재하는 리소스의 no-op PATCH가 404가 된다. SQLite만으로는 이 차이가 드러나지 않는다.
30. metadata 기준 test cleanup은 모델에 없는 `alembic_version`을 남길 수 있다. migration
    왕복 검증은 실제 table 전체를 제거한 빈 schema fixture를 써야 한다(F-014).
31. 서로 다른 모듈의 같은 Pydantic class 이름은 Scalar/SDK에 긴 module-qualified schema key로
    노출된다(F-015). OpenAPI schema 이름의 프로젝트 전역 고유성 검사가 필요하다.
32. `ADMIN=true`가 기본이고 `/admin`에 인증이 없다. 또한 `.env.example`의 wildcard CORS와
    credentials 조합은 현재 Settings validation에 의해 거부되는 값이라, 복사 가능한 예제라는
    문서 계약과 보안 기본값을 동시에 위반한다.
33. default 구현의 Raw DML 선두 키워드 판별은 일반 DML과 `FOR UPDATE`는 막았지만 CTE DML을
    읽기로 오판하는 잔여 위험을 수용했다. passive-style은 명시적 statement intent와 미분류
    `TextClause` fail-closed로 이 한계를 승계하지 않는다.
34. MySQL 통합 테스트가 인프라 부재로 skip되면 로컬 편의에는 유용하지만 CI까지 초록으로
    보일 수 있다. 병합 게이트에서는 MySQL skip을 실패로 처리하고 실행 건수를 보고해야 한다.
35. default 구현은 DEBUG 모드의 일반 500 응답에 `str(exc)`를 넣는다. Repository 밖에서 발생한
    SQLAlchemy·driver 예외는 SQL, bind 값과 내부 경로를 HTTP 응답으로 노출할 수 있으므로 일반
    500 detail은 환경과 무관하게 불투명해야 한다.
36. default ORM Repository는 안전한 응답 detail과 달리 application logger에 DB 예외 객체를
    `%s`로 전달한다. `SqlNoiseFilter`는 application logger를 통과시키므로 formatter가 SQL과
    params를 다시 출력할 수 있다. canary 검사는 record message가 아니라 traceback을 포함한 최종
    handler 출력까지 확인해야 한다.
37. default `compose.test.yaml`의 `3308:3306`은 고정 test credential의 MySQL을 모든 host
    interface에 노출한다. passive-style은 loopback bind를 기본으로 하고 CI에서는 service network를
    우선한다.
38. Bandit text reporter는 Windows cp949에서 비 ASCII finding 문맥을 출력하다 실패할 수 있다.
    보안 게이트는 자식 stdio를 UTF-8로 고정하거나 JSON reporter를 사용하고 reporter 실패를
    통과로 처리하지 않아야 한다.
39. default `review_gate.py`는 고정 `.pytest_tmp`/`.mypy_tmp`를 재사용하고 실패 detail을
    `stdout or stderr`로 선택한다. 병렬 실행·잔류 권한 때문에 tool이 실패할 수 있고 stdout이 한 줄이라도
    있으면 실제 stderr traceback이 숨겨진다. 실행별 고유 temp/cache와 양쪽 스트림 보고가 필요하다.

## 3. 워크플로우 해석 보정

요청 원칙 8번의 “비즈니스 코드는 View에서 실행한다”는 다음과 같이 해석한다.

> View가 주입받은 Service의 비즈니스 유스케이스를 호출해 실행한다. 비즈니스 규칙 자체는
> Service에 작성하고, SQL은 Repository에만 작성한다.

비즈니스 규칙을 View 본문에 직접 작성하면 현재 프로젝트의 계층 계약과 테스트 가능성이
무너진다. View의 책임은 아래로 제한한다.

- HTTP 입력 수신 및 FastAPI 파라미터 선언
- 주입된 Service 유스케이스 호출
- 쓰기 성공 시 응답 전 `await service.commit()`
- ORM 또는 Raw 결과를 Pydantic 응답으로 변환
- HTTP 상태, 응답 모델, 오류 응답 및 OpenAPI 메타데이터 선언

## 4. 목표 아키텍처

```text
HTTP Request
  -> versioned View
  -> FastAPI Dependency
       -> 현재 get_session/get_read_session
       -> 목표 get_writer_db_session/get_read_only_db_session
       -> ORM Service 또는 Raw Service 구성
  -> Service: 비즈니스 유스케이스
  -> Repository: 데이터 접근
       -> BaseRepository -> CRUDBase              (ORM)
       -> RawRepositoryBase -> RawCRUDBase         (Raw SQL)
  -> AsyncSession / DatabaseRouter
  -> Pydantic Response DTO
  -> OpenAPI JSON
  -> Scalar

Application assembly
  -> config.INSTALLED_APPS
  -> Apps.populate(config -> models -> ready)
  -> app/core/apps/wiring.py::install_routers
  -> FastAPI
```

JWT는 프로젝트의 향후 기본 인증 방식이지만 이번 작업에서는 신규 적용하거나 확장하지
않는다. 기존 인증 동작의 회귀만 보호하며 token rotation, revoke/logout과 권한 정책은 별도
후속 작업으로 분리한다.

### 4.1 공통 불변식

- View는 `AsyncSession`을 직접 받거나 SQL을 실행하지 않는다.
- Service는 SQL을 작성하지 않는다.
- Repository는 HTTP 객체와 Pydantic 응답 모델을 알지 않는다.
- Base Repository는 `commit()`하지 않고 필요한 경우 `flush()`만 수행한다.
- GET/HEAD 조회는 `get_read_only_db_session`, 쓰기 또는 조회 후 쓰기는
  `get_writer_db_session`을 사용한다.
- 쿼리 종류에 따른 동적 라우팅이 반드시 필요한 승인된 경로에서만
  `get_routed_db_session`을 사용한다.
- SQLAlchemy 세션을 나타내는 Dependency 인자와 애플리케이션 계층 속성은
  `db_session`으로 명명한다.
- 쓰기 View는 성공 응답을 만들기 전에 정확히 한 번 커밋한다.
- Raw SQL은 반드시 `sqlalchemy.text()`와 named bind parameter를 사용한다.
- 테이블명, 컬럼명, 정렬 방향처럼 바인딩할 수 없는 식별자는 사용자 입력을 직접
  보간하지 않고 코드 allowlist로 선택한다.
- Raw 결과는 `RowMapping`을 Service에서 Pydantic DTO로 검증해 반환한다.

## 5. ORM Base 재설계

### 5.1 `models_base.py`

확정 공통 모델 계층은 다음과 같다.

```python
class Base(DeclarativeBase): ...

class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(...)

class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(...)

class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(...)

class UUIDTimestampModel(
    Base,
    UUIDPrimaryKeyMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
):
    __abstract__ = True

class UUIDCreatedModel(Base, UUIDPrimaryKeyMixin, CreatedAtMixin):
    __abstract__ = True
```

정책은 작은 Mixin 분리로 확정한다. 변경 가능한 엔티티는 `UUIDTimestampModel`, 접속 로그
같은 불변 모델은 `UUIDCreatedModel`을 사용한다. 외부 PK 모델은 시간 Mixin만 조합한다.
Mixin 전환 후 기존 schema diff가 없어야 한다.

### 5.2 `crud_base.py`

ORM 인스턴스의 최소 영속성 primitive만 담당한다.

```text
CRUDBase[ModelT]
  session
  model
  _get(pk)
  _add(entity)
  _delete(entity)
  _flush()
  _refresh(entity)
```

`_update()`가 `_add()`를 그대로 호출하는 현재 구조는 의미가 불명확하므로 제거하거나
명시적인 `flush/refresh`로 바꾼다. `commit/rollback`은 두지 않는다.

### 5.3 `repository_base.py`

일반 ORM Repository가 공통으로 쓸 안정적인 공개 API만 둔다.

```text
BaseRepository[ModelT, PrimaryKeyT]
  create(data)
  get_by_id(pk)
  get_by_id_or_raise(pk)
  list(offset, limit)
  count(filters)
  exists(filters)
  update_by_id(pk, changes)
  delete_by_id(pk)
```

PK 제네릭은 정식 계약으로 도입한다. 현재 문자열 UUID Repository도
`BaseRepository[ModelT, str]`을 명시하며 정수·외부 PK 모델을 허용한다.

공개 Base API는 위의 최소 CRUD로 확정한다. eager loading, join, partial column, batch와
aggregation은 기능별 Repository로 이동하고, 두 개 이상의 실제 기능에서 같은 구현이
확인된 경우에만 별도 Mixin으로 추출한다.

호환성을 위해 기존 공개 메서드를 즉시 삭제하지 않는다. 사용처와 테스트를 먼저 조사하고
deprecated wrapper → 호출부 전환 → 제거 순서로 진행한다.

목록 메서드는 pagination 재현성을 위해 호출자가 정렬을 주지 않아도 유일한 PK를 마지막
정렬 키로 사용한다. 또한 현재 구현의 `detail={"error": str(e.orig)}`/`str(e)`는 글로벌
`AppException` handler를 통해 그대로 응답될 수 있으므로 제거한다. ORM과 Raw가 공유하는
작은 DB 예외 변환기는 공개 detail에는 model/query/공개 error code만 넣고 내부 원인은
`raise ... from e`와 SQL/params 없는 `logger.exception()`으로만 보존한다. Repository의
flush뿐 아니라 `BaseService.commit()`에서 발생한 오류도 같은 정책으로 변환한다.

## 6. Raw SQL Base 설계

### 6.1 `raw_crud_base.py`

SQL 실행 primitive와 결과 형태 변환만 담당한다.

```python
class RawCRUDBase:
    def __init__(self, db_session: AsyncSession) -> None: ...

    async def _fetch_one(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> RowMapping | None: ...

    async def _fetch_all(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Sequence[RowMapping]: ...

    async def _fetch_scalar(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Any: ...

    async def _execute(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> int: ...
```

설계 제약:

- 입력은 문자열이 아니라 사전에 만든 `TextClause`를 기본으로 한다.
- 반환은 ORM 객체가 아닌 `RowMapping`, scalar, affected row count다.
- SQL을 임의로 조합하는 public `execute(sql: str)` 만능 메서드는 제공하지 않는다.
- 예외를 삼키거나 커밋하지 않는다.

### 6.2 `raw_repository_base.py`

Raw Repository의 공통 정책을 담당한다.

```text
RawRepositoryBase -> RawCRUDBase
  fetch_one(..., *, query_name)
  fetch_all(..., *, query_name)
  fetch_scalar(..., *, query_name)
  execute(..., *, query_name)
  DatabaseException 변환
  공통 로깅(쿼리 이름, 소요 시간; 민감 파라미터 제외)
```

도메인 SQL은 Base 파일에 넣지 않는다. 기능별 Repository가 안정적인 상수 형태의 쿼리
이름과 SQL을 소유하고 Base에 `query_name`을 명시적으로 전달한다.

`query_name`은 요청값이 아니라 코드 상수이며 `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`와
같은 제한된 형식 및 길이 상한을 Base에서 검증한다. SQL 본문과 params는 성공·실패 로그 어느
쪽에도 기록하지 않는다. 또한 read-only 세션의 현재 router는 `TextClause` DML을
`UpdateBase`로 인식하지 못하므로 Raw Base가 각 statement에 `read`/`write` execution intent를
붙이고 router가 이를 우선 판정한다. `fetch_*`는 read, `execute`와 `SELECT ... FOR UPDATE`는
write다. intent가 없는 `TextClause`는 reader로 보내지 않는 fail-closed 정책을 사용한다.
default 구현의 선두 키워드 방식처럼 CTE DML을 오판하는 잔여 위험을 승계하지 않는다.
Raw Base가 private `_READ_ONLY` key를 복제하지 않도록 router에 공개
`is_read_only_session(db_session)` helper를 추가한다.

```python
class SalesReportRawRepository(RawRepositoryBase):
    async def daily_summary(self, start: date, end: date):
        stmt = text("""SELECT ... WHERE created_at >= :start AND created_at < :end""")
        return await self.fetch_all(
            stmt,
            {"start": start, "end": end},
            query_name="sales_report.daily_summary",
        )
```

## 7. 시나리오 기반 예제 범위

### 7.1 ORM 시나리오: 상품 카탈로그 CRUD

- `Product` ORM 모델
- 생성, 목록, 단건, 부분 수정, 삭제
- `ProductRepository(BaseRepository[Product, str])`
- `ProductService`
- read-only/writer DB session Dependency 분리
- `v1/products.py`와 그룹 `router.py`
- Scalar 요청/응답 및 오류 문서
- Repository 단위 테스트, Service 테스트, API 통합 테스트, 트랜잭션 테스트

### 7.2 Raw 시나리오: 일별 매출 리포트

- 이 저장소가 migration으로 소유할 `sales_orders`에는 `SalesOrder` ORM 스키마 모델을 두되,
  집계 결과용 ORM 모델은 만들지 않음
- `SalesReportRawRepository(RawRepositoryBase)`
- named parameter가 적용된 집계 SQL
- `SalesReportService`
- read-only Dependency
- `v1/sales_reports.py`와 동일한 그룹 `router.py`
- `DailySalesItem`, `DailySalesReportResponse` Pydantic DTO
- SQL injection 방지, mapping 변환, reader routing, API 계약 테스트

이 구분은 현재 `tests/core/test_alembic_metadata.py`의 “registry 모델 집합 = Base.metadata”와
`tests/core/test_migration_chain.py`의 “migration schema = metadata” 계약을 지키기 위해
필수다. migration만으로 `sales_orders`를 추가하면 extra table drift로 실패한다. 반대로 외부
소유 주문 테이블을 예제로 선택한다면 migration/ORM 모델을 모두 제외하고 별도 drift 제외
정책을 먼저 설계해야 하므로, 이 계획은 프로젝트 소유 테이블 방식을 채택한다.

### 7.3 Raw 쓰기 보조 시나리오

Raw 조회만 구현하면 트랜잭션 규칙이 검증되지 않는다. 별도 테스트 fixture에서 Raw update를
한 건 포함해 다음을 검증한다.

- Repository는 flush/execute까지만 수행
- 쓰기 View가 정확히 한 번 커밋
- 예외 시 commit 없음
- read-only 세션에서 DML 실행 시 `ReadOnlyRoutingError`

## 8. Scalar/OpenAPI 문서 기준

ORM 모델은 DB 매핑 정보이며 Scalar의 직접 계약이 아니다. 문서 계약은 다음 순서로 관리한다.

1. View: `summary`, `description`, 고유 `operation_id`, `response_model`, `responses`, 상태 코드
2. Path/Query/Header: 설명, 제약, 예시
3. Pydantic 요청/응답: `Field` 설명·제약·예시, `json_schema_extra`
4. Router: 실제 `tags=[...]`
5. `tags_metadata.py`: 태그 설명과 표시 순서
6. 보안 적용 시 FastAPI `Security` 스키마

ORM 컬럼의 comment/info는 DB와 내부 개발 문서에는 유용하지만 Pydantic 응답 문서를
대체하지 않는다. Raw 결과도 Pydantic DTO가 없으면 안정적인 OpenAPI 계약을 만들 수 없다.

추가 자동 검증:

- 모든 API operation에 고유 `operationId`가 있는지 검사
- 라우터 태그와 `tags_metadata` 집합 비교
- 모든 2xx 응답에 `response_model`이 있는지 검사(204 제외)
- 주요 요청/응답 스키마에 예시가 있는지 검사
- 규칙 기반 OpenAPI contract 검사와 상품·매출 핵심 schema snapshot

## 9. Lifespan 및 애플리케이션 자원 관리 설계

### 9.1 현재 상태와 보강 필요성

현재 `app/core/bootstrap.py`의 `lifespan`이 다음 작업을 직접 수행한다.

- `DEBUG=True`일 때 `create_db_tables()` 실행
- 종료 시 `access_log_tasks.drain()`
- writer, reader, background DB engine dispose

DB 엔진은 `app/core/db/session.py` import 시 생성되며 실제 연결은 pool이 처음 사용될 때
열린다. FastAPI API 프로세스가 소유한 Redis client는 현재 없다. Redis API client/cache와
readiness 연계는 JWT와 함께 후속 작업으로 분리한다. 현재 Celery broker/backend에 사용되는
Redis 설정은 기존 동작으로 유지하며 Celery worker 프로세스가 관리한다.

보강할 문제는 다음과 같다.

1. 모델이 하나도 없어도 `create_all()` 경로가 DB 연결을 시도할 수 있다.
2. startup 중간 실패 시 이미 생성된 자원의 정리가 하나의 경로로 보장되지 않는다.
3. 백그라운드 태스크 drain과 DB 종료 순서를 하나의 계약으로 관리해야 한다.

### 9.2 단순한 목표 구조

일반적인 FastAPI `asynccontextmanager` 패턴을 사용한다. 이미 존재하는 `Apps`/`AppConfig`
registry는 설치 앱의 SSOT로 유지하며 별도의 범용 plugin registry는 만들지 않는다.

```text
bootstrap.lifespan
  -> async with manage_application_resources(app)
       startup
         1. ApplicationResources를 app.state.resources에 저장
         2. create_app()에서 population된 registry 상태 확인
         3. app.state.app_registry가 소유한 모델의 table 목록 계산
         4. 개발 자동 생성 정책 ON + 소유 table 1개 이상이면 해당 tables만 create_all
       yield
       shutdown/failure cleanup
         1. 신규 요청 종료 후 in-flight background task drain
         2. DB writer/reader/background engine dispose
```

권장 파일은 하나만 추가한다.

```text
app/core/resources.py
  ApplicationResources
  manage_application_resources(app)
```

목표 인터페이스:

```python
@dataclass(slots=True)
class ApplicationResources:
    table_count: int = 0


@asynccontextmanager
async def manage_application_resources(
    app: FastAPI,
) -> AsyncIterator[ApplicationResources]:
    resources = ApplicationResources()
    app.state.resources = resources
    try:
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(dispose_engine)

            registry = app.state.app_registry
            owned_tables = list(dict.fromkeys(model.__table__ for model in registry.get_models()))
            resources.table_count = len(owned_tables)
            if app_settings.DEBUG and resources.table_count > 0:
                await create_registered_tables(owned_tables)

            # 마지막 등록이므로 shutdown에서 DB보다 먼저 drain된다.
            cleanup.push_async_callback(access_log_tasks.drain)
            yield resources
    finally:
        # 닫힌 client를 다음 lifespan/test가 재사용하지 않도록 참조도 제거한다.
        app.state.resources = None
```

이번 작업에서는 ADR-019를 유지하므로 위 Resource Manager가 QueueListener를 생성하거나
종료하지 않는다. 후속 ADR에서 Queue logging이 승인되면 listener callback을 DB dispose보다
먼저 등록해 실제 shutdown에서는 background drain → DB dispose → listener flush/stop 순서가
되도록 확장한다.

`app/core/bootstrap.py`의 lifespan은 조립만 담당하고 `main.py`는 계속 `create_app()` 호출만
유지한다.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app):
        yield
```

실제 구현에서는 `create_db_tables()` 내부의 `apps.populate()` 호출을 제거하거나
`create_registered_tables()`로 책임을 분리한다. 모델 준비는 `create_app()`의
`app_registry.populate()`만 담당하며 같은 startup에서 population을 두 번 수행하지 않는다.

### 9.3 테이블 생성 정책

모델 존재 여부는 파일 존재나 프로세스 전역 `Base.metadata.tables` 개수가 아니라, 현재
`app.state.app_registry.get_models()`가 소유한 실제 table 목록으로 판정한다.
`Base.metadata`는 한 번 import된 모델을 프로세스 동안 보존하므로 격리 registry를 주입한
테스트/앱에서 전체 metadata를 사용하면 미등록 테이블이 새 DB에 생성될 수 있다.

```text
table_count == 0
  -> DB 연결과 create_all을 시도하지 않음

table_count > 0 and DEBUG == true
  -> Base.metadata.create_all(tables=owned_tables) 시도

table_count > 0 and DEBUG == false
  -> create_all 금지, Alembic migration 사용
```

운영에서 무조건 `create_all()`을 실행하지 않는다. `create_all()`은 기존 컬럼 변경과 삭제를
마이그레이션하지 못하며 migration history를 대체하지 못한다. 향후 `DEBUG`와 문서 활성화의
결합을 해제할 경우 `DB_CREATE_TABLES_ON_STARTUP` 같은 명시 설정으로 분리하되 운영 기본값은
`false`로 한다.

### 9.4 자원 소유권과 종료 의미

Resource Manager는 FastAPI API 프로세스가 만든 장기 수명 자원만 관리한다.

| 자원 | 소유자 | lifespan 책임 |
|---|---|---|
| writer/read/background DB engine | FastAPI process | 모든 pool dispose |
| in-flight access log task | FastAPI process | 외부 연결 종료 전에 drain |
| logging queue/listener | FastAPI process | ADR-019 개정 시에만 생성하고 마지막 flush/stop |
| 요청별 AsyncSession | Dependency | 요청 종료 시 close/rollback |
| Celery broker/backend connection | Celery worker | FastAPI에서 관리하지 않음 |
| SQLAdmin | FastAPI app | 별도 네트워크 client가 없으면 close 없음 |

DB engine 객체와 sessionmaker 정의는 기존 Dependency 및 SQLAdmin 호환을 위해
`app/core/db/session.py`에 유지할 수 있다. 단, engine pool의 shutdown 소유자는 Resource
Manager 하나로 고정하고 다른 모듈이 별도 lifespan cleanup을 등록하지 않는다.

“자원 삭제”는 연결, pool, task 및 listener reference를 해제한다는 뜻이다. shutdown에서
DB table을 drop하지 않는다.

### 9.5 실패와 종료 정책

- 필수 자원 초기화 실패는 startup 실패로 처리한다.
- 선택 자원은 명시적 설정과 기능 요구가 있을 때만 생성한다.
- startup 중간 실패도 `finally` cleanup을 반드시 실행한다.
- background task를 먼저 drain하고 DB를 dispose한다. ADR-019 개정으로 Queue logging을
  도입한 경우 logging queue/listener를 마지막에 flush/stop한다.
- `AsyncExitStack`에 cleanup을 원하는 종료 순서의 역순으로 등록한다.
- 각 cleanup 실패는 로깅하되 ExitStack의 뒤 callback cleanup을 건너뛰지 않도록 구현한다.
- FastAPI shutdown은 background task 5초, DB dispose 10초, 전체 20초 timeout을 사용한다.
  Queue logging 도입 시 logging drain 5초를 추가하며 Celery worker cleanup은 별도
  프로세스에서 10초를 사용한다.
- background task의 정상 대기는 바깥 5초보다 짧게(기본 4초) 두고 남은 시간을 pending
  cancel + gather에 사용한다. 내부와 외부 timeout을 같은 값으로 두지 않는다.
- 같은 프로세스에서 lifespan은 1회 실행을 기본으로 하되 테스트에서 startup/shutdown
  재진입 후 누수가 없는지 확인한다.
- cleanup 후 `app.state.resources`의 닫힌 client 참조를 제거한다.
- multi-worker 배포에서는 worker마다 독립적인 pool/client가 생성·해제됨을 문서화한다.

### 9.6 추가 보강 워크플로우

1. **Liveness와 readiness 분리**: `/health`는 외부 연결을 검사하지 않는다. `/ready`는
   writer DB에서 `SELECT 1`을 최대 2초 안에 실행하며 성공 시 200, 오류·timeout 시 내부
   정보를 숨긴 503을 반환한다. Redis는 후속 도입 시 별도 정책으로 추가한다.
2. **선택 자원 명시화**: 설정만 존재한다는 이유로 연결하지 않는다. API 코드가 실제로
   사용하는 자원만 startup에서 생성한다.
3. **자원 접근 방식 통일**: 장기 수명 client는 `app.state.resources`에 두고 Dependency로
   제공한다. 기능 모듈에서 새 전역 client를 만들지 않는다.
4. **startup에서 장시간 업무 금지**: migration, 대량 seed, 캐시 warm-up은 배포 job으로
   분리한다. lifespan에는 짧고 결정적인 초기화만 둔다.
5. **설정 검증 선행**: URL, pool 수, 필수 secret과 환경 조합은 네트워크 연결 전에
   Pydantic Settings에서 fail-fast한다.
6. **자원 예산 검수**: worker 수 × writer/read/background pool 크기를 계산해 DB 최대
   연결 수를 넘지 않도록 배포 문서에 명시한다.
7. **관측성**: startup/shutdown 단계, 모델/테이블 수, 자원별 성공·실패·소요 시간을
   구조화 로그로 남기고 secret/DSN password는 기록하지 않는다.
8. **연결 예산**: 현재 하드코딩 값은 worker당 writer 40 + reader당 40 + background 20이다.
   최대치는 `workers × (40 + 40 × reader_count + 20)`이며 reader 1개·worker 4개면 400개다.
   이를 설정으로 이동하고 DB 예약분 및 타 서비스 사용량을 뺀 허용 한도와 배포 전에 비교한다.
9. **Readiness 구현**: `/health`는 그대로 외부 I/O 없는 liveness로 유지하고 `/ready`는 writer
   engine에서 `SELECT 1`을 `asyncio.timeout(2)` 안에 실행한다. timeout/DB 오류는 원인을
   숨긴 503으로 변환하며 route inventory와 OpenAPI 기대값도 의도적으로 갱신한다.

### 9.7 비동기 실행 모델 검수 및 보강

비동기 적용 기준은 “모든 함수를 `async def`로 만든다”가 아니다. 다음과 같이 분류한다.

| 작업 | 현재 판정 | 목표 |
|---|---|---|
| FastAPI View/Dependency/Service | async 충족 | 유지 |
| ORM DB I/O | async 충족 | 유지 |
| bcrypt | thread offload 충족 | 유지 |
| User-Agent 파싱 | 짧은 CPU 작업 | 동기 유지, 성능 회귀 시 재측정 |
| JWT/Pydantic/모델 변환 | 짧은 CPU 작업 | 동기 유지 |
| `run_sync(create_all)` | SQLAlchemy async bridge | 유지 |
| API/uvicorn 로그 출력 | 동기 I/O | ADR-019 개정 시 queue worker로 분리 |
| access log background task | async이나 timeout cleanup 불완전 | cancel + await 보강 |
| Celery task | worker 계약은 sync, 내부 DB는 async | worker shutdown cleanup 추가 |

#### Queue 기반 non-blocking logging

이 절 전체는 ADR-019 개정이 승인된 경우에만 적용하는 조건부 설계다. 승인 전에는 현재
`RotatingFileHandler`와 관련 테스트를 유지한다.

Python 표준 logging handler에는 await 기반 파일 API가 없다. `aiofiles`로 custom handler를
만들기보다 일반적으로 사용하는 `QueueHandler`/`QueueListener` 패턴을 적용한다.

```text
request event loop
  -> QueueHandler.emit(record)       # 메모리 queue 적재
  -> QueueListener thread
       -> stdout/stderr StreamHandler
       -> container/runtime log collector
```

구현 원칙:

- 애플리케이션의 root logger에는 `QueueHandler`만 연결한다.
- stdout/stderr handler는 `QueueListener`가 소유한다.
- 가능한 범위에서 uvicorn logger도 같은 queue 기반 출력 경로를 사용한다.
- listener는 Resource Manager startup에서 시작하고 shutdown에서 stop/flush한다.
- listener stop은 background task drain과 DB dispose가 끝난 후 마지막에 수행한다.
- listener의 flush/join은 `asyncio.to_thread()`로 event loop 밖에서 실행한다.
- worker별 queue 크기는 10,000건이며 `put_nowait()`만 사용한다.
- 포화 시 DEBUG/INFO/WARNING은 drop하고 counter와 rate-limited 관측 신호를 남긴다.
- 포화 시 ERROR/CRITICAL은 logging API를 재호출하지 않는 최소 stderr fallback을 사용한다.
- 정상 shutdown queue drain timeout은 5초다.
- logging thread 실패가 API 요청 실패로 전파되지 않도록 별도 오류 보고 경로를 둔다.

#### Logging queue 포화 정책

bounded queue가 가득 찼을 때의 선택지는 다음과 같다.

| 정책 | 장점 | 위험 |
|---|---|---|
| producer block | 로그 유실 최소화 | 요청 event loop가 멈춰 API latency와 가용성 저하 |
| 전 레벨 drop | 가장 단순하고 non-blocking | 장애 시 ERROR/CRITICAL까지 유실 |
| 레벨별 처리 | 일반 로그는 non-blocking, 오류 로그 보존 | fallback과 metric 구현 필요 |

적용 정책은 `put_nowait()` 기반 레벨별 처리로 확정한다. queue 포화 시
DEBUG/INFO/WARNING은 drop하고 누적 counter와 rate-limited metric을 남긴다.
ERROR/CRITICAL은 logging API를 다시
호출하지 않는 최소 포맷의 제한된 stderr fallback으로 기록해 재귀 logging을 방지한다.
fallback도 무기한 block해서는 안 된다.

목표 후보는 stdout/stderr와 외부 collector 방식이다. 다만 현재 저장소는 ADR-019에서
production/staging의 `RotatingFileHandler` 유지를 확정하고 관련 테스트도 이를 보호한다.
따라서 ADR-019를 먼저 개정한 경우에만 애플리케이션 파일 handler를 제거하고 Docker,
Kubernetes 또는 운영 agent에 저장·검색·rotation을 이관한다. 개정 후 각 worker는 독립
queue/listener를 가진다.

#### Background task timeout 처리

`drain()`은 timeout 후 남은 task를 그대로 두지 않는다.

```python
done, pending = await asyncio.wait(tasks, timeout=timeout)
for task in pending:
    task.cancel()
await asyncio.gather(*pending, return_exceptions=True)
```

완료 후 `_tasks`가 비어 있어야 하며, cancellation 중 session context가 rollback/close될
기회를 갖도록 취소한 task를 반드시 await한다. 그 다음 DB engine을 dispose한다.

#### Celery worker async bridge 종료

Celery task 함수가 동기인 것은 framework 실행 계약이므로 유지한다. 대신 process별 영속
event loop와 해당 loop에서 사용한 DB pool을 Celery worker signal로 정리한다.

```text
worker process init
  -> event loop는 첫 async task에서 lazy 생성

worker process shutdown
  -> loop.run_until_complete(dispose background worker resources)
  -> loop.run_until_complete(loop.shutdown_asyncgens())
  -> loop.close()
  -> global loop reference = None
```

FastAPI Resource Manager와 Celery worker cleanup은 서로 다른 프로세스 소유권이다. 공통
cleanup primitive는 재사용할 수 있지만 FastAPI lifespan에서 Celery 자원을 직접 닫지 않는다.

### 9.8 DB Session Dependency 명명 규칙

SQLAlchemy `AsyncSession`을 제공하는 함수는 일반적인 사용자 세션이나 HTTP 세션과
구분되도록 이름에 `db_session`을 포함한다.

| 현재 이름 | 목표 이름 | 계약 |
|---|---|---|
| `get_read_session` | `get_read_only_db_session` | 조회 전용 의도, router 활성 시 쓰기 차단 및 reader 선택 |
| `get_write_session` | `get_writer_db_session` | 첫 쿼리부터 primary writer에 고정 |
| `get_session` | `get_routed_db_session` | 구문에 따른 동적 reader/writer 선택이 필요한 예외 경로 |
| `get_background_session` | `get_background_db_session` | FastAPI DI에서 background 전용 pool 제공 |

요청 밖 async context manager인 `background_session()`도
`background_db_session()`으로 맞춘다. Dependency 인자, Service 및 Repository 생성자와
속성은 `session` 대신 `db_session`/`self.db_session`을 사용한다. SQLAlchemy 내부처럼
문맥이 완전히 명확한 짧은 지역 변수만 `session`을 허용한다.

기존 함수명은 즉시 삭제하지 않는다. 새 이름을 정식 API로 추가한 뒤 기존 이름을 deprecated
alias로 유지하고, 전체 호출부와 테스트 전환 후 별도 호환성 제거 단계에서 삭제한다.

FastAPI의 `dependency_overrides`는 callable identity를 키로 사용한다. 따라서 호환 별칭은
가능하면 `get_session = get_routed_db_session` 같은 직접 대입으로 동일 객체를 가리키게 한다.
경고를 위한 wrapper를 사용해야 한다면 기존/신규 이름별 override가 어느 route에 적용되는지
회귀 테스트를 먼저 추가하고 모든 route fixture를 같은 단계에서 전환한다.

## 10. 개발 단계

### 10.1 선행 이슈 해결 계획

ORM/Raw 구현은 아래 네 항목을 먼저 처리한 뒤 시작한다. 각 항목은 단순 참고 사항이 아니라
다음 단계 진입을 막는 품질 게이트다.

#### A. Windows CLI stderr UTF-8 기준선 복구

현재 `tests/scripts/test_new_app.py::test_cli_rejects_bad_name_with_nonzero_exit`는 부모
프로세스에서 `encoding="utf-8"`, `errors="strict"`를 사용하지만 자식 Python은 Windows 기본
stdio 인코딩으로 한글 stderr를 출력한다. CLI의 거부 동작과 종료 코드 `2`는 정상이고 자식과
부모의 인코딩 계약만 불일치한다.

처리 방법:

1. 테스트의 자식 명령을 `[sys.executable, "-X", "utf8", "-m", "scripts.new_app", ...]`로
   변경해 자식 stdout/stderr도 UTF-8로 고정한다.
2. 부모의 `encoding="utf-8"`, `errors="strict"`는 유지해 잘못된 바이트를 조용히 대체하지
   않는다.
3. 종료 코드 `2`, stderr의 `오류`, 대상 디렉터리 미생성을 함께 검증한다.
4. 해당 단일 테스트 후 전체 pytest를 실행한다.

완료 게이트: Windows 로컬과 CI에서 307개 테스트가 모두 통과하며 깨진 대체 문자에 의존하는
assert가 없다. 테스트 수가 변경되면 고정 숫자 대신 해당 commit의 실제 수집 결과를 기준선
기록에 남긴다.

#### B. ADR-019와 Queue logging 처리

이번 ORM/Raw 고도화에서는 ADR-019를 **유지**한다. 즉 production/staging의 console 및
`RotatingFileHandler` 계약과 `tests/utils/test_logs.py`를 변경하지 않는다. Queue logging은
Repository 고도화의 필수 조건이 아니며 기존 운영 정책을 바꾸는 별도 아키텍처 결정이므로
후속 ADR 과제로 분리한다.

이번 작업에서 수행할 범위:

- Resource Manager는 access-log task drain과 writer/read/background DB engine dispose를
  관리한다.
- `BackgroundTaskRunner.drain()`의 timeout 후 cancel + await와 Celery worker loop/pool
  cleanup은 logging 변경과 독립적으로 구현한다.
- `ApplicationResources`에 사용하지 않는 QueueListener를 만들지 않는다.
- shutdown 기본 순서는 background task drain → DB engine dispose다.

후속 ADR에서 Queue logging을 승인할 때만 수행할 범위:

- bounded `QueueHandler`/`QueueListener`, queue 크기 10,000, `put_nowait()`
- 레벨별 drop/fallback, drop counter, 5초 flush timeout
- application file handler 제거와 외부 collector 운영 책임 확인
- shutdown 마지막 단계에 listener flush/stop 추가
- `tests/utils/test_logs.py`와 운영 문서 동시 개정

완료 게이트: 본 작업의 코드·테스트·문서가 파일 handler 유지 정책과 모순되지 않으며,
Queue logging 구현이 섞여 들어오지 않는다.

#### C. MySQL 통합 테스트 환경 신설

현재 저장소에는 `compose.test.yaml`이 없으므로 “기존 구성 재사용”이 아니라 예제 migration
착수 전 새로 만든다.

필수 산출물:

- root `compose.test.yaml`: 고정된 MySQL 8.4 image, test 전용 database/user/password,
  `utf8mb4` 설정, healthcheck, `127.0.0.1:${MYSQL_TEST_PORT:-3308}:3306`, tmpfs 또는 삭제 가능한
  test volume. CI에서는 host publish 없이 service network 접근을 우선한다.
- `pyproject.toml`: MySQL 전용 테스트를 구분할 `mysql` pytest marker 등록
- MySQL 8.4 `caching_sha2_password` 접속을 위한 `cryptography` dependency
- test 설정: 운영 DSN을 재사용하지 않고 test 전용 `ALEMBIC_DATABASE_URL`과 async DB 설정 사용
- CI job: 로컬과 동일한 compose 파일과 migration/test 명령을 사용하고 MySQL test skip 시 실패

표준 실행 순서:

```text
docker compose -f compose.test.yaml up -d --wait
  -> host port 점유와 실제 container identity 확인
  -> 빈 DB에서 alembic upgrade head
  -> pytest -m mysql
  -> 신규 revision downgrade 및 재-upgrade
  -> metadata/schema drift 확인
docker compose -f compose.test.yaml down -v
```

MySQL 검증 대상은 `DATE_ADD` 같은 방언 SQL, named binding, Raw DML rowcount, 무변경 UPDATE,
read-only DML 차단, duplicate/FK 예외 변환과 migration chain이다. schema cleanup은
`alembic_version`을 포함한 실제 table 전체를 제거하며 migration 검사는 빈 schema fixture를
쓴다. SQLite는 빠른 단위 테스트용으로 유지하되 MySQL 방언 정확성의 근거로 사용하지 않는다.

완료 게이트: 별도 로컬 MySQL 설치 없이 위 흐름이 재현되고 로컬과 CI가 같은 compose 파일을
사용하며 테스트 종료 후 container와 test volume이 정리된다.

#### D. 기준 문서의 passive-style 정합성 복구

`README.md`, `docs/ARCHITECTURE.md`, `docs/QUICKSTART.md`에서 현재 코드와 충돌하는 이전
default-style 문장을 수정한다.

필수 수정 항목:

- `feature/__init__.py`의 Router/Model 재노출 설명을 “가벼운 package marker”로 변경
- `import_all_models()` 설명을 `Apps().populate(INSTALLED_APPS, run_ready=False)`로 변경
- 신규 기능의 `main.py include_router()` 안내를 `apps.py` + `INSTALLED_APPS` 등록으로 변경
- `create_db_tables()`가 전 기능을 스캔한다는 설명을 이미 population된 metadata 사용으로 변경
- Quickstart의 “라우터가 안 붙으면 main.py 수정” 해결책을 AppConfig/INSTALLED_APPS 점검으로 변경

`tests/test_docs_consistency.py`에는 최소한 다음 회귀 검사를 추가한다.

- 세 기준 문서에 신규 앱의 `INSTALLED_APPS` 등록 절차가 존재한다.
- 현재 구조 설명에 `main.py` 직접 router 등록이나 `import_all_models()`가 다시 나타나지 않는다.
- 기능 root `__init__.py`가 Router/Model을 import한다고 안내하지 않는다.
- migration과 runtime이 같은 registry 모델 집합을 사용한다고 설명한다.

변경 이력에 과거 구조를 역사적으로 기록한 문장은 허용하되 “현재 절차”와 명확히 구분한다.

완료 게이트: 세 문서의 tree·개발 절차·문제 해결 절차가 실제 코드와 일치하고 문서 정합성
테스트가 이를 자동 보호한다.

#### E. Default 구현 피드백 보안 하드닝

default 프로젝트의 완료 구현과 CRP 기록에서 재현된 결함을 passive-style 착수 게이트로
이관한다.

- 모든 ADR-019 console/file/error handler에 SQL-noise/redaction filter를 적용하고 실제 secret
  bind probe로 SQLAlchemy·aiomysql·aiosqlite·PyMySQL 로그 유출을 검증한다. application logger의
  `%s` 예외 인자와 `exc_info` traceback도 최종 formatter 출력 기준으로 검사한다.
- 일반 500 응답은 DEBUG에서도 `str(exc)`를 반환하지 않고, 안전한 error code만 외부에 제공한다.
- SQL echo opt-in은 development/test에서만 허용하고 production/staging에서는 fail-fast한다.
- `migrations/env.py`의 `fileConfig(..., disable_existing_loggers=False)`와 migration 이후 앱
  logger 생존 테스트를 추가한다.
- `.env.example`의 CORS wildcard+credentials 충돌을 수정하고 예제 설정 로드 테스트를 추가한다.
- production/staging `ADMIN=false` 기본값 또는 동등한 fail-fast 보호를 적용하고 인증 없는
  `/admin` 및 참조 API의 잔여 위험을 운영 문서에 표시한다.
- 검수 게이트와 자식 프로세스 stdio를 UTF-8로 고정하고 AST 계층 검사, OpenAPI 비공허성,
  문서 경로·심볼·환경변수 실재 검사와 Bandit MEDIUM 이상 검사를 추가한다. Bandit은 UTF-8 text
  또는 JSON reporter를 사용하며 reporter 자체 실패도 게이트 실패로 보고한다.
- 검수 도구의 temp/cache는 실행별 고유 경로로 격리하고 cleanup한다. 실패 시 stdout과 stderr를
  함께 보존해 요약 stdout이 실제 traceback을 가리지 않게 한다.

완료 게이트: secret canary가 traceback을 포함한 어떤 최종 application handler 출력에도 나타나지
않고 DEBUG 일반 500 응답도 불투명하며, Alembic 실행 전후 logger가 살아 있고, 예제 환경 파일이
실제 Settings validation을 통과한다.

### Phase 0. 계약 고정

- 현재 Base Repository 공개 메서드 사용처 목록 작성
- 현재 API/OpenAPI snapshot과 307개 수집 테스트를 기준선으로 저장
- §10.1-A 방식으로 Windows 자식 프로세스 stderr UTF-8 계약을 수정하고 전체 green 기준선을 만든다
- ADR-019 유지와 Queue logging 후속 분리를 이번 milestone 정책으로 기록한다
- §10.1-D의 기준 문서 드리프트를 수정하고 회귀 테스트를 추가한다
- §10.1-E의 SQL logging, Alembic logger, Admin/CORS 보안 기준선을 먼저 고정한다
- 일반 500 detail 불투명성, SQL echo 환경 제한, loopback test DB publish와 Bandit UTF-8 reporter를
  착수 보안 계약에 포함한다
- 검수 게이트의 실행별 temp/cache 격리와 stdout/stderr 동시 보고를 기준선 계약에 포함한다
- ORM/Raw 공통 트랜잭션 규칙을 ADR 또는 아키텍처 문서에 확정
- DB session Dependency 정식 이름과 deprecated alias 제거 시점을 확정

완료 조건: 307개 기준 테스트가 모두 통과하고, ADR-019 유지와 App Registry 보존 정책이
명시되며, 기준 문서가 현재 코드와 일치한다. 이 조건 전에는 Phase 1에 진입하지 않는다.

### Phase 1. 비동기 Runtime 및 Lifespan Resource Manager

- `app/core/resources.py`와 `ApplicationResources` 추가
- app registry 소유 모델에서 `owned_tables`를 계산하고 전역 metadata 전체가 아닌 해당
  `tables=`만 개발 create_all 대상으로 전달
- 모델 0개일 때 DB 접속/create_all 미시도 테스트
- 기본 app 모델이 이미 import된 프로세스에서 빈/부분 registry app을 생성하는 격리 회귀 테스트
- startup 실패와 정상 shutdown의 동일 cleanup 경로 구현
- access log drain → DB engine dispose 순서 테스트
- ADR-019에 따라 기존 production/staging `RotatingFileHandler`와 관련 테스트 유지
- drain timeout 후 pending task cancel + gather + 추적 집합 비우기
- 5초 전체 예산 중 정상 대기 4초·취소 회수 1초를 확보하는 timeout 경쟁 회귀 테스트
- Celery worker shutdown signal에서 async generator, DB engine, event loop 종료
- 동기 유지 허용 작업(User-Agent/JWT/Pydantic/run_sync)의 근거를 회귀 문서에 고정
- `app/core/bootstrap.py` lifespan을 manager 호출만 남도록 단순화하고 `main.py`는 수정하지 않음
- API Redis client/cache 및 Redis readiness 연계는 후속 작업으로 제외하고, 이번 단계에서는
  writer DB만 검사하는 `/ready`와 기존 Celery Redis 설정을 유지
- DB session Dependency에 새 이름을 추가하고 기존 이름은 deprecated alias로 유지
- callable identity와 기존 `dependency_overrides` 호환성을 보존하는 alias 테스트
- 쓰기 Dependency를 `get_writer_db_session`, 조회 Dependency를
  `get_read_only_db_session`으로 전환
- `/ready` writer `SELECT 1`, 2초 timeout, 안전한 503과 route/OpenAPI 테스트 구현
- pool 크기를 Settings로 이동하고 worker/reader 수 기반 최대 연결 계산·validation 추가

완료 조건: lifecycle 조립이 한 함수로 집중되고 FastAPI와 Celery가 각자 소유한
task/loop/pool을 실패 경로에서도 해제하며 기존 logging 동작은 변하지 않는다.

### Phase 2. ORM 모델 기반 정리

- UUID/created/updated 책임이 분리된 Mixin과 조합 Base 구현
- 기존 모델을 작은 단위로 공통 믹스인으로 전환
- Alembic metadata/schema diff가 없어야 함
- 기존 API 응답이 변하지 않는지 검증
- Repository 단위 테스트 모델은 별도 `DeclarativeBase`를 사용해 application metadata 오염 방지

완료 조건: 반복 필드는 공통 정책으로 관리되고 DB 스키마 변경은 없다.

### Phase 3. ORM Repository 고도화

- `CRUDBase` primitive 책임 정리
- `BaseRepository[ModelT, PrimaryKeyT]`와 최소 공개 CRUD 계약 구현
- 입력 dict 불변, `exists`, PK typing, 안정적인 기본 정렬, 예외 변환 개선
- `str(e)`/`str(e.orig)` 응답 제거와 commit 단계까지 포함한 공통 안전 변환기 구현
- canary 값으로 HTTP 응답·로그의 SQL/params/DSN 비노출 검증
- DEBUG 일반 500과 application logger traceback의 비노출을 실제 formatter 출력으로 검증
- MySQL `rowcount=0`을 부재와 동일시하지 않도록 no-op PATCH와 실제 404 의미를 분리
- 고급 메서드 사용처를 기능별 Repository로 이동
- 호환 wrapper를 통한 점진적 전환

완료 조건: 모든 기존 ORM Repository와 API 테스트가 통과하고 공개 계약 테스트가 추가된다.

### Phase 4. Raw 기반 클래스 구현

- `raw_crud_base.py`, `raw_repository_base.py` 추가
- `RowMapping` 반환, named binding, rowcount, 예외 변환 구현
- commit 금지와 read-only DML 차단 테스트
- Raw public API의 명시적 read/write intent와 미분류 `TextClause` fail-closed를 구현하고
  일반 DML, CTE read/DML, 주석·공백·대소문자, `FOR UPDATE`, replica 오라우팅 회귀 테스트 추가
- 정적 `text()` 보간 검사와 `query_name` 형식/길이/상수 소유 규칙 추가
- 민감정보 없는 구조화 로그 기준 추가
- third-party SQL/driver 로그까지 ADR-019 모든 handler에서 차단하는 end-to-end canary 테스트
- Alembic 실행 이후 application logger가 비활성화되지 않는 회귀 테스트

완료 조건: Raw Base 단위 테스트가 DB별 차이에 독립적으로 통과한다.

### Phase 5. 두 예제 기능 구현

- §10.1-C의 MySQL Compose 환경과 CI 실행 경로를 먼저 구축
- ORM 상품 전체 CRUD(create/list/get/update/delete) 예제 추가
- Raw 일별 매출 리포트와 테스트용 Raw DML workflow 추가
- `catalog_products`와 Raw 원본 `sales_orders`를 실제 Alembic migration 두 개로 추가
- `sales_orders`용 `SalesOrder` 스키마 모델을 reports registry에 등록하되 Raw 집계 반환은
  `RowMapping`/DTO로 유지하여 metadata와 migration drift 계약 보존
- 각 migration에 명시적인 upgrade/downgrade와 migration chain 테스트 추가
- 저장소에 `compose.test.yaml` MySQL test service를 새로 추가하고 로컬과 CI에서 동일하게 사용
- SQLite 단위 테스트와 별도로 MySQL Raw SQL 및 migration 통합 테스트 실행
- MySQL 8.4 `cryptography`, loopback configurable port, tmpfs, 실제 container 확인과 CI skip 금지 적용
- `alembic_version`까지 제거하는 빈 schema fixture로 head → base → head 왕복
- 동일한 라우터/Dependency/Service/트랜잭션 구조 적용
- 기능별 테스트와 라우터 등록 누락 테스트 확장
- 각 예제에 `apps.py`의 `AppConfig` subclass를 추가하고 `config.INSTALLED_APPS`에 등록
- 기능 root `__init__.py`는 가벼운 marker로 유지하고 registry 미등록 시 route/model/admin이
  비활성임을 검증

완료 조건: 사용자는 두 예제를 나란히 비교해 데이터 접근 방식만 교체할 수 있고, SQLite
단위 테스트와 MySQL 방언/migration 통합 테스트가 각각의 책임으로 통과한다.

### Phase 6. Scalar 문서 정비

- 오래된 `tags_metadata.py` 설명 수정 및 `Auth`/신규 예제 태그 추가
- Pydantic 예시와 오류 응답 보강
- 규칙 기반 OpenAPI 정합성 테스트와 핵심 schema snapshot 추가
- 공개 Pydantic schema 이름 전역 고유성(`__` 금지), 검사 대상 비공허성과 참조 DTO 존재 검사
- 각 OpenAPI 규칙의 fail-on-revert 검증

완료 조건: Scalar에서 ORM/Raw 예제의 요청, 응답, 오류, 파라미터가 완결되어 보인다.

### Phase 7. 문서 및 최종 검수

- 개발 지침서와 실제 코드 경로·시그니처 대조
- README/ARCHITECTURE/QUICKSTART의 이전 default-style 잔재를 registry 계약에 맞게 업데이트
- `tests/test_docs_consistency.py`의 passive-style 금지·필수 패턴 회귀 검사 통과
- 문서가 참조하는 경로·심볼·환경변수 실재 여부 기계 검사
- Windows UTF-8 출력, AST 계층 불변식, 공개 API baseline과 MySQL skip 금지를 포함한
  Bandit MEDIUM 이상 검사를 포함하는 `scripts/review_gate.py` 또는 동등한 결정적 게이트 실행
- 게이트를 연속·병렬 실행해도 temp/cache 충돌이 없고 실패 fixture에서 stderr 원인이 보이는지 검증
- 완료 보고서에 부하/실행계획, 실제 replica 지연, Celery worker, Scalar UI처럼 실행하지 않은
  검증과 수용한 잔여 위험을 별도 기록
- 전체 품질 게이트 실행

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
```

## 11. 테스트 매트릭스

| 계층 | ORM | Raw |
|---|---|---|
| Base 단위 | CRUD, PK, flush, 예외 | binding, one/all/scalar, rowcount, 예외 |
| Repository | 모델/관계 쿼리 | SQL 결과 mapping, injection 방지 |
| Service | 비즈니스 규칙 | 집계 규칙, DTO 검증 |
| Dependency | read-only/writer DB session 선택 | read-only/writer DB session 선택 |
| View | 요청/응답/오류/commit | 요청/응답/오류/commit |
| Router | 버전·그룹 prefix | 버전·그룹 prefix |
| OpenAPI | ORM DTO schema | Raw DTO schema |
| 회귀 | 기존 API/DB schema 불변 | reader routing, DML 차단 |
| Lifespan | 모델 유/무, startup 실패 cleanup | 자원 close 순서, 재진입 누수 |
| 비동기 runtime | task cancel/await, 기존 logging 회귀 | Celery loop/pool shutdown |

## 12. 비목표

- View에서 SQL 직접 실행
- Raw SQL 결과를 검증 없이 `dict`로 반환
- 자동 라우터/Repository 탐색
- 기존 `INSTALLED_APPS`/`AppConfig`/`Apps` registry 제거 또는 우회
- Base 클래스에서 도메인 전용 쿼리 제공
- Repository 내부 commit
- 문자열 포매팅으로 SQL 값 또는 식별자 삽입
- ORM과 Raw Repository를 하나의 만능 클래스로 통합
- shutdown에서 DB table drop
- FastAPI process가 소유하지 않은 Celery worker 연결 종료
- API Redis client/cache 또는 Redis를 `/ready` 필수 조건으로 추가
- 짧은 CPU 연산까지 무조건 `to_thread()`로 전환
- Celery 동기 task wrapper를 근거 없이 async 함수로 변경
- JWT 인증 정책 및 access/refresh token lifecycle 구현
- ADR-019 개정 없이 운영 파일 logging 정책 변경

## 13. 최종 완료 기준

- ORM과 Raw 경로가 동일한 계층 및 트랜잭션 규칙을 따른다.
- 모든 ORM 기능 Repository가 ORM Base 계층을 사용한다.
- 모든 Raw 기능 Repository가 Raw Base 계층을 사용한다.
- ORM Base와 Raw Base 사이에 상속 관계는 없고 세션·예외 정책만 평행하게 유지한다.
- View/Service/Repository 책임을 위반하는 SQL 또는 비즈니스 규칙이 없다.
- lifespan이 manager 함수 하나로 자원을 초기화·해제하고 모델이 없으면 DB 테이블 생성을
  시도하지 않는다.
- 부분 registry app은 전역 metadata 전체가 아니라 자신이 소유한 테이블만 개발 DB에 생성한다.
- read-only 차단이 `TextClause` DML까지 적용되고 DB 오류 응답·로그가 SQL/params/driver
  원문을 노출하지 않는다.
- `/health`와 writer DB 기반 `/ready`가 분리되며 연결 pool 최대치가 배포 한도 내로 검증된다.
- startup 실패와 shutdown 모두 background task와 외부 연결을 누수 없이 정리한다.
- 기존 ADR-019의 production/staging `RotatingFileHandler` 동작과 테스트가 유지된다.
- drain timeout 후 남은 task가 취소·await되고 Celery worker loop/pool도 종료된다.
- Scalar 문서에서 두 예제의 계약이 완전하고 태그가 실제 라우터와 일치한다.
- 전체 테스트, Ruff, format check, mypy가 통과한다.
- 예제 앱의 설치 여부가 `INSTALLED_APPS` 하나로 route, model, Admin, `ready()`에 동일하게 반영된다.
- Windows와 CI에서 기준 테스트가 307/307 통과한다.
- 로컬과 CI가 같은 `compose.test.yaml`로 MySQL migration과 Raw SQL을 검증한다.
- README/ARCHITECTURE/QUICKSTART의 현재 절차가 App Registry 코드와 일치한다.
