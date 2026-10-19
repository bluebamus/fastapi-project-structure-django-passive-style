# Ledger — admin-session-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 ① · INV-1·2·3·5·6 | Fix | Fixed | Round 1 · `cc72ade` · `app/core/security/admin_session.py` · `app/core/security/admin_auth.py` · `app/core/apps/wiring.py` · `config.py` · `tests/core/security/test_admin_session.py` · `tests/core/security/test_admin_auth.py` | 서명 쿠키 세션이라 로그아웃 뒤 복사 쿠키가 8시간 유효했다(admin-login R-001·security-ops-hardening R-003). fail-on-revert: 로그아웃 키 미삭제 → 2건, 로그인 회전 제거 → 1건, TTL=idle 고정 → 1건, 절대 만료 검사 제거 → 1건, TTL 갱신 제거 → 1건, HMAC 대신 sid 키 → 1건, Redis 장애 삼킴 → 1건, 사용자별 폐기 no-op → 1건, idle≤max 검증 제거 → 1건 실패 |
| F-002 | MED | REQ-001 ② · INV-4 | Fix | Fixed | Round 1 · `cc72ade` · `AdminCsrfMiddleware`·`AdminCsrf`·`require_post_logout` · `app/templates/admin/sqladmin/base.html` · `tests/core/test_admin_csrf.py` · `tests/browser/test_admin_login.py` | 로그인 이후 생성·수정·삭제·일괄 삭제·가져오기·로그아웃(GET)에 토큰이 없었다(security-ops-hardening R-001). fail-on-revert: 미들웨어 통과 → 1건(첫 실패에서 멈춤), 헤더 경로 무시 → 1건, 폼 본문 재생 제거 → 요청이 걸림(120초 시간 초과), 로그아웃 POST 전환 제거 → 1건, meta 제거 → 1건, 스크립트 헤더 부착 제거 → 1건, 로그아웃 POST 스크립트 제거 → 1건 실패 |
| F-003 | MED | REQ-001 ① · REQ-002 · INV-3 | Fix | Fixed | Round 1 · `cc72ade` · `UserService._revoke_sessions` · `get_admin_session_store` · `UserAdmin.on_model_change/after_model_change/after_model_delete` · `scripts/create_superuser.py` · `app/features/user/tests/test_endpoint.py` · `tests/core/test_admin_csrf.py` · `tests/scripts/test_create_superuser.py` | 비활성화·강등·삭제·비밀번호 변경 뒤에도 관리 세션이 남았다(매 요청 DB 확인만). fail-on-revert: API 폐기 제거 → 1건, 관리 화면 수정 훅 제거 → 1건, 삭제 훅 제거 → 1건, 스크립트 폐기 제거 → 1건, 전후 비교 없이 항상 폐기 → 1건, 강등 비교 제거 → 1건, 비활성화 비교 제거 → 1건, 폐기 표시 무력화 → 1건, Redis 오류 삼킴 → 1건 실패 |
| F-006 | MED | REQ-003 · INV-3 | Fix | Fixed | Round 2 · `app/core/security/revocation.py`(`UserSessionRevoker`) · `UserAdmin.on_model_change/on_model_delete` · `get_user_session_revoker` · `tests/core/test_admin_csrf.py` | 관리 화면 폐기가 커밋 뒤라 Redis 장애 때 "DB 강등 + 세션 생존" 이 남을 수 있었고, 관리 화면 경로는 refresh 를 폐기하지 않았다. fail-on-revert: refresh 폐기 빠짐 → 1건, 관리 세션 폐기 빠짐 → 1건, 수정 폐기 실패 삼킴 → 1건(커밋됨), 삭제 폐기 실패 삼킴 → 1건(삭제됨), 삭제 훅 제거 → 1건, 전후 비교 없이 폐기 → 1건, 강등·비활성화 비교 제거 → 각 1건, 수정 훅 무력화 → 1건(자기 강등), API 폐기 호출 제거 → 1건 실패 |
| F-004 | LOW | REQ-001 ③ · INV-7 | Fix | Fixed | Round 1 · `97d274f` · `app/core/admin_filters.py` · `app/templates/admin/sqladmin/filters/local_date_filter.html` · `tests/core/test_admin_date_filter.py` · `tests/core/test_admin_pages.py` | 한 필터로 기간을 지정할 수 없었다(security-ops-hardening R-005). fail-on-revert: 기간 연산 제거 → 실패, 종료일 미포함 → 1건, 역순 허용 → 1건, 템플릿 종료일 입력 제거 → 1건 실패 |
| F-005 | LOW | REQ-001 ④ | Accept-out-of-scope | Accepted | ADR-006 · residual-risk R-002 | 메서드별로 나눈 라우트의 405 `Allow` 불완전 — 사용자 결정으로 수용(2026-10-19) |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
-->
