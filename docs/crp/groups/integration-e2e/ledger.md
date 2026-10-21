# Ledger — integration-e2e (결함 원장)

> 모든 finding 의 **영구 기록**. 분류: **Fix** / **Accept-out-of-scope** / **Wont-fix** / **Decision-needed**(정책 결정 필요 — 멈추고 보고).
> 심각도: CRIT / HIGH / MED / LOW. ID 는 이 그룹 안에서만 유효하다.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | 계획서 L2 미인증 칸 — 401 + `WWW-Authenticate` | Fix | Fixed (`1bf527b`) | `app/core/security/dependencies.py` · `tests/test_authorization_policy.py::test_protected_operation_with_invalid_token_is_401_with_bearer_challenge` | 보호 operation 24개가 토큰 **없을** 때만 `WWW-Authenticate: Bearer` 를 싣고, 위조·만료 토큰의 401 에는 빠졌다(RFC 6750 §3). 모든 보호 라우트가 지나는 `get_current_principal` 한 곳에서 붙인다. 수정 전 단위 24 failed |
| F-002 | MED | L1 회귀(`-m browser`) | Fix | Fixed (`f9756d7`) | `tests/browser/conftest.py` · `tests/browser/test_live_server.py` | 브라우저 하네스가 서버 출력을 `stdout=PIPE` 로 받고 읽지 않아, 파이프가 차면 서버가 로그를 쓰다 멈췄다. Windows 는 9번째 요청에서 멈춰 뒤의 브라우저 테스트 9건이 모두 `goto` 시간 초과로 보였다(원인 가림). 출력은 임시 파일로. 회귀는 300요청(수정 전 ReadTimeout) |
| F-003 | HIGH | REQ-002(W0) | Fix | Fixed (`36cdd9d`) | `tests/browser/conftest.py::server_env` · `tests/browser/test_redis_target.py` · `.github/workflows/ci.yml` · `tests/core/test_dsn.py` | 브라우저 하네스의 Redis 대상이 `REDIS_TEST_PORT` 기본값(6380)으로 묵시적이었다. `REDIS_HOST`·`REDIS_PORT` 가 없으면 접속 전에 `pytest.fail`, 있으면 자식 env 에 명시. CI gate·mysql job 에 두 변수 명시. 그 결과 `REDIS_PORT` 를 명시한 실행에서 기본값(6379)에 기대던 `test_dsn` 의 Redis URL 검사 2건이 갈려 포트를 고정했다. RED 는 접속하지 않는 `server_env()` 호출로 확인(3 failed) — 6379 접속 0 |
| F-004 | HIGH | REQ-003(결정 1) | Fix | Fixed (`fd7d64d`) | `app/core/bootstrap.py` · `tests/core/test_redis_unavailable.py` · e2e L5 | Redis 장애 시 가입·로그인·refresh·logout·사용자 비활성화/삭제가 처리되지 않은 예외 500 — 기록 2건, keep-alive 끊김(e2e 실측). `ConnectionError`·`TimeoutError` 전용 핸들러로 503 `SERVICE_UNAVAILABLE`, 기록 1건, 연결 유지. 수정 전 단위 12 failed(예외가 응답 대신 올라왔다) |
| F-005 | HIGH | REQ-004(결정 2) | Fix | Fixed (`47161ac`) | `app/core/db/router.py` · `tests/core/test_db_replica_fallback.py` · e2e L5 | replica offline 이면 읽기가 `OperationalError`(3032) 500 — 기록 2건, keep-alive 끊김. 읽기 전용 세션의 연결 계열 오류만 primary 로 한 번 재시도 + WARNING(ADR-010). 되돌리면 재시도 테스트 1 failed |
| F-006 | — | REQ-005(결정 3) | Fix(계약 고정) | Verified (`dcfa974`) | `tests/utils/test_log_early_lines.py` · e2e L6 · ADR-011 | 이 저장소에서는 **재현되지 않았다** — 4개 진입 경로 모두 콘솔 줄이 자기 파일에 있다. 코드 변경 없이 계약 테스트로 고정(되돌림 검증: `entry_process` 를 예전 동작으로 바꾸면 워커 경우 실패) |
| F-007 | MED | 계획서 §5-2(CSRF 본문 상한) | Decision-needed | Open | e2e L5 `test_measure_csrf_form_body_buffering` · residual-risk R-001·R-002 | ① 토큰 없는 폼 본문을 전부 메모리에 읽는다 — 50 MiB 에서 최대 RSS +101~109 MiB(본문 + 파싱 사본), 403 까지 0.38초. ② 필드 **하나**가 1 MiB 를 넘으면 Starlette 폼 파서의 필드 상한 예외가 CSRF 미들웨어 안에서 터져 500 + 연결 끊김, 50 MiB 뒤 RSS +54 MiB 가 남는다. 상한·응답 코드(413/400)는 사용자 결정 |
| F-008 | MED | 계획서 L3-8(쓰기 직후 읽기 일관성) | Decision-needed | Open | `tests/e2e/test_l3_scenarios.py::test_me_right_after_register_under_replication_lag` · residual-risk R-003 | 복제가 밀린 상태에서 가입 직후 `/me` 가 **유효한 토큰에 401(AUTH_INVALID_TOKEN)** — `get_current_user` 가 사용자를 replica 에서 다시 읽고 없으면 토큰 무효로 답한다. 클라이언트가 "다시 로그인" 으로 처리하면 로그인 직후 튕긴다. 전체 e2e 에서 primary 장애 회복 직후 1회 실제로 나왔다. 쓰기 세션으로 읽을지·다른 응답을 낼지는 정책 결정 |
| F-009 | LOW | REQ-003 범위 | Decision-needed | Open | e2e L5(`admin-anonymous`) · residual-risk R-004 | 관리 화면 쿠키 없는 첫 요청(예: `GET /admin/login`)은 Redis 장애 때 응답 직전 세션 **저장**이 실패해 500 — 기록 2건·연결 끊김. ARCHITECTURE 가 "응답 직전 저장 실패는 500" 으로 문서화한 현행이고, sqladmin 하위 앱의 미들웨어라 앱 예외 핸들러가 닿지 않는다. 503 으로 바꿀지는 정책 결정 |
| F-010 | LOW | 계획서 L2(422 형식) | Accept-out-of-scope | Observed | e2e L2 관측 | 422 실제 응답은 `ErrorResponse{error_code, message, detail[field,message,type]}` 인데 OpenAPI 는 FastAPI 기본 `HTTPValidationError{detail[loc,msg,type]}` 를 광고한다 — 응답 형식 변경은 정책 결정(residual-risk R-005) |
| F-011 | LOW | 계획서 L2(405) | Accept-out-of-scope | Observed | e2e L2 관측 | 메서드 분할 경로의 405 `Allow` 는 처음 맞은 라우트의 메서드만 싣는다 — 사용자 결정으로 현행 유지(값만 기록) |
| F-012 | LOW | 계획서 L2(미인증) | Decision-needed | Open | e2e L2 관측 · residual-risk R-006 | PublicWrite 인 로그인·refresh·logout 의 자격 오류 401 에는 `WWW-Authenticate` 가 없다(보호 라우트는 F-001 로 붙는다). 붙일지는 정책 결정 |
| F-013 | MED | REQ-006(결정 2) | Fix | Fixed (`8665236`) | `tests/core/test_unhandled_exception.py` | 처리기 없는 예외(버그)는 `Exception` 처리기가 500 을 낸 뒤 `ServerErrorMiddleware` 가 다시 던져 uvicorn 이 `Exception in ASGI application` 으로 한 번 더 기록하고 keep-alive 연결을 닫았다(실제 uvicorn 재현: traceback 2·연결 종료). 가장 바깥 사용자 미들웨어에서 같은 처리기로 끝낸다 |
| F-014 | LOW | REQ-006(의존성) | Fix | Fixed (`ab7f15d`) | `tests/core/test_dsn.py` | `cryptography` 를 직접 선언 — 사용처(드라이버 RSA 인증)와 떨어져 있었다. `aiomysql[rsa]` 로 통일 |

### 상태 갱신 — 2026-10-21 (e2e-policy-2, 원 행은 고치지 않는다)

| ID | 새 Status | 커밋 | 근거 |
|---|---|---|---|
| F-001 | Fixed — 부착 위치를 전역 핸들러(`_challenge`)로 옮김 | `6788468` | 결정 3 |
| F-007 | Fixed — 413(10 MiB)·400(필드 1 MiB) | `6bfc431` | `tests/core/test_admin_csrf.py`·e2e L5 측정 |
| F-008 | Fixed — 인증 사용자 조회 primary | `4743b1c` | `app/features/auth/tests/test_endpoint.py::test_me_reads_the_user_from_primary`·e2e L3 |
| F-009 | Fixed — 응답 직전 저장 실패도 503 | `c3e8280` | `tests/core/security/test_admin_session.py`·e2e L5 |
| F-010 | Fixed — 422 광고 = 실제 본문 | `371d896`·`95ae048` | `tests/test_openapi_contract.py`·e2e L2 단정 |
| F-012 | Fixed — 모든 401 에 도전 헤더 | `6788468`·`62da6f6` | `tests/core/test_exception_headers.py`·e2e L2 단정 |
