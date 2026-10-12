# Ledger — admin-login (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001 ② · 위협 모델: 무인증 관리 화면 | Fix | Fixed | Round 1 · `app/core/security/admin_auth.py` · `app/core/security/admin_credentials.py` · `app/features/auth/admin_credentials.py` · `app/core/apps/wiring.py` · `tests/core/security/test_admin_auth.py` · `app/features/auth/tests/test_admin_credentials.py` · `tests/core/test_admin_login_flow.py` | `/admin` 이 자격증명 없이 사용자·게시글·접속 로그의 조회·수정·삭제·내보내기를 허용했다(service-hardening R-001). 슈퍼유저 세션 로그인으로 닫았다 |
| F-002 | MED | REQ-001 ④ · ADR-004 | Fix | Fixed | Round 1 · `config.py` · `app/core/bootstrap.py` · `tests/core/test_security_hardening.py` (`test_admin_is_allowed_in_deployment_without_an_ack`·`test_leftover_ack_in_environment_is_ignored`·`test_removed_ack_does_not_survive_in_code_or_operator_docs`) · `tests/core/test_deployment_safety.py::test_deployed_admin_boots_with_login_backend_and_ignores_the_removed_ack` | 무인증 승인 플래그·배포 환경 거부 규칙·기동 WARNING 이 로그인 도입 뒤에도 남아 정상 배포를 막는다 |
| F-003 | MED | REQ-001 ③ | Fix | Fixed | Round 1 · `app/templates/admin/sqladmin/login.html` · `tests/core/test_admin_login_flow.py` (`test_login_page_is_the_bootstrap_screen`·`test_login_page_escapes_the_error_message`) · `tests/core/test_admin_wiring.py::test_login_template_overrides_the_sqladmin_default` · `tests/browser/test_admin_login.py` | sqladmin 기본 로그인 화면은 `base.html`(Tabler·JS)을 확장하고 autocomplete 를 끈다. Bootstrap 독립 화면으로 덮어썼다 |
| F-004 | MED | REQ-001 ① · ADR-008 | Fix | Fixed | Round 1 · `README.md` · `.env.example` · `config.py` · `docs/guides/*` · `migrations/versions/e5a7c2d9f310_store_datetimes_as_utc.py` · `app/core/middlewares/client_ip.py` · `scripts/create_superuser.py` | 배포 전 할 일이 문서마다 달랐다 — KST→UTC 리비전의 오프셋 가정·백업은 README·`.env.example` 에 없었고, "/admin 은 인증 없음" 서술이 README·ARCHITECTURE·HTML 안내서·admin.py docstring 에 남아 있었다 |
| F-005 | LOW | ADR-006 | Fix | Fixed | Round 1 · `config.py` `SessionSettings` docstring · ARCHITECTURE §3.2 · 서버 수명주기 안내서 | `SESSION_SECRET_KEY` 를 "소비처 없음" 으로 적은 서술이 사실과 달라졌다(관리 세션 서명) |
| F-006 | MED | REQ-002 ① · ADR-005 | Fix | Fixed | Round 2 · `config.py` (`ADMIN_DISABLED`·`validate_removed_settings`) · `app/core/bootstrap.py` · `tests/core/test_admin_disabled.py` · `tests/core/test_admin_lazy_loading.py` | 관리 화면 끄기가 `ADMIN=false` 였고 끈 로그가 경로(`/admin`)를 남겼다. `ADMIN_DISABLED` 로 교체, 예전 이름 잔존 시 기동 실패, 경로 흔적 제거 |
| F-007 | HIGH | REQ-003 · INV-7 | Fix | Fixed | Round 2 · `app/features/{blog,home,reply,sns,user,reports,catalog}/admin.py` · `tests/core/test_admin_pages.py::test_every_admin_view_lists_filters_and_shows_details` · `tests/browser/test_admin_login.py` | `column_filters` 에 모델 컬럼을 그대로 넘겨 sqladmin 0.32 목록 처리가 `AttributeError: ... 'parameter_name'` 로 죽었다 — 로그인 후 **모든 목록 페이지가 500**(7개 뷰 전부, 실제 기동 스모크에서도 재현). 무인증 시절에도 같은 결함이었지만 목록을 여는 테스트가 없어 드러나지 않았다. `BooleanFilter`·`OperationColumnFilter` 로 바꾸고 시각 필터는 뺐다(ADR-009). `scripts/new_app.py` 의 admin 템플릿은 `column_filters` 를 만들지 않아 해당 없음 |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
