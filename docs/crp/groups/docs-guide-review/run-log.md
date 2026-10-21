# Run Log — docs-guide-review

### Round 0 — 2026-10-21 (base SHA: `8553cdc`) · 계획
- **트리거:** REQ-001
- **신규 finding:** CRIT 0 · HIGH 0 · MED 12 · LOW 14 → ledger F01~F26 + 누락 8
- **수렴 판정:** `NOT CONVERGED` (Open Fix 26)

### Round 1 — 2026-10-21 · 수정
- **변경:** 커밋 `6864018`·`069bbe1`·`c998e20` (문서만, 코드·테스트 무변경)
- **검사:** `tests/test_docs_consistency.py`·`tests/test_docs_references.py`·`tests/test_docs_secret_examples.py` 80 passed ·
  링크·앵커 검사 broken 0 · html.parser 태그 오류 0(HTML 4개) · 바뀐 파일 EOL 모두 LF(main 과 같음) ·
  `pytest -m "not mysql and not browser"` 1386 passed · 37 deselected (review_gate 에 문서 전용 단계가 없어 그 pytest 단계를 직접 돌렸다)
- **잔여:** R-001(listProducts OpenAPI 설명), R-002(테스트 메시지의 옛 파일명) — 코드라 범위 밖
- **수렴 판정:** `CONVERGED` (Open Fix 0)
