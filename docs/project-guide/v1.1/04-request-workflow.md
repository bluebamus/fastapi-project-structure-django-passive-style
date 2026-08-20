# 전체 요청 워크플로

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.1.0 |
| 작성일 | 2026-08-20 |
| 대상 프로젝트 | fastapi-project-structure-django-passive-style 0.1.0 |
| 적용 코드 기준 | Git `b88f654` |

## 1. 전체 흐름

```mermaid
sequenceDiagram
    participant C as Client
    participant M as Middleware
    participant R as Router
    participant D as Dependency
    participant S as Service
    participant P as Repository
    participant DB as Database
    participant BG as Access-log task

    C->>M: HTTP request
    M->>M: CORS / 접속정보 수집
    M->>R: 설치된 route 호출
    R->>D: Service 또는 현재 사용자 요청
    D->>D: read/write session 선택
    D-->>R: Service/User
    R->>S: 유스케이스 실행
    S->>P: 영속성 연산
    P->>DB: SQL 실행/flush
    DB-->>P: 결과
    P-->>S: entity/result
    S-->>R: 결과
    opt 쓰기 요청
        R->>S: commit()
        S->>DB: session.commit()
    end
    R-->>M: response
    M-->>C: HTTP response
    M-->>BG: 접속 로그 저장 task 생성
    BG->>DB: 별도 background pool로 저장
```

## 2. 요청 진입

1. Uvicorn이 `main:app`으로 요청을 전달한다.
2. CORS middleware가 preflight와 응답 header 정책을 적용한다.
3. 접속 로그가 활성화되어 있고 제외 경로·확장자가 아니면 `UserInfoMiddleware`가 요청 정보를 수집한다.
4. Registry가 설치한 Router에서 method와 path가 일치하는 handler를 선택한다.
5. FastAPI가 path, query, body, form, header와 dependency를 검증·해석한다.

## 3. 조회 요청

대표 흐름은 `GET /api/v1/blog/posts`다.

1. Router가 `get_blog_service_readonly`를 요청한다.
2. dependency가 `get_read_only_db_session()`으로 `AsyncSession`을 열고 `BlogService`를 만든다.
3. Service가 `PostRepository`에 페이지 조회를 위임한다.
4. DB Router가 활성화되고 replica가 구성되어 있으면 SELECT는 해당 세션에 고정된 reader로 간다.
5. 결과는 Pydantic response model로 직렬화된다.
6. 조회 경로는 `commit()`을 호출하지 않는다.
7. 예외가 있으면 dependency가 rollback하고 전역 handler가 오류 응답을 만든다.

## 4. 쓰기 요청

대표 흐름은 `POST /api/v1/blog/posts`다.

1. 요청 body가 `PostCreate` schema로 검증된다.
2. `get_blog_service`가 `get_writer_db_session()` 으로 Service를 만든다.
3. Service가 Repository의 `create()`를 호출한다.
4. Repository가 model을 추가하고 flush하여 DB 생성값을 확보한다.
5. Router가 `await service.commit()`을 명시적으로 호출한다.
6. 커밋 성공 후에만 201 응답 model이 생성된다.
7. 커밋 또는 처리 중 예외가 발생하면 세션 dependency가 rollback한다.

수정과 삭제도 같은 경계를 사용한다. 존재하지 않는 리소스는 기능별 Not Found 예외로 변환된다.

정의 위치: `app/features/blog/dependencies/blog_dependencies.py`

## 4-1. Raw SQL 조회 요청

대표 흐름은 `GET /api/v1/reports/sales/daily`다. **§3 과 비교하면 다른 곳이 한 군데뿐**이다.

1. Router가 `get_report_service_readonly`를 요청한다.
2. dependency가 `get_read_only_db_session()`으로 세션을 열고 `ReportService`를 만든다.
3. Service가 입력 기간을 검증하고 `SalesReportRawRepository`에 위임한다.
4. **Repository 가 `fetch_all()` 에 모듈 상수 `text()` 와 bind parameter 를 넘긴다.**
5. 결과 `RowMapping` 을 Service 가 Pydantic model 로 변환한다.
6. 조회 경로는 `commit()`을 호출하지 않는다.

