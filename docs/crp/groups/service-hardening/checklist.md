# Checklist — service-hardening (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다. 단계는 design-baseline §2-1 의 D-A1 ~ D-F2 와 같다.

## Round 0 — 2026-10-12 · 계획
- [x] 이번 요청을 design-baseline §2(REQ-001)에 기록 + 이전 요구 충돌 확인 — 인증 비목표 3곳을 ADR-021 로 대체, 두 그룹 design-baseline 에 상태 한 줄 append
- [x] 그룹 6파일 작성(design-baseline·charter·checklist·ledger·residual-risk·run-log)
- [x] 리뷰 지적을 ledger F-001~F-025 로 등록

## Round 1 — 2026-10-12 · 단계 A (CI 재현성 · DSN · 잠금 읽기 · 정렬)
- [x] (F-004) A1 — CI `uv sync --frozen` → `--locked`(gate·mysql job), 주석·DEVELOPMENT.md 정정, 계약 테스트 · fail-on-revert. `scripts/review_gate.py` 는 `rglob` 으로 작업 트리를 훑지 않아 파일 목록 교체 대상 없음
- [x] (F-003) A2 — DSN `URL.create()`, 마스킹 `render_as_string`, Alembic `%%`, Redis 비밀번호 인코딩, 문자열 비교 테스트를 의미 비교로 · fail-on-revert
- [x] (F-001) A3 — ORM `with_for_update()` 를 쓰기로 판정(라우터 writer, read-only 거부), router on/off 테스트 · fail-on-revert
- [x] (F-002) A3 — `get_all` 기본 정렬, 접속 로그 `id desc` 보조 키, 동률 결정성·offset 비중복 테스트 · fail-on-revert. catalog 목록 OpenAPI 설명·문서의 "정렬 없음" 서술 정정
- [x] GATE 3 인수기준(단계 A 분) 그린 — 729 passed · skip 0 · coverage 94.01%
- [x] 요구사항 회귀 0 — C-1~C-15, orm-raw-repository C-22(공개 메서드 8개) 위반 없음
- [x] run-log·residual-risk 갱신

## Round 2 — 2026-10-12 · 단계 B (접속 로그 수집 · 오류 매핑)
- [x] (F-007) B1 — `ClientIPResolver`(`app/core/middlewares/client_ip.py`), `TRUSTED_PROXY_HOPS=0`, 미들웨어 생성자 주입. 기본값의 동작 변경을 ADR-023·`.env.example`·ARCHITECTURE 에 기록 · fail-on-revert
- [x] (F-008·F-011) B2 — 500 기록 후 재전파, 민감 query 마스킹(`ACCESS_LOG_SENSITIVE_QUERY_KEYS`), 세션 쿠키 이름 `SESSION_COOKIE_NAME` · fail-on-revert
- [x] (F-006) B3 — home `UserAccessLogService.create_access_log` 가 `UserAccessLog.__table__` 의 `String(n)` 길이로 자르기 · fail-on-revert
- [x] (F-009) B4·B5 — `app/core/schemas.py` `PatchSchema`(5개 Update 스키마 상속, `nullable_fields` 가 모델 nullable 과 일치하는지 검사), `convert_db_error` 코드별 변환(ADR-024) · fail-on-revert
- [x] (F-010) B6 — 리포트 날짜 1970-01-01..9998-12-31(최대 366일은 기존) · fail-on-revert
- [x] (F-005·F-012·F-013) B7 — catalog total, lifespan 이 주입 registry 사용·populate 목록 불일치 거부, 4xx WARNING(ADR-025) · fail-on-revert
- [x] GATE 3 인수기준(단계 B 분) 그린 — 777 passed · skip 0 · coverage 94.96%
- [x] 요구사항 회귀 0 — C-1~C-15 위반 없음(core→features 0, 기능 간 import 0, 계층 검사 그린)
- [x] run-log·residual-risk 갱신 (R-007·R-008)

