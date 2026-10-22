# Run Log — docs-guide-site

### Round 0 — 2026-10-22 (base SHA: `6f7dc70`) · 계획
- **트리거:** REQ-001 ("1번으로 지적 전부 고쳐줘")
- **신규 finding:** HIGH 1 · MED 17 · LOW 15 → ledger 33건
- **원본 커밋:** `4d346ee` (생성물 그대로, `docs/review/`·`.env` 제외)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 33)

### Round 1 — 2026-10-22 · 수정
- **변경:** `7c8e91c`·`905dfc4`·`daf9805`·`b36a58e`·`f00b28e`·`ffb09e7`·`bd3b83b` (코드 동작 무변경 — docstring·문서·테스트)
- **계약 테스트(red→green):** 원본 문서(`4d346ee` 의 `docs/guides`)에서 `tests/test_docs_guide_site.py` 4 failed · 1 passed(스타일시트 경로는 처음부터 맞음) → 수정 후 5 passed
- **검사:** `.env` 없는 클론에서 `tests/test_doc*.py`·인가 정책·커밋 경계 테스트 310 passed ·
  작업 트리 `pytest -m "not mysql and not browser"` 1507 passed · 37 deselected · `ruff check`·`ruff format --check` 통과 ·
  링크 검사 broken 0 · HTML 태그 균형 오류 0 · 바뀐 파일 CR 0(main 과 같은 LF) · 2차 검수 표지(직접 commit 문구·request id·not integration·DB·Redis URL·mermaid@11 미고정·index 한 줄) 0
- **잔여:** R-001(Mermaid 실제 렌더 미확인), R-002(설정 설명은 Field description 수준)
- **수렴 판정:** `CONVERGED` (Open Fix 0 · Partial 2 — GS-03·DEP-03 는 코드대로 고침, ledger 사유)
