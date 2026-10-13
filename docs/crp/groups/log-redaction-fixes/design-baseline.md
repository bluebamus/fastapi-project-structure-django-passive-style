# Design Baseline — log-redaction-fixes (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.
>
> 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다. 다른 그룹의 ID 를 가리킬 때는
> `orm-raw-repository ADR-038` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-13 · 변경 이력: (없음)

> 핵심 갈림길은 사용자가 요청에서 정했다 — 접속 로그 원문 저장은 **유지**(REQ-001 ②), 405 는 `Allow` 를 넘긴다(REQ-001 ③),
> Redis 요구 버전은 코드가 쓰는 명령으로 다시 정의한다(REQ-001 ④), 커버리지 하한은 기본 0(REQ-002).

## 1. 목적 / 배경

2026-10-07 전체 검수 리뷰(로컬 `docs/review/`)의 남은 권장 항목 가운데 사용자가 고르라고 한 것들을 고친다.
① 잡히지 않은 예외의 traceback·로그 메시지에 DSN 비밀번호·`password=`·Bearer 토큰이 그대로 남는다(재현함).
② 접속 로그의 `session_id` 쿠키·Referer·X-Forwarded-For 원문 저장은 사용자가 유지하기로 했다.
③ Starlette `HTTPException` 핸들러가 `exc.headers` 를 버려 405 에 `Allow` 가 없다(리뷰 M-03, 재현함).
④ Redis 요구 버전이 문서마다 달랐고(리뷰 §0 "6.2 이상"), 코드가 쓰는 `EXPIRE NX` 는 7.0 부터다.
⑤ (추가 요청) 커버리지 하한을 기본 0 으로 둔다.