## Round 3 — 2026-10-12 · 단계 C (테스트 하네스)
- [x] (F-014) C1 — `tests/session_overrides.py` `sqlite_session_overrides`(writer `using_writer`, read-only `mark_read_only`, `on_session` 훅), 11파일 전환, read-only flush 거부·writer 고정 회귀 테스트, 손 오버라이드 금지 AST 계약 · fail-on-revert
- [x] (F-015) C2 — `tests/integration/test_mysql_orm_smoke.py` 5건(catalog CRUD, 동률 created_at 정렬·페이지, username utf8mb4_unicode_ci 중복 409, NOT NULL None 422, 접속 로그 자르기) 작성 · `-m mysql --collect-only` 수집 확인. 실행 판정은 CI mysql job(skip·xfail 0)
- [x] (F-016) C3 — `test_migration_chain` 호출 시점 patch, 루트 `conftest.py` `restore_config` 스냅샷 복원(security_hardening 3곳·deployment_safety 공용), reload 후 미끼 URL 회귀 테스트 · fail-on-revert
- [x] GATE 3 인수기준(단계 C 분) — 782 passed · skip 0 · coverage 94.96% · 정순(`-p no:randomly`)·파일 역순 모두 그린
- [x] 요구사항 회귀 0 — C-1~C-15 위반 없음(앱 코드 변경 없음, 테스트 하네스만)
- [x] run-log·residual-risk 갱신 (R-009)
- [ ] (F-015) CI mysql job 그린 확인 — 감독자 푸시 후

## Round 4 — 2026-10-12 · 단계 D (UTC 저장)
- [x] (F-017) D1 — `UTCDateTime`(`app/core/models/types.py`, MySQL `DATETIME(6)`, naive 거부, 결과 UTC 부착), `type_annotation_map`·reports `ordered_at`, `TimezoneSettings.utc_now()`·`local_midnight_utc()`, 모델 default/onupdate, Alembic 렌더 훅(`render_item`) · fail-on-revert
- [x] (F-017) D2 — 리비전 `e5a7c2d9f310`(MySQL `DATETIME(6)` + `CONVERT_TZ` KST→UTC, SQLite no-op, downgrade 역변환), head 참조(ARCHITECTURE 체인) 갱신, SQLite `upgrade head`·`alembic check` 드리프트 없음, MySQL 오프라인 SQL 확인
- [x] (F-017) D3 — 리포트 영업일 경계(지역 0시 → UTC 순간)·방언별 일자 버킷(`ponytail:` 고정 오프셋), 접속 로그 날짜 범위를 지역 일자로 · fail-on-revert
- [x] (F-017) D4 — Celery `enable_utc=True`, 응답 스키마 시각 설명 "(UTC, 오프셋 포함 ISO 8601)", catalog 예시 `Z`, API 응답 오프셋 테스트 · fail-on-revert
- [x] (F-015 시각 부분) MySQL 테스트 작성 — `tests/integration/test_mysql_time_policy.py`(DATETIME(6) 정밀도·KST→UTC 마이크로초 왕복·자정 경계 리포트), `test_mysql_migration_roundtrip.py::test_utc_revision_converts_existing_kst_values` · `--collect-only` 31건
- [x] GATE 3 인수기준(단계 D 분) — 805 passed · skip 0 · coverage 95.12%
- [x] 요구사항 회귀 0 — C-1~C-15 위반 없음(C-9 충족, core→features 0, 기능 간 import 0)
- [x] run-log·residual-risk 갱신 (R-010)
- [ ] (F-015) CI mysql job 그린 확인 — 감독자 푸시 후(단계 C·D 테스트 함께)

## Round 5 — 단계 E (Redis 필수 · /ready · Celery 자동 발견)
- [ ] (F-019) E1 — `get_redis`, `/ready` DB·Redis ping
- [ ] (F-018) E2 — `AppConfig.tasks_module`, 워커 include 를 `INSTALLED_APPS` 에서

## Round 6 — 단계 F1 (인증 코어)
- [ ] (F-020·F-021) `PasswordHasher`·`TokenService`·`RefreshTokenStore`·`RateLimiter`·`AuthService`, 엔드포인트, 의존성 추가(`pwdlib[argon2]`, dev `fakeredis`)

## Round 7 — 단계 F2 (인가 · 소유권 · 운영 도구)
- [ ] (F-022~F-025) `Principal`·`OwnershipPolicy`·슈퍼유저, 라우트 정책, `scripts/create_superuser.py`, 문서·OpenAPI 기준선

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
