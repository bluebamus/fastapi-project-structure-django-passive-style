# Residual Risk — docs-guide-site (잔여 위험 등록부)

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | Mermaid 도식 22개의 실제 렌더링은 확인하지 않았다(CDN 필요). 원문 블록과 실패 안내가 있어 본문은 읽힌다 | LOW | 오프라인 검사 환경 | 2026-10-22 | 브라우저로 허브를 열 때 |
| R-002 | 설정 표의 설명은 `Field(description=...)` 그대로라 일부는 짧다. 세부 의미는 `.env.example`·README 가 정본 | LOW | ADR-003 — 코드에서 뽑아 어긋남을 막는 쪽을 택했다 | 2026-10-22 | 설명 보강 요청이 오면 Field description 을 고친다 |
