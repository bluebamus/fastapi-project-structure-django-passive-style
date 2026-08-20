"""Catalog 기능 패키지 — **ORM 데이터 접근 예제**.

같은 저장소의 `reports` 기능과 나란히 두고 읽으라고 만든 것이다. 두 기능은 라우터
등록·Dependency·Service·트랜잭션 경계·DTO 검증·예외 처리가 **완전히 같고**, 오직
Repository 구현만 다르다(ORM vs Raw SQL).

**가벼운 package marker 다.** Router 도 Model 도 여기서 import 하지 않는다 —
registry 의 3단계 초기화(config → models → ready)를 지키려면 root package import
단계에서 하위 모듈이 딸려오면 안 된다. 결선은 ``apps.py`` 의 ``CatalogConfig`` 가
선언하고 ``app/core/apps/wiring.py`` 가 수행한다.

* Router: ``app/features/catalog/api/routers/router.py`` 의 ``catalog_router``
* Models: ``app/features/catalog/models/``
"""