원칙은 저장소의 것을 따른다 — 같은 목적은 하나의 모듈·클래스, 조합은 주입, 모든 단계에 단위 테스트와 fail-on-revert.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "권장 하는 항목에 대해 수정해줘. 다른 두 저장소도 적용해줘. 접속 로그가 session_id 쿠키, Referer, XFF 헤더를 원문 그대로 저장하는 로그는 그대로 유지해줘. ... 405 응답에 allow 헤더를 넘겨주는 것으로 수정해줘. ... redis도 적절하게 다시 정의해줘." | ① 로그 메시지·traceback(`exc_text`)·`stack_info` 의 비밀값을 하나의 규칙으로 가린다 — 저장소의 **모든 핸들러 경로**(console·file·error_file·uvicorn 직접 실행·uvicorn CLI·Celery) ② 접속 로그 원문 저장은 코드·테스트를 손대지 않고 결정으로 기록 ③ 예외 핸들러가 `exc.headers` 를 응답에 싣는다(본문 형식 유지) ④ Redis 최소 버전 상수·근거·기동 확인·문서 일치 ⑤ 엔드포인트 보호 현황 조사(읽기 전용, 보고만) | Active | ADR-001~ADR-004 · C-1~C-4 · F-001~F-003 |
| REQ-002 | 2026-10-13 | "0%로 정의해줘. 기본 설정은 0%이며 차후 사용자가 필요한 수준만큼 설정하는 것으로 정의하고 싶다. 최초는 다른 기능들이 제대로 동작하는지 여부 확인이 중요하다." | `pyproject.toml` `fail_under = 0` 명시(주석에 뜻), 정본은 그 값 하나(CI·로컬 게이트에 `--cov-fail-under` 없음), CI 는 측정·출력 유지, 계약 테스트, 문서(올리는 법) | Active | ADR-005 · C-5 · F-004 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-13 | 마스킹 규칙의 정본은 `app/utils/logs/redaction.py` 의 `SecretRedactor` 하나다(DSN·URL userinfo 비밀번호, `password`·`passwd`·`pwd`·`secret(_key)`·`token`·`api_key`·`authorization`·`credential(s)` 로 **끝나는** 키의 값 — `Authorization` 은 scheme 까지, 키 없는 `Bearer` 토큰, JWT → `***`). `configure_logging()` 이 `install_record_redaction()` 으로 **LogRecord factory** 를 감싸 레코드가 만들어질 때 ① 렌더된 메시지 ② traceback 본문(`exc_info` 를 `logging.Formatter().formatException` 으로 미리 포맷해 가린 뒤 `exc_text` 로 고정 — 포매터는 `exc_text` 가 있으면 다시 포맷하지 않는다) ③ `stack_info` 를 가린다. 메시지는 가능하면 `msg`·`args` 구조를 지키고(인자별로 가린 결과에 비밀값이 남지 않을 때), 아니면 렌더 결과로 고정한다(`args=None`). factory 는 한 번만 감싼다 | 저장소에는 로그 메시지용 마스킹 클래스가 **없었다**(접속 로그의 query 마스킹은 DB 저장용이고 REQ-001 ② 로 손대지 않는다) — 그래서 새로 하나를 두고 정본으로 삼았다. 포매터 단계는 우리가 포매터를 소유하는 핸들러만 덮는다: `uvicorn main:app` CLI 는 uvicorn 의 `DefaultFormatter` 로 `uvicorn.error` 를 찍고, Starlette 의 `ServerErrorMiddleware` 는 500 핸들러가 응답을 만든 뒤에도 예외를 다시 올려 uvicorn 이 `Exception in ASGI application` traceback 을 **그 핸들러로** 남긴다. Celery 워커는 기본값으로 root 핸들러를 자기 것으로 바꾼다. 핸들러 필터도 같은 이유로 외부 핸들러마다 붙여야 한다. factory 는 로거·핸들러와 무관하게 모든 레코드가 지나가는 한 지점이라 한 번에 덮인다. `args` 구조 보존은 uvicorn `AccessFormatter` 가 args 를 5-튜플로 풀기 때문이다(평탄화하면 그 줄이 `handleError` 로 사라진다). 의존성 추가 없음 | Accepted | |
| ADR-002 | 2026-10-13 | 접속 로그(`user_access_logs`)의 `session_id` 쿠키·`referer`·`forwarded_for`·`real_ip` **원문 저장은 유지한다** — 사용자 결정. 코드·테스트는 바꾸지 않는다. ADR-001 의 가리기는 로깅(`logging`) 레코드에만 적용되고 DB 에 저장되는 접속 로그 행에는 적용되지 않는다 | 사용자 결정(REQ-001 원문 "그대로 유지해줘"). 관련 잔여 위험은 R-001 과 service-hardening R-007 에 "결정으로 수용" 으로 적었다 | Accepted | |
| ADR-003 | 2026-10-13 | `StarletteHTTPException` 핸들러(`app/core/bootstrap.py`)가 `JSONResponse(..., headers=exc.headers)` 로 예외의 헤더를 그대로 싣는다. 본문(`ErrorResponse{error_code: HTTP_<status>, message, detail: None}`)은 그대로다. FastAPI `HTTPException` 은 Starlette 의 하위 클래스라 같은 핸들러를 탄다. `AppException` 핸들러는 이미 `headers=exc.headers` 를 넘기고 있었고, `RequestValidationError`·일반 `Exception` 핸들러는 헤더를 가진 예외가 아니다 | 405 `Allow`·401 `WWW-Authenticate`·`Retry-After` 는 HTTP 의미의 일부다(RFC 9110 §15.5.6 — 405 는 `Allow` 를 **반드시** 보낸다). `DELETE /health` 로 재현했다 | Accepted | |
| ADR-004 | 2026-10-13 | Redis 최소 버전은 `app/core/redis.py` 의 `REDIS_MIN_VERSION = (7, 0)` 하나다 — 코드가 쓰는 명령의 요구 버전 최댓값(`EXPIRE … NX` 7.0 > `GETDEL` 6.2 > `SET … NX EX` 2.6.12)이고 근거 표를 상수 주석에 둔다. lifespan 의 Redis 연결(`resources._redis`)이 `ping()` 직후 `ensure_redis_version(client)` 를 부른다: `INFO server` 의 `redis_version` 이 최소 미만이면 `UnsupportedRedisVersion`(RuntimeError)으로 기동을 멈추고 클라이언트를 닫는다. `INFO` 가 `ResponseError`(명령 이름 변경·ACL 거부 — 관리형 Redis)거나 버전을 읽지 못하면 WARNING 을 남기고 계속한다 | Redis 필수 정책(service-hardening ADR-011)과 같은 방향 — 맞지 않는 Redis 는 첫 요청이 아니라 기동에서 드러나야 한다. 6.x 서버는 `EXPIRE NX` 를 문법 오류로 거부해 로그인·가입·관리 로그인이 첫 요청부터 500 이다. 리뷰 문서와 이전 서술의 "GETDEL 때문에 6.2 이상" 은 레이트 리밋의 `EXPIRE NX` 를 빠뜨린 틀린 값이다. INFO 를 막은 관리형 Redis 를 기동 실패로 만들면 정상 배포를 막으므로 경고로 둔다(R-004). 테스트의 fakeredis 2.x 는 INFO 를 모른다(`ResponseError`) — 같은 경고 경로라 테스트가 깨지지 않는다. 확인 로직은 기존 Redis provider 모듈(`app/core/redis.py`)에 두고 수명주기 모듈이 부른다 | Accepted | |
| ADR-005 | 2026-10-13 | 커버리지 하한 `[tool.coverage.report] fail_under` 의 기본값을 **0**(하한 없음)으로 명시한다. 정본은 그 값 하나라는 구조(orm-raw-repository ADR-038 ②)는 유지한다 — CI·로컬 게이트 명령줄에 `--cov-fail-under` 를 두지 않고, 둘 다 `--cov=app --cov-report=term-missing` 으로 측정·출력은 계속한다(`skip-covered` 는 쓰지 않는다 — F-026 이력). 하한을 올릴 때는 측정치보다 조금 낮게 정해 점차 올린다(DEVELOPMENT §6.1) | 사용자 결정(REQ-002): "최초는 다른 기능들이 제대로 동작하는지 여부 확인이 중요하다." 값이 한 곳에 있으므로 올릴 때도 한 곳만 고친다 | Accepted | orm-raw-repository ADR-038 ② 의 **값**(85) |

