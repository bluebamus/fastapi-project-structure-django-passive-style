# Checklist — log-redaction-fixes (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-13 · 계획 · 재현
- [x] 요청을 design-baseline §2(REQ-001)에 기록 + 이전 요구 충돌 확인 — orm-raw-repository ADR-010(traceback 은 끄지 않는다)과 일치, 접속 로그 원문은 결정으로 유지
- [x] 그룹 6파일 작성(design-baseline·charter·checklist·ledger·residual-risk·run-log)
- [x] 재현 — 프로젝트 dictConfig 로 비밀값이 든 체인 예외의 `logger.exception` 출력에 비밀값이 남음, `DELETE /health` 405 에 `Allow` 없음
- [x] 핸들러 경로 조사 — 앱 root(console·file·error_file), uvicorn 직접 실행(`setup_uvicorn_logging`)·CLI(uvicorn 자체 설정), Celery(root 교체), 외부 로거(sqlalchemy 는 root 전파)
- [x] DEBUG 500 응답 본문의 `str(exc)` 경로 확인 — 없음(`general_exception_handler` 가 DEBUG 에서도 detail 을 비운다)

## Round 1 — 2026-10-13 · 가리기 · 예외 헤더 · Redis 버전 · 엔드포인트 보호 조사
- [x] (F-001) `SecretRedactor`·`install_record_redaction`, `configure_logging()` 설치, 핸들러 경로별 테스트(체인·`stack_info`·진단 정보 유지) · fail-on-revert
- [x] (F-002) `StarletteHTTPException` 핸들러 `headers=exc.headers`, 405 `Allow`·임의 헤더·본문 형식 테스트 · fail-on-revert
- [x] (F-003) `REDIS_MIN_VERSION`·`ensure_redis_version`·lifespan 호출, 거부·통과·경고·fakeredis·명령 대조 계약 테스트 · fail-on-revert
- [x] (F-003) README·`.env.example`·ARCHITECTURE·DEVELOPMENT·서버 수명주기 안내서·compose·CI 주석·`rate_limit`·`refresh_store` docstring 의 버전 서술을 7.0 으로
- [x] 접속 로그 원문 저장 유지 결정 기록(ADR-002, R-001) + service-hardening R-007 표시 — 코드·테스트 무변경
- [x] 엔드포인트 보호 현황 조사(읽기 전용) — 결과는 run-log Round 1

## Round 2 — 2026-10-13 · 커버리지 하한 기본 0 (REQ-002)
- [x] (F-004) `fail_under = 0` + 주석, 계약 테스트(단일 정본·값 0·게이트/CI 명령줄 무하한·CI 측정) · fail-on-revert
- [x] DEVELOPMENT §6.1(올리는 법)·ARCHITECTURE NFR-08·README 테스트 절·CI 주석·게이트 단계 설명
- [x] orm-raw-repository ADR-038 ② 값 대체 표시
- [x] GATE 3 인수기준 그린 — `.env` 없는 사본에서 1089 passed · 34 deselected · skip 0 · coverage 96%

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
