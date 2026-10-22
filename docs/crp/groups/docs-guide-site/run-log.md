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

### Round 2 — 2026-10-22 · 재검수 남은 결함 (REQ-002 "2번으로 진행해줘")
- **트리거:** 재검수 보고(Codex 실증 + Claude 재검수)의 passive 남은 결함 P-N1~P-N5 + 공통 X-1~X-3
- **정정:** Round 1 의 `CONVERGED (Open Fix 0)` 는 사실과 달랐다(ledger 정정-01)
- **변경:** `bab635a`·`1a47a02`·`1cbe48b` + 기록 커밋 (코드 동작 무변경 — 문서·docstring·주석·.env.example 주석·테스트)
- **계약 테스트(red→green):** 저장소 밖 복사본에서 features/auth `register` 접근 수준 public_write→login, 설정 표 `MYSQL_PORT` 3306→9999 로 변조 →
  보강 전 테스트 5 passed(헛통과) / 보강 후 각각 1 failed → 원본 7 passed. X-2: fragment 변조는 기존 검사가 이미 1 failed. Mermaid 고정 URL 삭제도 기존 검사가 1 failed
- **수렴 판정:** `CONVERGED` (Open Fix 0 · Not a defect 1 — X-2)

### 후속 P-F1 — 2026-10-22 · 접속 로그 저장 범위 (병합 후 가로 대조)
- **트리거:** main `fc8ae20` 병합 뒤 가로 대조에서 "모든 요청에서 수집·저장" 문구가 `_should_skip`(활성·제외 경로·제외 확장자)과 어긋남
- **변경:** `329ad95` (docstring·API 소개 문자열·.env.example 주석·문서만, 코드 동작 무변경)
- **상태:** 수정됨 — 검수 대기
