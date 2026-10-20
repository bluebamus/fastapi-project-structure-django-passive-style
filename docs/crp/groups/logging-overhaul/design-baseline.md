# Design Baseline — logging-overhaul (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

> 핵심 갈림길은 사용자가 정했다 — 포맷 C(모든 경로가 항상 프로젝트 형식), 날짜+크기 회전 + 보관 일수,
> DSN 의 id·비밀번호와 `.env` 비밀값 원문 가리기, 파일은 프로세스별 + 에러.

## 1. 목적 / 배경

로그를 Django `settings.LOGGING` 처럼 한 곳에서 구성하고 `.env` 로 세부를 바꾼다. 앱·uvicorn(`python main.py`·`uvicorn main:app`)·
Celery 워커가 같은 형식을 쓰고, 헤더(`app=`)로 출처를 구분하며, 모든 줄에 모듈·클래스·함수·시각이 나온다. 레벨은 헤더별로 `.env` 에서,
파일은 날짜·크기로 회전하고 보관 일수로 지운다. DB 계정·비밀번호 같은 값은 로그 어디에도 원문으로 나오지 않는다.

변경 전 흐름(조사, run-log Round 0): 설정 정본 `build_dictconfig()`(root 핸들러만, ADR-019) · `python main.py` 는 별도 uvicorn dictConfig
(default·access 포매터, access 는 `[app=uvicorn] {message}` 고정) · `uvicorn main:app` CLI 는 uvicorn 기본 형식(config-cleanup ADR-012·R-004) ·
Celery 는 `setup_logging` 수신자로 앱 구성(`--logfile` 무시) · 파일은 `{date}_app.log`·`{date}_error.log` 의 `RotatingFileHandler`
(기동 날짜로 이름이 고정돼 자정에 넘어가지 않는다) · 가리기는 LogRecord factory(DSN 은 비밀번호만).

## 2. 요구사항 (append-only)

| ID | 날짜 | 원문 요지 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "모든 로그는 Django LOGGING 처럼 모듈화 · 앱별·Celery 별 헤더, 출력 포맷은 하나 · 모든 줄에 모듈·클래스·함수·시간 · 레벨은 .env · 로테이트·분할·보관 기간 · DB id·비밀번호 같은 주요 정보는 로그에 나오면 안 된다" + 결정(포맷 C, 날짜+크기+보관일수, DSN id·비밀번호와 .env 비밀값 원문, 프로세스별+에러) | ① 모든 경로 같은 구성·형식(L1) ② 헤더 판별 한 함수 + 외부 로거 이름 표(L2) ③ 포맷 필수 필드 검사(L3) ④ `LOG_APP_LEVELS`(L4) ⑤ 프로세스별 파일(L5) ⑥ 날짜+크기 회전·`LOG_RETENTION_DAYS`(L6) ⑦ DSN 계정명·비밀번호, 설정 비밀값 원문 가리기(L7) ⑧ 문서(L8) | Active |