## 4. 불가침 제약 (Invariants — 위반 시 즉시 Fix)

- C-1: 로그 출력(메시지·traceback·`stack_info`)에 C-1 규칙이 잡는 비밀값이 남지 않는다 — 앱 핸들러·uvicorn(직접 실행·CLI)·Celery 포매터 모두. 마스킹 규칙의 정본은 `SecretRedactor` 하나다 — ADR-001
- C-2: 접속 로그 원문 저장(`session_id`·Referer·XFF)은 사용자 결정으로 유지한다 — 바꾸려면 새 요구사항이 필요하다 — ADR-002
- C-3: 전역 예외 핸들러는 예외가 들고 온 헤더를 응답에서 버리지 않는다. 본문 봉투 형식은 바꾸지 않는다 — ADR-003
- C-4: Redis 최소 버전은 `REDIS_MIN_VERSION` 하나이고, 코드가 쓰는 명령의 요구 버전 최댓값과 같다(`tests/core/test_redis_version.py` 가 대조) — ADR-004
- C-5: 커버리지 하한은 `pyproject.toml` `fail_under` 하나다(기본 0). CI 는 커버리지를 측정·출력한다 — ADR-005

## 5. 변경 이력
- v0.1 (2026-10-13): 최초 작성. REQ-001·REQ-002, ADR-001~ADR-005, C-1~C-5 등재. ADR-005 가 orm-raw-repository ADR-038 ② 의 값(85)을 대체.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
