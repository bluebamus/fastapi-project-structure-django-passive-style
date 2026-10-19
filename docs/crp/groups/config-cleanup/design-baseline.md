# Design Baseline — config-cleanup (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

> 핵심 갈림길은 사용자가 정했다 — SMTP 삭제, `SESSION_EXPIRE_SECONDS` 삭제(기존 만료 설정이 정본), `UPLOAD_*` 삭제.

## 1. 목적 / 배경

`SMTPSettings`(`SMTP_*`)·`UploadSettings`(`UPLOAD_*`)·`SESSION_EXPIRE_SECONDS` 는 선언만 있고 운영 코드가 읽지 않았다.
값을 바꿔도 아무 일도 없는 설정은 "메일·업로드·세션 만료가 된다" 는 오해를 만든다. 사용자는 "세션 만료 시간 설정은
있어야 한다" 고 했고, 실제 만료는 이미 `ADMIN_SESSION_MAX_AGE_SECONDS`·`ADMIN_SESSION_IDLE_SECONDS`·
`ACCESS_TOKEN_EXPIRE_MINUTES`·`REFRESH_TOKEN_EXPIRE_DAYS` 가 정한다 — 이것을 정본으로 문서에 한 번 적는다.

**과거 그룹 문서의 언급은 이력이다.** `skeleton-purpose-audit`(REQ-S10·ADR-S11 — 배포 안전 검사에 `SMTP_PASSWORD` 추가)과
`orm-raw-repository` 등 이전 그룹 문서가 `SMTP_PASSWORD`·`SMTPSettings` 를 언급하는 것은 그 시점의 기록이며 고치지 않는다(append-only).
현재 상태는 이 그룹 문서와 README·ARCHITECTURE 가 기준이다.

## 2. 요구사항 (append-only)

