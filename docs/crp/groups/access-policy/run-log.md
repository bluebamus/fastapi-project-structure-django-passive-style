# Run Log — access-policy (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이
> 안 바뀌었으면 동일 요청은 "할 일 없음".

## 라운드 기록

### Round 0 — 2026-10-13 (base SHA: `e78f7cb`) · 계획 · 조사
- **트리거:** 사용자 요청 REQ-001
- **조사:** 가드 초안의 판정을 `main.app` 에 돌렸다. 메서드 기준 API 라우트 39개 중 선언 없음 15개 — blog·sns·reply·catalog 의
  목록·단건 GET 8, auth register·login·refresh·logout 4, `/health`·`/ready`·`/docs`(DEBUG). 나머지는 인자(`CurrentPrincipal`)·
  라우트 단위 `_ADMIN_ONLY`·라우터 단위 `require_superuser`(home·reports)로 이미 판정됐다 — 라우터 단위가 `effective_route_contexts()` 의
  `dependant` 에 합쳐져 있음을 확인했다. FastAPI 기본 `/openapi.json` 은 Starlette `Route`, `/admin` 은 `Mount`.
- **신규 finding:** CRIT 0 · HIGH 0 · MED 2 · LOW 2 → ledger F-001 ~ F-004
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-13 · 구현 · 검증
- **변경:** `app/core/security/access.py`(신규), `create_app()` 8단계 `verify`, 예시 뷰·health·ready·docs 선언, 스캐폴드, 권한표 테스트 정리, 문서.
- **fail-on-revert(대상 파일을 작업 폴더 밖에 복사 → 변형 → 지정 테스트 → 복원):**
  - 가드 무력화 2 실패 · 슈퍼유저 접기 제거 4 · 쓰기+Public 검사 제거 2 · 안전+PublicWrite 검사 제거 2 · 중첩 펼침 제거 2 · 트리 재귀 제거 1
  - `create_app()` 의 `verify` 제거 → `test_create_app_refuses_to_start_with_an_undeclared_route` 실패
  - blog `listPosts` 선언 제거 → `main` import 단계에서 기동 거부(수집 오류) · catalog 생성 `LoginRequired` → 회귀 표 대조 실패
  - 스캐폴드 `Public` 제거 → `test_generated_app_is_inactive_until_registered` 실패
- **검사(`.env` 없는 저장소 밖 클론):** ruff format·check 통과 · mypy 219 파일 이상 없음 · bandit MEDIUM 이상 0건(253 파일) ·
  `pytest -m "not mysql and not browser" -rsxX --cov=app` **1102 passed · 34 deselected · skip 0 · coverage 96%** ·
  OpenAPI fail-on-revert 20/20 감지 · `-m browser` 수집 8건(로컬은 수집만). pip-audit(네트워크)·mysql·browser 실행은 CI 몫.
- **신규 finding:** 0
- **수렴 판정:** `CONVERGED` (Open Fix 0)
