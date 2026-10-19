# Checklist — admin-session-hardening (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 · 계획 · 조사
- [x] 요청을 design-baseline §2(REQ-001, 감독자 추가 지시 REQ-002)에 기록 + 이전 요구 충돌 확인 — security-ops-hardening ADR-004(로그인 CSRF)를 넓히고, ADR-006(access 15분)은 그대로, log-redaction-fixes ADR-003(405 헤더 보존)은 그대로
- [x] 그룹 6파일 작성
- [x] 조사 — sqladmin 0.32 소스: 라우트 표(로그아웃 GET 전용, 삭제 DELETE, 생성·수정 GET/POST, 가져오기 POST, `@action` GET), `templates/sqladmin/{base,layout,create,edit,list}.html`·`modals/*`, `statics/js/main.js`(삭제 `$.ajax` DELETE, 가져오기 `fetch`), 템플릿 로더(`sqladmin_original/` 접두사), `_queries._update_async`(`on_model_change` 는 속성 적용 전), `AuthenticationBackend.__init__`(서명 세션), `itsdangerous` 소비처 grep

## Round 1 — 2026-10-19 · 구현 · 검증
- [x] (F-001) `AdminSessionStore`·`RedisSessionMiddleware` · 설정 2개·검증 · 백엔드 미들웨어 교체 · 회전 · 503 · 테스트 · fail-on-revert
- [x] (F-002) `AdminCsrf`·`AdminCsrfMiddleware`(로그인 검사 통합)·`require_post_logout` · `base.html` 확장(meta·스크립트) · 원본 대조 테스트 · 요청별 403/정상·헤더/폼·다른 세션 토큰 · browser 생성·삭제·로그아웃(수집만) · fail-on-revert
- [x] (F-003) API·관리 화면(전후 비교)·`create_superuser --set-password` 폐기 · 자기 강등 · Redis 오류 비은닉 · fail-on-revert
- [x] (F-004) `between` 연산·템플릿·빠른 선택 · 경계·DST·열린 구간·역순·형식 오류·모든 뷰 좁혀짐 · fail-on-revert
- [x] `itsdangerous` 직접 의존 제거(`uv remove`)
- [x] 실기동 스모크(uvicorn lifespan off + SQLite + fakeredis + Chromium) — run-log Round 1
- [x] 문서 — README·ARCHITECTURE·DEVELOPMENT·관리 화면 인증 가이드·서버 수명주기 안내서 부록·이전 그룹 residual-risk 덧붙임·review 문서 2개(로컬, 커밋 안 함)
- [x] 검사 — run-log Round 1

## Round 2 — 2026-10-19 · 감독자 정정(REQ-003) · 구현 · 검증
- [x] (F-006) `UserSessionRevoker`(refresh + 관리 세션) · API·관리 화면 같은 집합 · 관리 화면 폐기를 커밋 전 훅(`on_model_change`·`on_model_delete`)으로 · 폐기 실패 시 수정·삭제가 커밋되지 않음 · fail-on-revert
- [x] 문서 — 가이드 폐기 표·시퀀스, ARCHITECTURE·DEVELOPMENT 폐기 서술, residual-risk R-005·R-007
- [x] 검사 — run-log Round 2
