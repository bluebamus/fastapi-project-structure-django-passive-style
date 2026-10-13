# Ledger — log-redaction-fixes (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001 ① · C-1 | Fix | Fixed | Round 1 · `app/utils/logs/redaction.py` · `app/utils/logs/setup.py` · `tests/utils/test_log_redaction.py` | **재현:** 프로젝트 dictConfig 로 `logger.exception` 에 DSN(`mysql+asyncmy://u:secret42@h/db`)·`password=secret42`·`Authorization: Bearer …` 가 든 체인 예외를 남기면 출력에 그대로 남았다(메시지·traceback 모두). 저장소에 로그 메시지 마스킹 자체가 없었다(SQL 은 `SqlNoiseFilter`, DB 예외는 `convert_db_error` 가 막지만 그 밖의 예외·메시지는 열려 있었다). uvicorn CLI·Celery 는 우리 포매터를 쓰지 않는 경로라 같은 규칙이 닿지 않았다. LogRecord factory 로 닫았다. fail-on-revert: `setup.py` 를 main 으로 되돌리면 핸들러 경로 6건 실패 |
| F-002 | MED | REQ-001 ③ · C-3 | Fix | Fixed | Round 1 · `app/core/bootstrap.py` · `tests/core/test_exception_headers.py` | **재현:** `DELETE /health` → 405, `Allow` 없음(리뷰 M-03). `StarletteHTTPException` 핸들러가 `exc.headers` 를 버렸다. fail-on-revert: 3건 실패(405 `Allow`·401/418 임의 헤더) |
| F-003 | MED | REQ-001 ④ · C-4 | Fix | Fixed | Round 1 · `app/core/redis.py` · `app/core/resources.py` · `tests/core/test_redis_version.py` · README·ARCHITECTURE·가이드·compose·CI 주석 | 최소 Redis 버전이 코드 어디에도 정의되지 않았고 기동이 확인하지 않았다. 리뷰 문서·이전 서술은 GETDEL 만 보고 "6.2 이상" 이라 했으나 `rate_limit.py` 의 `EXPIRE NX` 는 7.0 부터다 — 6.x 에서는 로그인·가입 레이트 리밋이 첫 요청부터 500. fail-on-revert: `resources.py` 되돌림 → lifespan 거부 테스트 실패, 상수를 (6, 2) 로 바꾸면 3건 실패(6.2.14 거부·lifespan·명령 대조 계약) |
| F-004 | LOW | REQ-002 · C-5 | Fix | Fixed | Round 2 · `pyproject.toml` · `tests/scripts/test_gates.py` · DEVELOPMENT §6.1 · ARCHITECTURE NFR-08 · README | 사용자 결정으로 기본 하한을 0 으로. 85 를 고정하던 계약 테스트와 orm-raw-repository ADR-038 ② 의 값을 갱신했다. fail-on-revert: pyproject 를 main(85)으로 되돌리면 `test_coverage_threshold_has_one_source` 실패 |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
