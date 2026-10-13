# Checklist — access-policy (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-13 · 계획 · 조사
- [x] 요청을 design-baseline §2(REQ-001)에 기록 + 이전 요구 충돌 확인 — service-hardening C-11(인가 경로 core 하나)·admin-login ADR-001(`/admin` 세션 인증)과 일치
- [x] 그룹 6파일 작성
- [x] 현재 판정 조사 — 가드 초안을 `main.app` 에 돌려 선언 없는 라우트 15개(공개 GET 8·auth 쓰기 4·health·ready·docs) 확인

## Round 1 — 2026-10-13 · 구현 · 검증
- [x] (F-001) `access.py` 접근 수준 4개·`AccessPolicyGuard`, `create_app()` 8단계 `verify` · 가드 단위·앱 단위 테스트 · fail-on-revert
- [x] (F-002) 예시 뷰·health·ready·docs 선언, home·reports·catalog·user 의 슈퍼유저 선언을 뷰 단위로 · 회귀 표 대조 · fail-on-revert
- [x] (F-003) 스캐폴드 `/ping` 에 `Public` + 템플릿 주석 · 생성물 가드 통과 테스트 · fail-on-revert
- [x] (F-004) 권한표 테스트 정리(표 한 벌, 가드 판정 대조)
- [x] 문서 — README 권한 절, ARCHITECTURE §7.1, DEVELOPMENT §2.8·§2.9·§4.5(감싸는 데코레이터를 쓰지 않는 이유), 관리 화면 인증 가이드 비교 표, 기능 개발 가이드 라우터 예시
- [x] 검사 — ruff·format·mypy·bandit·인프라 제외 pytest(`.env` 없는 사본)·OpenAPI fail-on-revert·browser 수집
