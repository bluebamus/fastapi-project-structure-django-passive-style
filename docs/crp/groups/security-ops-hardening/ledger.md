# Ledger — security-ops-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001 ① · INV-1 | Fix | Fixed | Round 1 · `app/core/db/session.py`(`ENGINE_SAFETY_OPTIONS`) · `migrations/env.py` · `tests/core/test_engine_hide_parameters.py` | 엔진 생성 지점 4곳(writer·reader·background·Alembic) 어디에도 `hide_parameters` 가 없어 `IntegrityError` 문자열·`logger.exception` 출력에 INSERT 값(이메일·해시)이 그대로 실렸다(감독자 확인). fail-on-revert: 옵션 정본을 `{}` 로 → 4건 실패(무결성 오류 문자열·로그 출력·엔진 객체·정본 값), `migrations/env.py` 펼침 제거 → 생성 지점 AST 검사 실패 |
| F-002 | MED | REQ-001 ② · INV-2 | Fix | Fixed | Round 1 · `config.py` · `.env.example` · home repository·service·provider·`tasks.py` · `app/features/home/tests/test_access_log_retention.py` · `tests/integration/test_mysql_access_log_retention.py` | 접속 로그에 보존 기간이 없었다. fail-on-revert: 경계 `<`→`<=` 1건, 배치 커밋 제거 3건, 배치 반복 제거 2건, 보존 0 검사 제거 1건, `ge=0` 제거 1건, provider 보존 일수 누락 1건, beat 등록 제거 1건 실패 |
| F-003 | MED | REQ-001 ④ · INV-3 | Fix | Fixed | Round 1 · `app/core/security/admin_auth.py`(`AdminLoginCsrf`) · `app/templates/admin/sqladmin/login.html` · `tests/core/security/test_admin_auth.py` · `tests/admin_login.py` | 로그인 폼에 CSRF 토큰이 없었다(admin-login R-002). fail-on-revert: 파일 되돌림 → 수집 오류, 검사 생략 → 7건, 레이트 리밋을 CSRF 앞에 → 4건(카운터 증가 3·ip 한도 1), `==` 비교 → 상수 시간 테스트 1건, 템플릿 hidden 입력 제거 → 로그인 흐름 6건 + 관리 페이지 3 errors 실패 |
| F-004 | LOW | REQ-001 ⑤ · INV-4 | Fix | Fixed | Round 1 · `app/core/admin_filters.py`(`LocalDateFilter`) · `app/templates/admin/sqladmin/filters/local_date_filter.html` · 관리 뷰 7개 · `tests/core/test_admin_date_filter.py` · `tests/core/test_admin_pages.py` | 관리 목록의 시각 컬럼 필터가 없었다(admin-login R-006). fail-on-revert: 관리 뷰 7개 되돌림 → 2건, `on` 끝 경계 포함 → 1건, UTC 변환 없음 → 3건, 형식 오류 처리 제거 → 6건(500 포함) 실패 |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
-->
