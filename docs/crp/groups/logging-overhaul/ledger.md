# Ledger — logging-overhaul (결함 원장)

> 모든 finding 의 **영구 기록**. 분류: **Fix** / **Accept-out-of-scope** / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 ⑤ · INV-5 | Fix | Fixed | Round 1 · `app/utils/logs/setup.py`(`entry_process`) · `test_import_time_lines_of_worker_go_to_worker_files` | 실기동 스모크: `celery -A app.celery.app worker` 가 `setup_logging` 시그널 전, 모듈 import 중(`[database] 라우팅 구성`) 줄을 웹 기본값으로 구성해 `app.log` 에 썼다 — 웹과 워커가 한 파일을 회전시키는 바로 그 상황. 진입 명령이 `celery` 면 첫 구성부터 워커 파일을 쓴다 |
| F-002 | MED | REQ-001 ⑤ · INV-5 | Fix | Fixed | Round 1 · `app/utils/logs/{setup,config}.py` · `app/celery/app.py` · `test_entry_process`·`test_celery_receiver_in_beat_uses_beat_files` | beat 도 `setup_logging` 시그널을 보내 워커와 같은 `celery.log` 를 회전시켰다(별도 프로세스). `celery-beat.log`·`celery-beat-error.log` 로 나눴다 |
| F-004 | HIGH | REQ-001 ⑦ · INV-7 | Fix | Fixed | Round 1b · `app/utils/logs/redaction.py` · `test_dsn_user_and_password_are_masked`(5건 추가) | 감독자 추가 확인. 계정명 없는 `redis://:pw@` 는 이 브랜치에서 이미 가려졌다(main 규칙도 계정명 0자를 허용). 남아 있던 것: 인코딩 안 된 `@` 가 든 비밀번호(`redis://:pa@ss:w@h` → `redis://:***@ss:w@h` 로 뒷부분 노출)와 계정명만 있는 DSN(`mysql://dbuser@h`). ADR-010 |
| F-003 | LOW | 기존 문서 | Fix | Fixed | Round 1 · README·ARCHITECTURE·server-lifecycle-guide·`.env.example` | uvicorn CLI 가 "로그 설정과 무관"·파일 `{date}_app.log`·`LOG_BACKUP_COUNT`·"앱별 레벨 불가" 서술이 바뀐 동작과 어긋난다 — 고쳤다. 과거 CRP 그룹·specs 문서는 이력이라 두었다 |
