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

## 3. 설계 결정 (ADR)

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| ADR-001 | 2026-10-19 | 지운 키가 `.env`·환경에 남아도 **기동을 거부하지 않는다**(`extra="ignore"` 로 무시). `REMOVED_SETTINGS`(레거시 `ADMIN`)에 넣지 않는다 | `ADMIN` 은 뜻이 뒤집혀 보안 위험이었지만 이 키들은 효과 없는 값일 뿐이다. README 업그레이드 노트에 "지워도 되고 남아도 무시된다" 고 적는다 | Active |
| ADR-002 | 2026-10-19 | 계약 테스트는 **AST** 로 운영 코드(`config.py`·`main.py`·`app`·`scripts`·`migrations`, 테스트 제외)의 속성 접근 이름과 `getattr(obj, "X")` 상수를 모아, 모든 설정 필드가 그 안에 있는지 본다. 예외는 사유와 함께 `UNREAD_ALLOWED` 에 둔다 | 문자열 grep 은 주석·docstring·이름 목록(`REQUIRED_WITHOUT_ENV_FILE`)까지 "사용" 으로 센다. 이 저장소는 설정을 모두 `xxx_settings.FIELD` 나 `self.FIELD` 로 읽어 AST 속성 접근이면 충분하다. 오탐은 5건이고 모두 이미 문서가 "미사용" 이라 밝힌 것이다 | Active |
| ADR-003 | 2026-10-19 | 예외 목록: `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`·`API_VERSION` | 사용자 결정 범위(SMTP·UPLOAD·SESSION_EXPIRE) 밖이라 지우지 않았다. 목록은 이제 읽히거나 사라진 이름이 남으면 실패한다(목록 부패 방지) | Active |
| ADR-004 | 2026-10-19 | `python-multipart` 는 유지 | 업로드와 무관하게 쓰인다 — `OAuth2PasswordRequestForm`(API 로그인, `app/features/auth/api/routers/v1/auth.py`·`dependencies/auth_dependencies.py`), `/admin` 로그인·CSRF 폼 파싱(`app/core/security/admin_auth.py` 의 `request.form()`), sqladmin 생성·수정 폼 | Active |
| ADR-005 | 2026-10-19 | `server-lifecycle-guide.html` 부록의 만료 필드 행(`ACCESS_TOKEN_EXPIRE_MINUTES` 등)은 남긴다 | 부록은 "config.py 필드 전체" 이고 `test_lifecycle_guide_appendix_lists_every_setting` 이 누락을 막는다. 나머지 문서(ARCHITECTURE·admin-auth-guide)의 만료 기본값 표는 README 표를 가리키게 바꿨다 | Active |

## 4. 불가침 제약

- C-1: `SESSION_COOKIE_NAME`(접속 로그)·`SESSION_SECRET_KEY`(관리 세션 HMAC 키)는 유지한다.
- C-2: 배포 안전 검사(`validate_deployment_safety`)는 유지한다 — `SMTP_PASSWORD` 항목만 빠진다.
- C-3: 마이그레이션 변경 없음.

## 5. 변경 이력
- v1.0 (2026-10-19): 최초 작성.
