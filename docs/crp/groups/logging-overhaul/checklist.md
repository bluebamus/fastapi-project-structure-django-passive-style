# Checklist — logging-overhaul (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 · 현재 흐름 조사
- [x] 요청을 design-baseline §2(REQ-001)에 기록, 그룹 6파일 작성
- [x] 현재 로그 흐름 조사(`app/utils/logs/*`·`main.py`·uvicorn CLI·Celery 수신자·`LogSettings`) — run-log Round 0

## Round 1 — 2026-10-19 · 구현 (브랜치 `feat/logging-overhaul`)
- [x] (L1) 모든 경로 같은 구성 — uvicorn 로거 root 전파, `setup_uvicorn_logging()` = `build_dictconfig()`, `--no-access-log` 유지, Celery `--logfile` 존중
- [x] (L2) 헤더 표 — `_app_from_path(pathname, logger_name)`
- [x] (L3) 필수 필드 검사
- [x] (L4) `LOG_APP_LEVELS` + `AppLevelFilter` + 모르는 헤더 경고
- [x] (L5) 프로세스별 파일 + 에러 파일 분리(ADR-003), 지운 키 무시 계약
- [x] (L6) `DailySizeRotatingFileHandler` + `LOG_RETENTION_DAYS`
- [x] (L7) DSN 계정명 가리기, `LOG_REDACTED_SETTINGS` 원문 가리기(4글자 미만 규칙), 계약 테스트
- [x] (F-001) 실기동 스모크에서 워커 import 중 줄이 `app.log` 로 가는 것 발견 → `entry_process()` · TDD
- [x] (F-002) beat 와 워커가 `celery.log` 를 함께 회전시키는 문제 → `celery-beat*.log` · TDD
- [x] (F-004, 감독자 추가 확인) DSN 의 빈 계정명·계정명만·`@`/`:` 가 든 비밀번호 고정 · TDD · fail-on-revert
- [x] fail-on-revert 기록 — run-log Round 1
- [x] (L8) README 로깅 절·업그레이드 노트, ARCHITECTURE §5·§12, DEVELOPMENT §1, server-lifecycle 부록, `.env.example`, 이전 그룹 residual-risk 덧붙임
- [x] GATE 3 — run-log Round 1 검사
