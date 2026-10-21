# Residual Risk — docs-guide-review (잔여 위험 등록부)

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | `listProducts` 의 OpenAPI 설명(`app/features/catalog/api/routers/v1/products.py`)은 "total 은 필터와 무관한 전체 상품 수" 라고 적지만 `CatalogService.list_products` 는 `active_only=true` 면 `count(is_active=True)` 로 센다 | LOW | C-1 — 코드 문자열 변경은 이 그룹 범위 밖. 안내서는 코드 동작대로 고쳤다 | 2026-10-21 | 코드 정리 요청이 오면 설명 문자열을 동작에 맞춘다 |
| R-002 | `tests/test_docs_references.py` 의 실패 메시지가 옛 파일명 `server-lifecycle-guide.html` 을 쓴다(판정에는 영향 없음) | LOW | C-1 — 테스트 코드 | 2026-10-21 | 테스트를 고칠 때 함께 |
