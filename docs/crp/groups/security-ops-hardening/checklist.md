# Checklist — security-ops-hardening (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 · 계획 · 조사
- [x] 요청을 design-baseline §2(REQ-001)에 기록 + 이전 요구 충돌 확인 — log-redaction-fixes ADR-002(원문 저장 유지)·admin-login ADR-009(시각 필터 제외 이유)·service-hardening ADR-012(태스크 자동 발견)와 일치
- [x] 그룹 6파일 작성
- [x] 조사 — 엔진 생성 지점 grep(4곳, `hide_parameters` 없음), sqladmin 0.32 `Admin.login`(GET 은 컨텍스트 없이 렌더)·`ModelView.list`(연산 필터 분기)·`OperationColumnFilter` 소스, Celery `Beat.init_loader`(include import 후 일정 읽기)·`add_periodic_task`

## Round 1 — 2026-10-19 · 구현 · 검증
- [x] (F-001) `ENGINE_SAFETY_OPTIONS` 정본 + 4개 생성 지점 · 무결성 오류·로그 출력·엔진 객체·AST 생성 지점 테스트 · fail-on-revert
- [x] (F-002) `ACCESS_LOG_RETENTION_DAYS` · 배치 삭제(리포지토리)·정책(서비스)·provider 주입 · 태스크 + beat 일정 · 경계·배치·0·설정·일정·조립 테스트 · MySQL 마커 1건(수집만) · fail-on-revert
- [x] (F-003) `AdminLoginCsrf` · 템플릿 전역 함수·hidden 입력 · 토큰 없음/틀림/다른 세션 403·카운터 무증가·자격 확인 없음·회전·재시도·상수 시간 테스트 · 기존 로그인 통합·browser·mysql 테스트에 토큰 · fail-on-revert
- [x] (F-004) `LocalDateFilter` + 날짜 입력 템플릿 · 관리 뷰 7개 · 경계·연산 3종·잘못된 입력·빠른 선택 테스트 · 모든 뷰 목록+날짜 필터 200 · fail-on-revert
- [x] 문서 — README(특징·환경 표·관리 화면·운영 체크리스트), ARCHITECTURE(§1.3·§4.3·§4.7·§6·§8·§9·§11.1 #14·§11.3·§12), DEVELOPMENT(§4.4 beat·§4.5 관리 화면), 관리 화면 인증 가이드(비교 표·로그인 시퀀스·실패 경로·쿠키·위협 모델·남은 위험·코드 줄), 서버 수명주기 안내서 설정 부록, 이전 그룹 residual-risk 덧붙임
- [x] 검사 — run-log Round 1
