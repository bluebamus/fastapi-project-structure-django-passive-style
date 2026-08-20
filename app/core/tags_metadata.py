"""
OpenAPI Tags Metadata

API 문서의 태그 정보를 정의합니다.
Scalar 문서에서 각 태그별로 그룹화되어 표시됩니다.

사용 방법:
    main.py에서 FastAPI 앱 생성 시 openapi_tags 파라미터로 전달합니다.

    from app.core.tags_metadata import tags_metadata

    app = FastAPI(
        openapi_tags=tags_metadata,
        ...
    )

태그 구조:
    - name: 태그 이름 (엔드포인트의 tags=["Name"]과 일치해야 함)
    - description: 태그 설명 (Markdown 지원)
    - externalDocs: 외부 문서 링크 (선택적)

계약:
    이 목록은 **실제 사용되는 태그와 정확히 일치**해야 한다(DOC-004). 선언만 하고
    쓰지 않는 태그는 Scalar 좌측 목록에 빈 항목으로 남고, 반대로 선언하지 않은
    태그는 설명 없이 나타난다. 둘 다 tests/test_openapi_contract.py 가 잡는다.
"""

tags_metadata = [
    # =========================================================================
    # 시스템 API
    # =========================================================================
    {
        "name": "Health",
        "description": """
**서버 상태 확인 API**

liveness 와 readiness 를 **분리**해서 제공합니다(ADR-013).

| 경로 | 묻는 것 | DB 접속 |
|---|---|---|
| `GET /health` | 프로세스가 살아 있는가 | 하지 않음 |
| `GET /ready` | 요청을 받을 준비가 됐는가 | writer 에 ping |

`/health` 가 DB 를 보지 않는 이유는, liveness 가 DB 에 의존하면 DB 가 잠깐
흔들릴 때 오케스트레이터가 멀쩡한 프로세스를 죽이기 때문입니다. 준비되지 않은
인스턴스는 재시작이 아니라 로드밸런서에서 빼는 것이 맞습니다.
        """,
    },
    # =========================================================================
    # 인증
    # =========================================================================
    {
        "name": "Auth",
        "description": """
**인증 API**

JWT 기반 회원가입·로그인·토큰 재발급과 현재 사용자 조회를 제공합니다.

### 엔드포인트
- `POST /register` — 회원가입 (bcrypt 해시 저장)
- `POST /login` — 자격 검증 후 access/refresh 토큰 발급
- `POST /refresh` — refresh 토큰으로 재발급
- `GET /me` — 현재 토큰의 사용자

### 응답 모델
`AuthenticatedUserResponse` 는 `User` 태그의 `UserResponse` 와 **다른 모델**입니다 —
인증 경로는 생성·수정 시각 없이 최소 정보만 돌려줍니다.

`login` 과 `refresh` 는 DB 를 변경하지 않습니다. 쓰기 메서드지만 커밋하지 않습니다.
        """,
    },
    # =========================================================================
    # Home 모듈 API
    # =========================================================================
    {
        "name": "Home",
        "description": """
**접속 로그 조회 API**

미들웨어가 수집한 접속 로그를 조회·집계합니다. 쓰기 엔드포인트는 없습니다 —
기록은 요청 처리 경로가 자동으로 남깁니다.

### 엔드포인트
- 목록 조회 (페이지네이션)
- 최근 접속 로그
- IP별 / 사용자별 필터
- 장치·OS·브라우저별 통계

### 수집 정보
IP 주소(`X-Forwarded-For`·`X-Real-IP` 우선), User-Agent 파싱 결과(OS·브라우저·장치),
요청 경로와 응답 시간.
        """,
    },
    # =========================================================================
    # User 모듈 API
    # =========================================================================
    {
        "name": "User",
        "description": """
**사용자 관리 API**

사용자 레코드의 CRUD 를 제공합니다. 인증(로그인·토큰)은 `Auth` 태그가 담당합니다.

### 엔드포인트
- `POST /users` — 생성 (이메일·사용자명 중복 시 409)
- `GET /users` — 목록 (페이지네이션, limit 상한 있음)
- `GET /users/{user_id}` — 단건 조회
- `PATCH /users/{user_id}` — 부분 수정 (전달한 필드만)
- `DELETE /users/{user_id}` — 삭제

응답 `UserResponse` 에는 비밀번호 해시가 포함되지 않습니다.
        """,
    },
    # =========================================================================
    # Blog 모듈 API
    # =========================================================================
    {
        "name": "Blog",
        "description": """
**블로그 게시글 API**

게시글 CRUD 를 제공합니다.

### 엔드포인트
- `POST /posts` — 작성
- `GET /posts` — 목록 (페이지네이션, limit 상한 100)
- `GET /posts/{post_id}` — 단건 조회
- `PATCH /posts/{post_id}` — 부분 수정
- `DELETE /posts/{post_id}` — 삭제

댓글은 `Reply` 태그가 담당합니다.
        """,
    },
    # =========================================================================
    # Reply 모듈 API
    # =========================================================================
    {
        "name": "Reply",
        "description": """
**댓글 API**

게시글에 달리는 댓글 CRUD 를 제공합니다.

### 엔드포인트
- `POST /replies` — 작성 (`post_id` 로 게시글 지정)
- `GET /replies` — 목록 (페이지네이션)
- `GET /replies/{reply_id}` — 단건 조회
- `PATCH /replies/{reply_id}` — 부분 수정
- `DELETE /replies/{reply_id}` — 삭제
        """,
    },
    # =========================================================================
    # SNS 모듈 API
    # =========================================================================
    {
        "name": "SNS",
        "description": """
**SNS 게시글 API**

짧은 글과 좋아요 수를 다루는 게시글 CRUD 를 제공합니다.

### 엔드포인트
- `POST /posts` — 작성
- `GET /posts` — 목록 (페이지네이션)
- `GET /posts/{post_id}` — 단건 조회
- `PATCH /posts/{post_id}` — 부분 수정
- `DELETE /posts/{post_id}` — 삭제

`Blog` 와 별개의 도메인입니다 — 같은 `/posts` 경로를 쓰지만 프리픽스가 다릅니다.
        """,
    },
    # =========================================================================
    # Catalog 모듈 API — ORM 데이터 접근 예제
    # =========================================================================
    {
        "name": "Catalog",
        "description": """
**상품 카탈로그 API (ORM 예제)**

SQLAlchemy ORM 으로 데이터에 접근하는 완결된 CRUD 예제입니다.
`Sales Reports` 태그의 Raw SQL 예제와 나란히 비교하도록 만들어졌습니다 —
두 기능은 **Repository 구현만 다르고** 나머지는 모두 같습니다.

### 엔드포인트
- `POST /products` — 등록 (SKU 중복 시 409)
- `GET /products` — 목록 (limit 상한 100, SKU 오름차순 안정 정렬)
- `GET /products/{product_id}` — 단건 조회
- `PATCH /products/{product_id}` — 부분 수정
- `DELETE /products/{product_id}` — 삭제

### 데이터 접근
`ProductRepository(BaseRepository[Product])` 가 ORM 모델을 돌려주고, 응답 DTO 가
`from_attributes=True` 로 변환합니다. 금액은 `Numeric(12, 2)` 입니다 — float 으로
두면 합계가 조용히 틀어집니다.

> 인증 없는 참조 예제입니다. 실제 업무 기능으로 승격할 때 인증·인가를 다시 검토하세요.
        """,
    },
    # =========================================================================
    # Sales Reports 모듈 API — Raw SQL 데이터 접근 예제
    # =========================================================================
    {
        "name": "Sales Reports",
        "description": """
**매출 리포트 API (Raw SQL 예제)**

SQLAlchemy `text()` 로 집계 쿼리를 실행하는 예제입니다. `Catalog` 태그의 ORM
예제와 라우터·Dependency·Service·트랜잭션·DTO 검증 구조가 동일합니다.

### 엔드포인트
- `GET /daily-sales` — 기간 내 일자별 주문 수와 매출 합계

결제 완료(`paid`) 주문만 집계하며, 종료일은 **포함**입니다. 조회 기간 상한은
366일입니다 — 무제한 집계는 replica 를 통째로 묶습니다.

### 데이터 접근
`SalesReportRawRepository(RawRepositoryBase)` 가 `RowMapping` 을 돌려주고, Service 가
`dict(row)` 를 **명시적으로** Pydantic 검증합니다. ORM 객체가 아니므로
`from_attributes` 에 기댈 수 없습니다 — 컬럼 alias 가 바뀌면 그 자리에서 실패합니다.

조회 전용이라 read-only 세션만 사용합니다. Raw SQL 이라는 이유로 쓰기 세션을
쓰지 않습니다 — 세션 선택은 데이터 접근 방식이 아니라 하는 일이 결정합니다.

> 인증 없는 참조 예제입니다. 실제 업무 기능으로 승격할 때 인증·인가를 다시 검토하세요.
        """,
    },
]