| ID | 날짜 | 원문 요지 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "smtp는 삭제해줘." / SESSION_EXPIRE_SECONDS → "삭제, 기존 만료 설정을 정본으로" / UPLOAD_* → "삭제" | ① 세 묶음의 필드·클래스·전역 인스턴스·`.env.example` 절·배포 안전 검사 항목을 지운다(검사 자체는 유지). ② 남은 `.env` 줄은 기동을 깨지 않는다(무시). ③ 세션·토큰 만료를 README 표 한 곳에 모은다. ④ 읽히지 않는 설정이 다시 생기지 않게 계약 테스트 | Active |
| REQ-002 | 2026-10-19 | "API_VERSION 삭제, 로그 설정은 실제로 연결" (2차, 브랜치 `chore/config-cleanup-2`) | ① `ApiSettings`·`API_VERSION` 을 지운다(남은 `.env` 줄은 무시 — ADR-001 그대로). ② `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 을 포매터 fmt/datefmt 로, `LOG_CONSOLE_ENABLED` 를 콘솔 핸들러 생성 여부로 연결한다 — 기본값이면 출력은 그대로. ③ 잘못된 포맷은 설정 로드에서 거부. ④ 계약 테스트 예외 목록(`UNREAD_ALLOWED`)을 비워 없앤다 | Active |

## 3. 설계 결정 (ADR)

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| ADR-001 | 2026-10-19 | 지운 키가 `.env`·환경에 남아도 **기동을 거부하지 않는다**(`extra="ignore"` 로 무시). `REMOVED_SETTINGS`(레거시 `ADMIN`)에 넣지 않는다 | `ADMIN` 은 뜻이 뒤집혀 보안 위험이었지만 이 키들은 효과 없는 값일 뿐이다. README 업그레이드 노트에 "지워도 되고 남아도 무시된다" 고 적는다 | Active |
| ADR-002 | 2026-10-19 | 계약 테스트는 **AST** 로 운영 코드(`config.py`·`main.py`·`app`·`scripts`·`migrations`, 테스트 제외)의 속성 접근 이름과 `getattr(obj, "X")` 상수를 모아, 모든 설정 필드가 그 안에 있는지 본다. 예외는 사유와 함께 `UNREAD_ALLOWED` 에 둔다 | 문자열 grep 은 주석·docstring·이름 목록(`REQUIRED_WITHOUT_ENV_FILE`)까지 "사용" 으로 센다. 이 저장소는 설정을 모두 `xxx_settings.FIELD` 나 `self.FIELD` 로 읽어 AST 속성 접근이면 충분하다. 오탐은 5건이고 모두 이미 문서가 "미사용" 이라 밝힌 것이다 | Active |
| ADR-003 | 2026-10-19 | 예외 목록: `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`·`API_VERSION` | 사용자 결정 범위(SMTP·UPLOAD·SESSION_EXPIRE) 밖이라 지우지 않았다. 목록은 이제 읽히거나 사라진 이름이 남으면 실패한다(목록 부패 방지) | Superseded (ADR-006) |
| ADR-004 | 2026-10-19 | `python-multipart` 는 유지 | 업로드와 무관하게 쓰인다 — `OAuth2PasswordRequestForm`(API 로그인, `app/features/auth/api/routers/v1/auth.py`·`dependencies/auth_dependencies.py`), `/admin` 로그인·CSRF 폼 파싱(`app/core/security/admin_auth.py` 의 `request.form()`), sqladmin 생성·수정 폼 | Active |
| ADR-005 | 2026-10-19 | `server-lifecycle-guide.html` 부록의 만료 필드 행(`ACCESS_TOKEN_EXPIRE_MINUTES` 등)은 남긴다 | 부록은 "config.py 필드 전체" 이고 `test_lifecycle_guide_appendix_lists_every_setting` 이 누락을 막는다. 나머지 문서(ARCHITECTURE·admin-auth-guide)의 만료 기본값 표는 README 표를 가리키게 바꿨다 | Active |
| ADR-006 | 2026-10-19 | 계약 테스트의 예외 목록 `UNREAD_ALLOWED` 와 그 설명을 **지운다** — 모든 설정 필드는 예외 없이 읽혀야 한다 | REQ-002 로 다섯 이름이 모두 읽히거나 사라졌다. 빈 목록을 남기면 "예외를 넣어도 된다" 는 자리를 남기는 셈이다 | Active |
| ADR-007 | 2026-10-19 | 콘솔 핸들러 생성 여부는 `app/utils/logs/config.py` 의 `console_enabled()` 한 곳에서 정한다 — `build_dictconfig()`(앱·Celery)와 `setup_uvicorn_logging()`(`python main.py`)이 이것을 본다. 끄면 uvicorn 로거는 자기 핸들러 없이 root 로 전파(`propagate=True`) | 경로마다 따로 판단하면 하나가 빠진다. uvicorn 로거를 핸들러 0개·`propagate=False` 로 두면 `logging.lastResort` 가 WARNING 이상을 stderr 로 찍어 "꺼도 나온다" 가 된다 | Active |
| ADR-008 | 2026-10-19 | 출력이 모두 꺼지면(콘솔 false + 파일 핸들러 없음) root 에 `NullHandler` 를 달고 `configure_logging()` 이 stderr 에 경고 한 줄을 `print` 한다 | 핸들러 0개면 `lastResort` 가 stderr 로 새어 설정을 무시한다. 경고는 로깅이 꺼진 상태라 로거가 아니라 stderr 에 직접 쓴다 | Active |
| ADR-009 | 2026-10-19 | Celery 워커는 `celery.signals.setup_logging` 수신자(`app/celery/app.py` 의 `use_app_logging`)로 `configure_logging(force=True)` 를 부른다. `--loglevel` 은 root 레벨로 따르고 `--logfile` 은 쓰지 않는다 | 수신자가 없으면 Celery 가 root 핸들러를 자기 포매터로 갈아끼워 콘솔 스위치·포맷이 워커에서만 무시된다. 결과로 워커 콘솔 줄이 Celery 기본 형식에서 앱 형식으로 바뀐다 | Active |
| ADR-010 | 2026-10-19 | 포맷 검증은 `LogSettings` 의 field_validator 가 `logging.Formatter(fmt, style="{")` 로 샘플 레코드(tzname·appname·classname 채움)를 렌더해 본다. `TzFormatter` 를 직접 쓰지 않는다 | `TzFormatter` 모듈이 `from config import timezone_settings` 를 하므로 `config.py` 에서 부르면 순환 import 다. `TzFormatter` 는 `style="{"` 의 `logging.Formatter` 에 tzname·appname·classname 을 채울 뿐이라 결과가 같다 | Active |
| ADR-011 | 2026-10-19 | `TzFormatter.formatTime` 은 날짜 형식과 무관하게 `with_ms`(development)면 `.밀리초` 를 붙인다. 기본 포맷 정본은 `config.DEFAULT_LOG_FORMAT`(=`app.utils.logs.LOG_FORMAT`) | 기본 `LOG_DATE_FORMAT` 을 넘기면서 개발 밀리초가 사라지면 기본 출력이 바뀐다. strftime 에 밀리초 지시자가 없다. 기본값을 한 곳에 두어 하드코딩과 설정 기본값이 갈라지지 않게 한다 | Active |
| ADR-012 | 2026-10-19 | `uvicorn main:app`·`fastapi dev` CLI 의 `uvicorn.*` 로거는 손대지 않는다(uvicorn 자체 dictConfig) — 문서에 "이 설정들과 무관" 으로 적는다 | uvicorn 이 앱 import 전에 자기 로깅을 구성한다. 앱 쪽에서 덮으면 CLI `--log-config` 같은 uvicorn 의 정상 경로를 가로챈다. 가리기(LogRecord factory)는 그대로 적용된다 → residual-risk R-004 | Active |

## 4. 불가침 제약

- C-1: `SESSION_COOKIE_NAME`(접속 로그)·`SESSION_SECRET_KEY`(관리 세션 HMAC 키)는 유지한다.
- C-2: 배포 안전 검사(`validate_deployment_safety`)는 유지한다 — `SMTP_PASSWORD` 항목만 빠진다.
- C-3: 마이그레이션 변경 없음.

## 5. 변경 이력
- v1.0 (2026-10-19): 최초 작성.
- v1.1 (2026-10-19): REQ-002(2차 — API_VERSION 삭제·로그 설정 연결), ADR-006~ADR-012, ADR-003 Superseded.
