# Ledger — access-policy (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 ② · C-2 | Fix | Fixed | Round 1 · `app/core/security/access.py` · `app/core/bootstrap.py` · `tests/core/security/test_access_policy.py` | 기본값이 공개였다 — 선언을 잊은 라우트는 회귀 표 테스트가 있어야만 잡혔고 앱은 그대로 기동했다. 기동 시 검사로 닫았다. fail-on-revert: 가드 무력화(`if found` → `if False`) 2건 실패, `create_app` 의 `verify` 호출 제거 → `test_create_app_refuses_to_start_with_an_undeclared_route` 실패, 슈퍼유저 접기 제거 4건·쓰기+Public 검사 제거 2건·안전+PublicWrite 검사 제거 2건·`_IncludedRouter` 펼침 제거 2건·트리 재귀 제거 1건 실패 |
| F-002 | MED | REQ-001 ①④ · C-1 | Fix | Fixed | Round 1 · 예시 뷰 8개 파일 · `app/core/bootstrap.py`(health·ready·docs) · `tests/test_authorization_policy.py::test_example_views_declare_the_intended_access_level` | 공개 GET·auth 쓰기·health·ready·docs 에 선언이 없었고 home·reports 는 라우터 단위였다. 뷰 단위로 통일, 응답 코드·OpenAPI 불변. fail-on-revert: blog `listPosts` 의 `Public` 제거 → `main` import 가 기동 거부로 수집 오류, catalog 생성을 `LoginRequired` 로 바꾸면 회귀 표 테스트 실패 |
| F-003 | LOW | REQ-001 ⑤ | Fix | Fixed | Round 1 · `scripts/new_app.py` · `tests/scripts/test_new_app.py::test_generated_app_is_inactive_until_registered` | 스캐폴드 `GET /ping` 에 선언이 없어 생성 즉시 기동 거부가 될 상태였다. `Public` + 템플릿 주석. fail-on-revert: 템플릿에서 `Public` 제거 → 실패 |
| F-004 | LOW | ADR-003 | Fix | Fixed | Round 1 · `tests/test_authorization_policy.py` | 표 ↔ OpenAPI 집합 비교(`test_policy_table_covers_every_operation`)는 기동 검사와 중복 — 같은 표를 가드 판정과 대조하는 테스트로 바꿨다(표 한 벌) |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
-->
