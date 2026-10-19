# Residual Risk — admin-login (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은 "새 결함"이
> 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 서버 측 세션 저장소가 없다 — 로그아웃 전에 복사해 둔 `admin_session` 은 만료(8시간)까지 서명이 유효하고, 계정이 활성 슈퍼유저로 남아 있으면 그 복사본으로 들어올 수 있다 | LOW | charter §2-4 비목표. 권한은 매 요청 DB 로 보므로 강등·비활성화·삭제로 즉시 끊을 수 있고, `SESSION_SECRET_KEY` 교체로 전원을 끊을 수 있다(관리 화면 인증 가이드 §7·§10) | 2026-10-12 | 강제 로그아웃·세션 목록 요구가 생기면 — Redis 세션 저장소로 교체 — **(2026-10-19)** Redis 세션 저장소 이전은 사용자 결정 대기(security-ops-hardening R-003) |
| R-002 | 로그인 폼에 CSRF 토큰이 없다 | LOW | `SameSite=Strict` 쿠키라 교차 사이트 요청에는 세션이 실리지 않는다. 로그인 CSRF 는 공격자가 슈퍼유저 계정을 가져야 의미가 있다 | 2026-10-12 | SameSite 를 지원하지 않는 클라이언트를 지원해야 하거나 관리 화면을 다른 도메인에서 임베드해야 하면 — **해소 (2026-10-19, security-ops-hardening ADR-004·F-003)**: 로그인 폼이 세션 동기화 CSRF 토큰을 싣고, 없거나 다르면 레이트 리밋·자격 확인 전에 403. 로그인 이후 sqladmin 폼·GET 로그아웃은 security-ops-hardening R-001 로 이어진다 |
| R-003 | 관리 화면 안에 세분 권한이 없다 — 슈퍼유저면 모든 뷰·동작이 열린다 | LOW | charter §2-4 비목표(service-hardening R-006 과 같은 축). 사용자 생성은 막혀 있고 해시는 어디에도 나오지 않는다 | 2026-10-12 | 운영자 역할을 나눠야 하면 — `ModelView.is_accessible` 로 DB 판정 |
| R-004 | 예전 `ADMIN` 잔존 검사는 `ENV=test` 에서 돌지 않는다 | LOW | ADR-005 — `validate_env_source` 와 같은 기준(pytest 가 ENV=test 를 준다). 개발자 로컬 `.env` 의 잔존이 테스트 전체를 막지 않게 한다. 검사 함수 자체는 단위 테스트가 본다 | 2026-10-12 | 테스트 환경에서도 잔존을 막아야 하면 |
| R-005 | 로그인 화면 스타일은 jsDelivr CDN 에 의존한다 — 오프라인·CDN 차단·SRI 불일치면 스타일 없이 그려진다(로그인은 동작한다) | LOW | ADR-003 — 정적 파일을 저장소에 넣지 않는다. SRI 로 변조는 막는다 | 2026-10-12 | 폐쇄망 배포가 생기면 — CSS 를 정적 파일로 동봉 |
| R-006 | 관리 목록의 시각 컬럼(`created_at` 등)은 필터가 없다(정렬은 된다) | LOW | ADR-009 — sqladmin 의 연산 필터가 `UTCDateTime`(TypeDecorator)을 날짜로 인식하지 못해 문자열을 바인딩한다 | 2026-10-12 | 기간 필터가 필요하면 — UTC 변환을 하는 필터 클래스 추가 — **해소 (2026-10-19, security-ops-hardening ADR-005·F-004)**: `LocalDateFilter`(지역 날짜 → UTC 범위)를 `created_at` 이 있는 모든 관리 뷰에 달았다 |
| R-007 | 관리 로그인 레이트 리밋의 IP 정확도는 `TRUSTED_PROXY_HOPS` 에 달렸다 | MED | service-hardening R-013 과 같은 설정. 배포 체크리스트 항목(README·ARCHITECTURE §11.1 #10·가이드 §11) | 2026-10-12 | 신뢰 프록시를 CIDR 로 지정하는 요구가 생기면 |

## 최종 상태 (2026-10-12, Round 2 · 그룹 CONVERGED)

수용 항목은 R-001~R-007 이고, 모두 비목표(charter §2-4) 또는 배포 사실에 근거한 의도적 수용이다.

## 상태 갱신 (2026-10-19, admin-session-hardening)

> append-only — 위 표의 행은 그대로 두고 상태만 여기에 덧붙인다. 결정 정본은 `docs/crp/groups/admin-session-hardening/design-baseline.md`.

- **R-001 — 해소 — admin-session-hardening ADR-001·ADR-005.** 관리 세션을 Redis 서버 세션으로 옮겼다(쿠키 `admin_session` 에는 무작위 세션 ID 만,
  내용은 Redis `admin:sess:{HMAC}`). 로그아웃하면 Redis 키가 지워져 복사해 둔 쿠키도 즉시 무효이고, 비활성화·강등·삭제(API·관리 화면)와
  `scripts/create_superuser.py --set-password` 는 그 사용자의 관리 세션을 모두 지운다. 절대 만료 8시간(`ADMIN_SESSION_MAX_AGE_SECONDS`, 연장 불가)에
  미사용 만료 30분(`ADMIN_SESSION_IDLE_SECONDS`)이 더해졌다. 남은 관련 위험은 admin-session-hardening R-003·R-005·R-008 이다.
- **R-002 — 보강 — admin-session-hardening ADR-002·ADR-003.** 로그인 폼 토큰(security-ops-hardening ADR-004 로 해소)에 이어 로그인 이후 상태를 바꾸는
  모든 관리 요청(생성·수정·삭제·일괄 삭제·가져오기·로그아웃)도 CSRF 토큰을 요구한다(`AdminCsrfMiddleware`, 검사는 한 곳). 로그아웃은 POST 전용(GET 405).
  보호 밖은 사용자 정의 `@action`(GET) 뿐이다 — admin-session-hardening R-001.
- **R-006 — 보강 — admin-session-hardening ADR-004.** security-ops-hardening 이 단 `LocalDateFilter` 에 기간 연산(`S~E`, 양 끝 포함)이 더해져
  필터 하나로 시작일~종료일을 지정할 수 있다.
- R-007 의 "가이드 §11" 은 관리 화면 인증 가이드 재구성으로 §14(운영)가 됐다.
