# Residual Risk — docs-guide-review (잔여 위험 등록부)

코드 기반 재검수에서 기존 두 항목이 모두 해결되어 현재 등록된 잔여 위험은 없습니다.

## 해결된 후속 항목

| ID | 해결 내용 | 근거 |
|---|---|---|
| R-001 | `listProducts` OpenAPI 설명을 `active_only` 적용 시 반환되는 `total` 의미와 일치시켰다 | `app/features/catalog/api/routers/v1/products.py`, commit `6589418` |
| R-002 | 문서 참조 테스트의 옛 HTML 파일명 안내와 실패 메시지를 현행 경로로 수정했다 | `tests/test_docs_references.py` |