4번만 다르다. 1·2·3·5·6 은 ORM 조회와 글자 그대로 같다.

정의 위치: `app/features/reports/repositories/sales_report_repository.py`

### 세션은 데이터 접근 방식이 아니라 하는 일이 정한다

`reports` 는 Raw SQL 을 쓰지만 **read-only 세션만** 노출한다. "Raw 니까 쓰기 세션" 이
아니다 — 이 기능이 하는 일이 집계 조회뿐이라서다.

거꾸로 `catalog` 는 ORM 이지만 쓰기 endpoint 에 `get_writer_db_session()` 을 쓴다.
**세션 선택 기준은 두 갈래가 완전히 같다.**

read-only 세션에서 Raw DML 을 시도하면 SQL 이 DB 에 닿기 전에 `ReadOnlyRoutingError`
로 거부된다. 그 동작은 `app/features/reports/tests/test_raw_dml_workflow.py` 가 고정한다.

## 5. 인증 요청

### 로그인

1. `/api/v1/auth/login`이 OAuth2 password form을 받는다.
2. `AuthService`가 username으로 사용자를 조회한다.
3. bcrypt로 비밀번호를 검증하고 활성 여부를 확인한다.
4. Access Token과 Refresh Token을 발급해 반환한다.

### 보호된 요청

1. `OAuth2PasswordBearer`가 Authorization header에서 Bearer token을 읽는다.
2. `decode_token()`이 access secret, algorithm, 만료, token type을 검증한다.
3. subject로 사용자를 읽기 전용 세션에서 조회한다.
4. 사용자가 존재하고 활성 상태면 handler에 전달한다.
5. 실패하면 공통 401 응답으로 처리한다.

## 6. 오류 흐름

| 오류 출처 | 처리 |
|---|---|
| 기능/비즈니스 예외 | `AppException` handler가 status와 error code 유지 |
| 요청 검증 실패 | field·message·type 목록을 포함한 검증 오류 응답 |
| FastAPI/Starlette HTTP 예외 | `HTTP_<status>` 형식으로 정규화 |
| 예상하지 못한 예외 | 500 응답, DEBUG가 아니면 상세 숨김 |

## 7. 접속 로그 후처리

응답 handler가 끝나면 middleware는 상태 코드와 처리 시간을 수집 데이터에 합친다. `BackgroundTaskRunner.spawn()`이 작업을 수락하면 home 앱이 등록한 sink가 별도 background session으로 `UserAccessLog`를 저장하고 커밋한다.

동시 작업이 256개에 도달하면 새 로그 작업은 요청을 지연시키지 않고 드롭되며 누적 횟수가 기록된다. 로그 저장 실패 역시 원래 요청 응답에는 영향을 주지 않는다.

## 8. 종료 시 흐름

```mermaid
flowchart LR
    A[Shutdown signal] --> B[접속 로그 task drain]
    B --> C[Primary/replica engine dispose]
    C --> D[Background engine dispose]
    D --> E[Application stopped]
```

## 9. 관련 문서

- [데이터 접근 및 트랜잭션 워크플로](06-data-and-transaction-workflow.md)
- [기능별 워크플로](07-feature-workflows.md)
- [ORM/Raw 선택 기준](09-orm-vs-raw-decision.md)

## 변경 이력

| 문서 버전 | 작성일 | 변경 내용 |
|---|---|---|
| 1.1.0 | 2026-08-20 | 세션 dependency 이름 정정, Raw SQL 조회 흐름(§4-1) 추가 |
| 1.0.0 | 2026-08-18 | 조회·쓰기·인증·오류·접속 로그의 전체 요청 흐름 최초 정리 |
