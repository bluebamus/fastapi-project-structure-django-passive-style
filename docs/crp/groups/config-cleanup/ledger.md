# Ledger — config-cleanup (결함 원장)

> 모든 finding 의 **영구 기록**. 분류: **Fix** / **Accept-out-of-scope** / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|
| F-001 | LOW | REQ-001 ① · INV-1 | Fix | Fixed | Round 1 · `config.py` · `.env.example` · `tests/core/test_settings_contract.py` | `SMTPSettings`(8필드)·`UploadSettings`(7필드)·`SESSION_EXPIRE_SECONDS` 를 읽는 운영 코드가 없었다(AST 조사로 확인). `SMTP_PASSWORD` 는 배포 안전 검사에만 들어 있어 "안 쓰는 메일 비밀번호를 비우라" 는 안내까지 만들었다. fail-on-revert: `config.py` 를 main 으로 되돌리면 계약 테스트 5건 실패, `SESSION_EXPIRE_SECONDS` 한 필드만 되살려도 3건 실패(읽힘 계약·무시 계약·`.env.example` 문서화) |
| F-002 | LOW | REQ-001 ③ · INV-4 | Fix | Fixed | Round 1 · README·ARCHITECTURE·admin-auth-guide·server-lifecycle-guide | 만료 기본값이 README 환경 표·ARCHITECTURE 환경 표·§7 JWT 표·§11.1 #13·admin-auth-guide 운영 표에 흩어져 있었다. README 표 하나로 모으고 나머지는 가리키게 했다(부록 예외 ADR-005) |
| F-003 | LOW | REQ-001 ④ | Accept-out-of-scope | Accepted | ADR-003 | `ApiSettings.API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 도 읽는 곳이 없다 → residual-risk R-001 |