## 3. 설계 결정 (ADR)

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| ADR-001 | 2026-10-19 | uvicorn 로거 세 개(`uvicorn`·`uvicorn.error`·`uvicorn.access`)를 `build_dictconfig()` 의 `loggers` 에 **핸들러 없이·propagate=True·NOTSET** 으로 둔다. `setup_uvicorn_logging()` 은 `build_dictconfig()` 를 그대로 돌려준다. CLI 는 앱 import 의 `configure_logging()` 이 같은 구성을 다시 건다. `--no-access-log`(handlers 없음 + propagate False)은 구성 전 상태를 보고 유지한다 | 접속 줄 전용 포매터(`TzAccessFormatter`)는 만들지 않았다 — uvicorn 이 넘기는 메시지가 이미 요청 줄(`client - "GET /p HTTP/1.1" 200`)이라 `{message}` 로 충분하고, root 로 보내면 파일·헤더·레벨·가리기를 따로 결선할 필요가 없다(새 추상화 0). 앱별 로거 등록이 아니므로 ADR-019 는 유지된다. uvicorn CLI `--log-level` 은 앱 import 뒤 `.env` 레벨로 덮인다(레벨은 `.env` 가 정한다는 요구) | Active |
| ADR-002 | 2026-10-19 | 헤더 판별은 `filters._app_from_path(pathname, logger_name)` 한 함수 — 저장소 안 코드는 경로 규칙 그대로, 저장소 밖(`ext`)일 때만 로거 이름 첫 조각을 표(`EXTERNAL_HEADERS`)에서 찾는다 | 로거 이름을 먼저 보면 우리 코드의 잘못 붙인 로거 이름이 라벨을 바꾼다(ADR-019 의 장점 상실). 표는 dict 하나라 새 라이브러리는 한 줄로 더한다 | Active |
| ADR-003 | 2026-10-19 | 파일은 프로세스별로 나눈다 — 웹 `app.log`·`error.log`, 워커 `celery.log`·`celery-error.log`, beat `celery-beat.log`·`celery-beat-error.log`. 프로세스 종류는 `setup.entry_process()` 한 곳이 진입 명령(`celery` 이면 `beat`/`celery`)으로 정하고, Celery 수신자는 `entry_process(default="celery")` 로 부른다 | 명세의 `error.log` 공유안은 웹과 워커가 한 파일을 회전시켜 깨진다(다중 프로세스 회전 충돌) — 그래서 에러 파일도 나눈다. 워커는 `setup_logging` 시그널 **전**(`-A` import 중)에도 로그를 남겨 첫 구성부터 나눠야 했고(실기동 스모크에서 발견, F-001), beat 도 별도 프로세스라 같은 이유로 나눴다(F-002) | Active |
| ADR-004 | 2026-10-19 | 회전 핸들러 `DailySizeRotatingFileHandler`(`TimedRotatingFileHandler` 상속, `when="midnight"`, `delay=True`) — 자정 회전은 표준 동작, 크기 초과면 `<파일>.<오늘>.N`, 회전마다 `LOG_RETENTION_DAYS` 보다 오래된 `<파일>.YYYY-MM-DD[.N]` 삭제. 자정은 `utc=use_utc`(파일은 staging/production 에만 있고 그 시각은 UTC) | 파일 로그가 붙는 환경의 로그 시각이 UTC 라 파일 날짜도 UTC 여야 줄 시각과 파일 이름이 맞는다(운영 UTC 정책). `TIME_ZONE` 자정으로 돌리려면 표준 핸들러의 시스템 로컬 시간 가정을 바꿔야 해 코드가 늘어난다 | Active |
| ADR-005 | 2026-10-19 | `LOG_BACKUP_COUNT`·`LOG_APP_FILENAME`·`LOG_ERROR_FILENAME` 을 지운다(남은 `.env` 줄은 무시 — config-cleanup ADR-001 과 같은 방식, `REMOVED_KEYS` 에 추가). 보관은 `LOG_RETENTION_DAYS`(기본 30, `0` = 삭제 안 함, 음수 거부) | 개수와 일수가 함께 있으면 어느 쪽이 먼저 지우는지 설명해야 하고, 크기 분할 파일 수는 날마다 달라 "개수" 는 기간을 보장하지 못한다. 파일 이름 패턴은 날짜를 핸들러가 붙이므로 `{date}` 가 의미를 잃었다 | Active |
| ADR-006 | 2026-10-19 | `LOG_APP_LEVELS`("헤더=레벨" 쉼표 목록)는 `AppLevelFilter` 하나로 구현 — 모든 핸들러에서 `ContextFilter` 바로 뒤, 지정 없는 헤더는 `LOG_LEVEL`. root 레벨은 전체 최솟값. 형식·레벨 오류는 설정 로드 실패, 모르는 헤더는 `configure_logging()` 이 WARNING 한 줄 | 로거 레벨로 하면 앱별 로거 등록(ADR-019 비목표)이 필요하다. 헤더는 경로로 정해지므로 필터가 헤더를 그대로 쓴다. 모르는 헤더를 거부하면 아직 설치하지 않은 기능 이름을 미리 넣을 수 없다 | Active |
| ADR-007 | 2026-10-19 | 설정 비밀값 원문 가리기 — 대상 목록 정본은 `config.LOG_REDACTED_SETTINGS`, 값은 `config.log_secret_values()`(빈 값 제외), `configure_logging()` 이 `redactor.set_literals()` 로 넘긴다. 4글자 이상은 어디서나, 4글자 미만은 `user=`·`username=` 뒤에서만(DSN 은 DSN 규칙). 계약 테스트가 이름 규칙(`PASSWORD`·`SECRET`·`_KEY$`·`_USER$`)으로 목록 누락을 막는다 | 규칙 정본은 그대로 `SecretRedactor` 하나다. 짧은 계정명(`root`·`app`)을 원문 일치로 가리면 일반 단어·경로가 망가진다. DSN 규칙은 계정명까지 가리도록 바꿨다(계정명 없는 `redis://:pw@` 는 그대로 비밀번호만) | Active |
| ADR-008 | 2026-10-19 | 필수 자리표시자 검사는 기존 `_format_renders` validator 에 붙인다 — `string.Formatter().parse()` 로 필드 이름을 모아 `config.REQUIRED_LOG_FIELDS` 와 비교 | 이미 샘플 렌더를 하는 자리라 검사를 한 곳에 둔다. 기본 포맷은 모두 갖췄다(테스트로 고정) | Active |
| ADR-010 | 2026-10-19 | DSN 규칙은 세 꼴 — `user:password@`(→ `***:***@`)·`:password@`(→ `:***@`, `config.REDIS_URL` 의 모양)·`user@`(→ `***@`). 비밀번호 부분은 `[^\s/]+@` 로 탐욕적으로 **마지막** `@` 까지 먹는다 | 감독자 추가 확인(F-004): 인코딩 안 된 `@`·`:` 가 든 비밀번호는 첫 `@` 에서 끊겨 뒷부분이 남았고, 계정명만 있는 DSN 은 계정명이 그대로였다. `/` 가 없는 범위만 보므로 경로·메일 주소의 `@` 는 건드리지 않는다(테스트 고정). 쿼리 문자열에 `@` 가 있으면 호스트까지 가려질 수 있다 — 안전한 쪽 과잉 가림 | Active |
| ADR-009 | 2026-10-19 | 다중 프로세스(uvicorn `--workers` ≥ 2, Celery prefork 자식)의 파일 회전 충돌은 **문서로만** 안내한다 — "콘솔(stdout) + 수집기/`logrotate`, 파일 로그 끔" | uvicorn 자식 프로세스는 워커 수를 믿을 만하게 알 수 없고(`WEB_CONCURRENCY`·CLI 인자·프로세스 관리자마다 다름), 틀린 감지는 거짓 경고가 된다. 명세가 허용한 "감지 방법이 불확실하면 문서만" 을 따른다 → R-001 | Active |

## 4. 불가침 제약

- C-1: ADR-019(config) 유지 — 핸들러는 root 에만, 앱별 로거 등록 없음(uvicorn 전파 항목만 `loggers` 에 있다).
- C-2: 기존 가리기 동작 유지 — `password=`·Bearer·JWT·traceback·`stack_info`, args 모양 유지(접속 줄 유실 없음, config-cleanup F-007).
- C-3: 마이그레이션·의존성 변경 없음.
- C-4: 개발 환경 밀리초는 그대로.

## 5. 변경 이력
- v1.0 (2026-10-19): 최초 작성.
