# Checklist — admin-login (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-12 · 계획
- [x] 요청을 design-baseline §2(REQ-001)에 기록 + 이전 요구 충돌 확인 — service-hardening ADR-020(관리 화면 인증 영구 비목표)을 ADR-001·ADR-004 로 대체
- [x] 그룹 6파일 작성(design-baseline·charter·checklist·ledger·residual-risk·run-log)
- [x] sqladmin 0.32 코드 확인 — `AuthenticationBackend`(부모 생성자가 쿠키 옵션 없는 `SessionMiddleware` 생성), `Admin.login`(False → 400 재렌더, Response → 그대로), `ChoiceLoader` 순서(`templates_dir` 우선)

## Round 1 — 2026-10-12 · 관리 로그인 · Bootstrap 화면 · 배포 전 할 일
- [x] (F-001) `AdminAuthBackend`·`AdminSessionCookie`·`AdminLoginLimits`, 자격 확인 훅, `UserAdminCredentials`, `AuthConfig.ready()` 등록, `verify_credentials` 추출, `create_admin` 주입 · fail-on-revert
- [x] (F-002) `ADMIN_UNAUTHENTICATED_ACK`·`_guard_unauthenticated_admin`·기동 WARNING 제거, 잔존 시 기동 유지 · fail-on-revert
- [x] (F-003) `app/templates/admin/sqladmin/login.html` — Bootstrap 5.3.8 SRI(jsDelivr·npm tarball 대조) · fail-on-revert
- [x] (F-004·F-005) 배포 전 할 일 5항목 — README·`.env.example`·config 주석·ARCHITECTURE·DEVELOPMENT·HTML 안내서·리비전 docstring·`ClientIPResolver`·`create_superuser`
- [x] `itsdangerous` 추가(ADR-007), `uv lock --check`
- [x] mysql·browser 테스트 작성·수집 확인(실행은 CI)

## Round 2 — 2026-10-12 · ADMIN_DISABLED · 세션 범위 · 가이드 · 목록 500
- [x] (F-006) `ADMIN_DISABLED`, `validate_removed_settings`, `create_app(admin_disabled=…)`, 경로 없는 비활성 로그, 응답·헤더 무흔적 테스트 · fail-on-revert
- [x] 세션 범위 확인(ADR-006) — 메인 앱 무세션·API 가 관리 쿠키 거부·`/admin` 밖 Set-Cookie 없음 테스트, 쿠키 이름 충돌 가드 · fail-on-revert
- [x] `docs/guides/admin-auth-guide.html`(도식 7개 — 구성도·주입·기동 흐름·로그인 시퀀스·요청별 판정·로그아웃·계정 수명주기, Chromium 렌더 확인) + 문서 계약 테스트 등록
- [x] (F-007) `column_filters` → `sqladmin.filters`, 모든 뷰 목록·필터·상세 200 테스트, browser 테스트·기동 스모크에서 목록 확인 · fail-on-revert
- [x] 모든 문서 반영 + 낡은 서술 grep(결과는 run-log)
- [x] GATE 3 인수기준 그린 — `.env` 없는 클론에서 1052 passed · 34 deselected · skip 0 · coverage 96.37%
- [x] service-hardening R-001·ADR-020·C-13·INV-12 상태 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
