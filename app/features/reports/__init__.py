"""Reports 기능 패키지 — **Raw SQL 데이터 접근 예제**.

`catalog` 기능(ORM)과 나란히 두고 읽으라고 만든 것이다. 라우터 등록·Dependency·
Service·트랜잭션 경계·DTO 검증·예외 처리가 저쪽과 **완전히 같고**, Repository 만
`RawRepositoryBase` 를 상속한다.

`sales_orders` 는 이 저장소가 Alembic 으로 소유하는 원본 테이블이라 스키마 모델
(`models/models.py` 의 ``SalesOrder``)을 두고 App Registry 가 수집하게 한다. 그래야
registry-model/metadata 동등성과 schema drift 검사가 유지된다. 다만 **조회 결과로는
쓰지 않는다** — 집계 결과는 ``RowMapping`` 으로 받아 Pydantic DTO 로 검증한다.

**가벼운 package marker 다.** 결선은 ``apps.py`` 의 ``ReportsConfig`` 가 선언한다.

* Router: ``app/features/reports/api/routers/router.py`` 의 ``reports_router``
* Models: ``app/features/reports/models/``
"""
