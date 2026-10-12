# Ledger — service-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> 출처의 `R-xx` 는 2026-10-07 전체 검수 보고서(로컬 `docs/review/2026-10-07/`, 커밋하지 않음)의
> 지적 번호다. 그 보고서의 R-11~R-14 는 orm-raw-repository F-033~F-035 로 이미 해소돼 여기 없다.
> "제안 N" 은 2026-10-12 사용자 요청(REQ-001)의 제안 번호다.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | C-7 (잠금 읽기는 writer) | Fix | Open | 단계 A3 | 출처 R-08. `router.py` 의 `_is_write`·`_statement_is_readable` 이 `Select` 를 항상 읽기로 봐서 ORM `with_for_update()` 가 replica 로 가고 읽기 전용 세션에서도 통과했다 |
| F-002 | MED | C-8 (결정적 목록 순서) | Fix | Open | 단계 A3 | 출처 R-10(앞부분). `BaseRepository.get_all` 에 ORDER BY 가 없고, 접속 로그 조회는 `created_at desc` 단일 키라 동률에서 페이지가 겹친다 |
| F-003 | LOW | C-6 (DSN 은 URL 로 조립) | Fix | Open | 단계 A2 | 출처 리뷰 Low "DSN 의 비밀번호를 URL 인코딩하지 않음". `@ : / # ?` 가 든 비밀번호가 다른 호스트·계정으로 해석되고 `%` 는 Alembic 보간 오류 |
| F-004 | LOW | C-15 (CI 락 검사) | Fix | Open | 단계 A1 | 출처 제안 1. `uv sync --frozen` 은 락을 검사하지 않는데 주석은 "어긋나면 실패" 라고 적었다 |
| F-005 | MED | 계약: 목록 응답의 total 은 items 와 같은 조건이다 | Fix | Open | 단계 B7 | 출처 R-10(뒷부분). catalog `active_only=true` 의 total 이 전체 개수 |
| F-006 | MED | C-12 · 접속 로그 무결성 | Fix | Open | 단계 B3 | 출처 R-03. 긴 헤더·쿠키 하나로 MySQL strict 1406 → 미들웨어가 삼켜 기록이 빠진다 |
| F-007 | MED | 위협 모델: 헤더 위조 | Fix | Open | 단계 B1 | 출처 R-04. `X-Forwarded-For`/`X-Real-IP` 를 무조건 믿어 기록 IP 가 위조된다 |
| F-008 | MED | 접속 로그 무결성 | Fix | Open | 단계 B2 | 출처 R-05. 처리되지 않은 예외로 끝난 요청(500)이 기록되지 않는다 |
| F-009 | MED | 계약: 클라이언트 입력 오류는 4xx | Fix | Open | 단계 B4·B5 | 출처 R-06. PATCH 의 명시적 null 이 MySQL 1048 → 500 |
| F-010 | LOW | 계약: 클라이언트 입력 오류는 4xx | Fix | Open | 단계 B6 | 출처 리뷰 Low. `end_date=9999-12-31` 이 `OverflowError` → 500 |
| F-011 | LOW | C-12 (민감 값 비저장) | Fix | Open | 단계 B2 | 출처 리뷰 Low. 원본 query_string(토큰 등)을 그대로 저장 |
| F-012 | MED | orm-raw-repository C-2·C-3 (registry 단일 출처) | Fix | Open | 단계 B7 | 출처 R-15. lifespan 이 주입된 registry 를 무시하고 `populate()` 가 다른 목록에도 조용히 반환 |
| F-013 | LOW | 운영 로그 품질 | Fix | Open | 단계 B7 | 출처 리뷰 Info. 4xx 를 ERROR 로 기록 |
| F-014 | MED | C-1 · orm-raw-repository C-1 | Fix | Open | 단계 C1 | 출처 R-19. 엔드포인트 테스트 override 가 `mark_read_only` 를 우회 |
| F-015 | MED | C-1 | Fix | Open | 단계 C2 | 출처 R-20. tz·마이크로초·strict·collation 의 MySQL 방언 검증 0건 |
| F-016 | MED | C-1 (테스트 신뢰성) | Fix | Open | 단계 C3 | 출처 R-21. import 시점 설정 객체 patch 가 `importlib.reload` 순서에 의존 |
| F-017 | MED | C-9 (UTC 저장) | Fix | Open | 단계 D | 출처 R-09. `DateTime(timezone=True)` 가 MySQL 에서 tz·마이크로초를 잃는다 |
| F-018 | MED | C-14 (워커의 앱 탈착성) | Fix | Open | 단계 E2 | 출처 R-16. `app/celery/tasks.py` 가 home 을 직접 import |
| F-019 | MED | C-10 (Redis 필수의 근거) | Fix | Open | 단계 E1 | 출처 R-18. API 가 Redis 를 ping 만 하고 쓰지 않는다 — 필수 결정(ADR-011)과 실제 사용(F1)으로 해소 |
| F-020 | MED | 위협 모델: refresh 탈취·크리덴셜 스터핑 | Fix | Open | 단계 F1 | 출처 R-07. refresh 회전·폐기, 로그인 레이트 리밋, iss/aud·필수 claim 검사가 없다 |
| F-021 | LOW | 위협 모델: 크리덴셜 스터핑 | Fix | Open | 단계 F1 | 출처 리뷰 Low. bcrypt 72바이트 조용한 절단 — Argon2 이전으로 해소 |
| F-022 | HIGH | 위협 모델: IDOR · 무인증 쓰기 | Fix | Open | 단계 F2 | 출처 R-01. 사용자 CRUD 가 무인증이라 누구나 계정을 비활성화·삭제할 수 있다 |
| F-023 | MED | 위협 모델: 이름 선점 | Fix | Open | 단계 F2 | 출처 R-02. user API 가 비밀번호 없는 계정을 만든다 |
| F-024 | LOW | 접속 로그 무결성 | Fix | Open | 단계 F2 | 출처 리뷰 Low. `request.state.user_id` 를 채우는 코드가 없어 by-user 조회가 항상 빈 목록 |
| F-025 | LOW | 위협 모델: 로그 유출 | Fix | Open | 단계 F2 | 출처 리뷰 Low. 접속 로그 조회가 무인증 |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
