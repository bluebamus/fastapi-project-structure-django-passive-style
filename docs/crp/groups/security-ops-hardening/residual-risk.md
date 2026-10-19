# Residual Risk — security-ops-hardening (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 로그인 이후 sqladmin 이 그리는 생성·수정·삭제 폼과 GET `/admin/logout` 에는 CSRF 토큰이 없다 | LOW | charter 2-1·2-3 — 이 폼들은 sqladmin 템플릿이다. `admin_session` 은 `SameSite=Strict`·`Path=/admin` 이라 다른 사이트에서 시작한 요청에 실리지 않는다(1차 방어). 로그인 폼만 토큰을 확인한다(ADR-004) | 2026-10-19 | SameSite 미지원 클라이언트를 지원하거나 관리 화면을 다른 사이트에 임베드해야 하면 — sqladmin 폼 템플릿에 같은 `csrf_token(request)` 를 싣고 미들웨어로 확인 |
| R-002 | 보존 삭제는 Celery beat 가 떠 있어야 돈다 — beat 를 띄우지 않은 배포에서는 접속 로그가 계속 쌓인다 | LOW | ADR-003 — API 프로세스는 worker·beat 를 띄우지 않는다(소유권이 다른 프로세스). README·ARCHITECTURE §11.1 #14 에 배포 확인 항목으로 올렸다 | 2026-10-19 | beat 없이 배포하는 환경이 생기면 — 배포 측 cron 으로 같은 태스크를 보내거나 운영 명령을 추가 |
| R-003 | 관리 세션은 서명 쿠키다 — 서버 측 강제 로그아웃·세션 목록이 없다(admin-login R-001 과 같은 항목) | LOW | 비목표(charter 2-3). **Redis 이전은 사용자 결정 대기** | 2026-10-19 | 사용자가 관리 세션의 Redis 이전을 결정하면 |
| R-004 | access 토큰 15분과 "권한 회수는 토큰 만료까지 지연"(service-hardening R-002·R-014) | LOW | **사용자 결정으로 수용(2026-10-19, ADR-006)** — 원문 "15분 유지한다" | 2026-10-19 | 사용자가 즉시 회수를 요구하면 — access 수명 단축 또는 권한 버전 claim + Redis 대조 |
| R-005 | 날짜 필터의 빠른 선택은 "오늘·최근 7일·최근 30일" 을 고정 링크로 준다(임의 기간 `from`+`before` 조합은 한 필터로 동시에 걸 수 없다) | LOW | ADR-005 — sqladmin 연산 필터는 파라미터 하나·연산 하나다. 같은 날·이후·이전과 빠른 선택으로 요청 범위를 덮는다 | 2026-10-19 | 임의 기간(시작~끝) 필터가 요구되면 — 같은 컬럼에 두 번째 `LocalDateFilter(parameter_name=...)` 를 단다 |

## 최종 상태 (2026-10-19, Round 1 · 그룹 CONVERGED)

수용 항목은 R-001~R-005 — 모두 비목표 또는 사용자 결정·배포 사실에 근거한 의도적 수용이다.

## 상태 갱신 (2026-10-19, admin-session-hardening)

> append-only — 위 표의 행은 그대로 두고 상태만 여기에 덧붙인다. 결정 정본은 `docs/crp/groups/admin-session-hardening/design-baseline.md`.

- **R-001 — 해소 — admin-session-hardening ADR-002·ADR-003.** `AdminCsrfMiddleware` 가 `/admin` 아래 POST·PUT·PATCH·DELETE 전부(로그인 포함)의 토큰을
  세션 토큰과 대조하고, 덮어쓴 `app/templates/admin/sqladmin/base.html` 이 생성·수정 폼(hidden)·삭제·가져오기(헤더)에 토큰을 싣는다.
  로그아웃은 POST 전용 + 토큰이다(`require_post_logout`, GET 405). 남은 구멍은 사용자 정의 `@action`(GET) — admin-session-hardening R-001.
- **R-003 — 해소 — admin-session-hardening ADR-001·ADR-005.** 관리 세션은 Redis 서버 세션이다. 로그아웃·비활성화·강등·삭제·비밀번호 변경 시
  서버에서 즉시 지운다(`AdminSessionStore.revoke_user`). 사용자 결정은 "방법 2: Redis 서버 세션"(2026-10-19).
- **R-005 — 해소 — admin-session-hardening ADR-004.** `LocalDateFilter` 에 기간 연산(`between`, 값 `YYYY-MM-DD~YYYY-MM-DD`, 양 끝 포함, 한쪽만이면
  열린 구간)이 생겼고, 빠른 선택 "최근 7일·30일" 도 이 연산으로 표현한다.
