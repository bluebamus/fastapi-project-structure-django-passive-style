# 09. ORM 과 Raw 중 무엇을 쓸 것인가

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.1.0 |
| 작성일 | 2026-08-20 |
| 적용 코드 기준 | Git `b88f654` |

새 기능을 만들 때 이 구조에서 **가장 먼저 정해야 하는 것**이다. 나머지 파일(스키마·서비스·
라우터·앱 등록)의 작성 방식은 두 경우가 같고, 갈라지는 것은 Repository 구현 하나뿐이다.

## 1. 기본값은 ORM

먼저 ORM 으로 쓴다. Raw 는 ORM 이 **못 하는 일**이 생겼을 때 꺼낸다.

이유는 취향이 아니다. ORM 경로는 모델이 스키마를 소유하므로 마이그레이션과 어긋나면
그 자리에서 깨진다. Raw 경로는 SQL 문자열이 스키마를 알지 못해, 컬럼이 바뀌어도
**실행 시점까지 아무도 모른다**. 그 대가를 치를 이유가 있을 때만 치른다.

## 2. 판단 기준

| 상황 | 선택 | 왜 |
|---|---|---|
| 엔티티 단건·목록 CRUD | **ORM** | `BaseRepository` 가 create/get_by_id/get_one/get_all/count/exists/update/delete 를 이미 제공한다 |
| 관계를 타고 객체를 다룸 | **ORM** | 관계 로딩·변경 추적이 필요하다 |
| 여러 테이블 집계·리포트 (`GROUP BY`, 윈도 함수) | **Raw** | ORM 표현이 SQL 보다 길고 읽기 어려워지는 지점 |
| 대량 조회에서 필요한 컬럼만 | **Raw** | 엔티티를 만들 이유가 없다 |
| DB 고유 기능 | **Raw** | ORM 이 추상화하지 않는다 |
| 성능이 실제로 문제 | **Raw** | 단, **측정한 뒤에** 결정한다. 짐작으로 Raw 를 고르지 않는다 |

한 기능 안에서 섞어도 된다. `catalog` 가 ORM, `reports` 가 Raw 인 것은 기능 단위 분리가
아니라 **작업 성격**에 따른 분리다.

## 3. 두 계열의 실물

| | ORM | Raw |
|---|---|---|
| 상속할 Base | `app/core/repositories/repository_base.py` 의 `BaseRepository` | `app/core/repositories/raw_repository_base.py` 의 `RawRepositoryBase` |
| 하위 primitive | `app/core/repositories/crud_base.py` 의 `CRUDBase` | `app/core/repositories/raw_crud_base.py` 의 `RawCRUDBase` |
| 참조 예제 | `app/features/catalog/repositories/product_repository.py` | `app/features/reports/repositories/sales_report_repository.py` |
| 돌려주는 것 | 모델 인스턴스 | `RowMapping` / scalar / rowcount |

두 계열은 **상속 관계가 없다**. 하나의 Base 가 모델과 row 를 함께 돌려주면 호출부가
무엇을 받았는지 타입으로 알 수 없기 때문이다(AR-003). `RawCRUDBase` 는 하위 계층이라
기능 코드가 직접 상속하지 않는다 — 기능 Repository 는 `RawRepositoryBase` 를 상속한다.

## 4. 공통 규칙 (두 경우 모두)

- **Repository 는 commit 하지 않는다.** 트랜잭션 경계는 View 가 소유한다.
- 세션 Dependency 는 용도로 고른다 — `get_read_only_db_session()`(읽기),
  `get_writer_db_session()`(쓰기), `get_routed_db_session()`(라우팅 위임).
- Service 가 Pydantic 으로 검증해서야 값이 밖으로 나간다.

## 5. Raw 를 골랐을 때 추가로 지켜야 하는 것

ORM 에는 없는 제약이다. 이것들이 지켜지지 않으면 AST 검사와 테스트가 실패한다.

1. **SQL 은 `text()` 로 감싼 `TextClause`.** 문자열을 넘길 수 없다. 문자열을 받으면
   이 계층이 "안전한 문자열"과 "포맷된 문자열"을 구분할 방법이 없다.
2. **외부 값은 전부 named bind parameter** (`:start_at`). f-string·`%`·`.format()`·
   문자열 연결은 AST 검사가 실패시킨다.
3. **`query_name` 은 코드 상수.** `feature.use_case` 형식(소문자·숫자·밑줄, 점 하나,
   64자 이하)이고 요청값으로 만들지 않는다. 이 값이 로그 라벨이라, 사용자 입력이 섞이면
   로그 cardinality 가 터지고 값이 그대로 새어 나간다.
4. **읽기/쓰기 의도는 primitive 가 구문에 붙인다.** 읽기 전용 세션에서 쓰기를 시도하면
   `ReadOnlyRoutingError` 로 **실행 전에** 막힌다 — `DB_ROUTER_ENABLED` 값과 무관하다.
5. **방언 함수를 SQL 에 넣지 않는다.** 테스트는 SQLite, 운영은 MySQL 이다. 날짜 상한은
   `DATE_ADD` 같은 MySQL 전용 함수 대신 Service 가 계산한 배타 상한을 바인딩한다.

### 자주 틀리는 지점

- **`updated_at` 이 갱신되지 않는다** — `UpdatedAtMixin.onupdate` 는 ORM 이 UPDATE 를
  낼 때만 동작한다. Raw UPDATE 는 SQL 에 직접 써야 한다.
- **반환 타입이 DB 마다 다르다** — 같은 컬럼이 SQLite 에서 `str`·`float`, MySQL 에서
  `date`·`Decimal` 로 온다. `RowMapping` 을 그대로 흘리지 말고 Pydantic 으로 검증한다.
  실제 값 정확성은 MySQL 통합 테스트가 승인한다.
- **도메인 SQL 을 Base 에 두는 것** — Base 가 특정 기능의 쿼리를 알기 시작하면 다음
  기능도 거기로 오고, 결국 모든 기능이 Base 를 통해 서로 결합된다.

## 6. 결과 API 의 의미

| 메서드 | 결과 없음 | 돌려주는 것 |
|---|---|---|
| `fetch_one` | `None` | 첫 행 `RowMapping` |
| `fetch_all` | 빈 목록 | `RowMapping` 목록 |
| `fetch_scalar` | `None` | 첫 행 첫 컬럼 (`COUNT` 등 집계용) |
| `execute` | — | 영향 행 수. commit 은 하지 않는다 |

## 7. 이어서 볼 문서

- [06. 데이터 접근 및 트랜잭션 워크플로](06-data-and-transaction-workflow.md) — 세션·라우팅·커밋 경계
- [07. 기능별 워크플로](07-feature-workflows.md) — `catalog`·`reports` 가 실제로 어떻게 조립되는지
