# Run Log — integration-e2e

> 단계별 실행 기록. 명령·결과 수치·판단 근거를 남긴다.

## Round 0 — 2026-10-20 · 계획·인벤토리

**계획(writing-plans 요약)** — W0(별도 커밋) → W1 compose → W2 하네스 → W3 인벤토리 대조 → W4 L2~L6 → W5 의존성 → W6 CI →
W7 문서, 결함은 테스트 고정 후 별도 커밋, 정책 변경은 보고. 그다음 사용자 결정 3건을 결정마다 커밋(TDD·fail-on-revert).

**인벤토리 재추출**(병합된 main `eb47b6c`, 실제 앱 import — `app.openapi()`·`app.state.admin`·Celery 앱):

| 대상 | 계획서 §1 | 재추출 | 바뀐 점 |
|---|---|---|---|
| API operation | 38 | 38 | 같다. reports 는 `GET /api/v1/reports/daily-sales` |
| 관리 뷰 | 7 | 7 (`user-access-log`·`post`·`reply`·`sns-post`·`user`·`product`·`sales-order`) | 뷰별 가능 동작이 다르다 — user 는 생성 불가, sales-order 는 목록·상세·내보내기만, user-access-log 는 생성·수정 불가(삭제 가능). 불가 동작은 403 으로 거부되는지를 그 칸에서 본다 |
| 관리 라우트 | 로그인·로그아웃 | `/admin/login`(GET·POST), `/admin/logout`(POST 전용) 등 14 | 계획서의 `admin:login` 은 Redis 키가 아니라 sqladmin **라우트 이름**이다 |
| Celery | 태스크 2 | `home.aggregate_access_stats`·`home.purge_expired_access_logs`, beat 일정 1(매일 03:30) | 같다 |
| Redis 키 | `login:ip:`·`login:user:`·`register:ip:`(공용) | 실제 키는 레이트 리밋 접두어 `rl:` 가 붙는다 — `rl:login:ip:`·`rl:login:user:`·`rl:register:ip:`·`rl:admin-login:ip:`·`rl:admin-login:user:`, 관리 세션 `admin:sess:`·`admin:user_sessions:`, refresh `auth:rt:`·`auth:user:<sub>:fams`·`auth:fam:<fam>:revoked`, Celery broker·backend | 관리 로그인 제한은 공용 키가 아니라 `admin-login:` 접두어로 나뉜다 |
| 로깅(새 대상) | — | 웹 `app.log`/`error.log`, worker `celery.log`/`celery-error.log`, beat `celery-beat.log`/`celery-beat-error.log`, 날짜+크기 회전·보관일수, 헤더별 레벨(`LOG_APP_LEVELS`), DSN·설정 비밀값 가리기 | logging-overhaul 이후 |

포트 13341·13342·16393·18093: Windows `netstat`·WSL `ss -ltn` 모두 비어 있음. WSL 에서 연 포트가 Windows `127.0.0.1` 로 닿음(pymysql·redis 로 확인).

## Round 1 — W0 (`36cdd9d`)

- RED: `tests/browser/test_redis_target.py` — `server_env()` 는 접속하지 않는 함수라 RED 확인에 Redis 를 쓰지 않는다. 3 failed(기본 6380 을 돌려줬다).
- GREEN 후 단위 전체를 `REDIS_HOST=127.0.0.1 REDIS_PORT=16393` 로 돌리자 `tests/core/test_dsn.py` 2건이 기본 포트(6379)에 기대고 있어 실패 —
  systematic-debugging: 원인은 환경 의존(테스트 의도는 비밀번호 왕복), 생성자에 포트를 고정. 1322 passed.
- fail-on-revert: `tests/browser/conftest.py` 를 HEAD 로 되돌려 3 failed, 복원 3 passed.
- 6379 접속: 0(모든 실행에 `REDIS_HOST`·`REDIS_PORT` 명시, RED 는 비접속).

## Round 2 — W1~W6

- compose 첫 기동 24초 — primary·replica(GTID, `gtid_purged` 기준점)·Redis healthy. replica 쓰기는 1290(read_only)으로 거부.
- 하네스 첫 실행: 자식 env 허용 목록에 사용자명 변수가 없어 aiomysql import 가 `getpass.getuser()` 로 실패 → `USERNAME`·`USER`·`LOGNAME` 추가.
- L2 첫 실행 53 failed → 분석: (1) 위조 토큰 401 에 `WWW-Authenticate` 없음 = **결함 F-001**(TDD 수정 `1bf527b`, 단위 24 failed→pass),
  (2) 405 `Allow` 는 처음 맞은 라우트 메서드만 = 현행 유지 결정(관측 기록), (3) 테스트 기대값 오류 2(목록 응답 형식·오류 코드 접두어).
- L3: 접속 로그 테이블엔 `updated_at` 이 없음, 사용자 ID 는 인증 의존성이 도는 라우트에서만 기록, CTE 재귀 깊이 — 모두 테스트 쪽 가정 수정.
  beat 일정 목록은 DEBUG 라 `LOG_APP_LEVELS=celery=DEBUG` 로 확인.
- L4: `ADMIN_SESSION_*` 하한 60초(설정 검증) → 60/120초 실시간. Playwright `page.request` 는 `http://` 로 Secure 쿠키를 싣지 않음 → 브라우저 안 `fetch`(ADR-008).
  관리 폼 자동 필드(`created_at` 등) 문제는 **없었다**(생성·수정 저장 확인).
- L5 관측(수정 전): Redis 장애 시 로그인·refresh·가입·비활성화 500·기록 2건·keep-alive 끊김, replica 장애 읽기 500·기록 2건·끊김, primary 장애 쓰기는
  `DATABASE_ERROR` 500(변환기 처리, 기록 0·연결 유지). CSRF 측정 — 필드 하나 > 1 MiB 는 500(F-007).
- L6: `GRANT … '%%'`(인자 없는 pymysql 은 `%` 를 치환하지 않는다) 수정. 가짜 Redis 를 Windows 에서 16393 에 바인딩할 수 없어(WSL 포트 전달기 점유)
  실제 Redis 6.2 profile 로 교체(ADR-007) — 그 예외가 `try` 밖이라 Redis 재시작이 빠져 연쇄 실패했던 것도 함께 정리.
- 전체 1회차 3 failed: (a) 인벤토리 Redis 키 `admin-login:user:` 미관찰 — 로그인 성공이 키를 지운 뒤 관찰, 테스트 안에서 관찰로 수정,
  (b) replica 장애 테스트의 `/me` 401 — systematic-debugging: 400회 반복 재현 실패, 시계 역행 없음(Windows Time 이벤트), 코드 추적 결과
  `get_current_user` 가 replica 에서 사용자를 읽음 + 직전 primary 장애로 복제 지연 → **F-008**(정책 결정, 결정적 재현 테스트로 고정), 하네스는 `/me` 를 복제까지 기다린다.
- 전체 2회차: 309 passed, skip 0.
- L1 회귀: 단위 1344 passed. `-m mysql` 27 passed — §0 밖 포트(3309)를 쓰지 않으려고 e2e primary(13341) 안에 전용 DB·계정을 만들어 `MYSQL_TEST_PORT=13341`.
  `-m browser` 2 failed·7 errors → systematic-debugging: CDN 정상, 가설 "읽지 않는 PIPE 가 차서 서버가 멈춘다" 를 프로브로 확인(9번째 요청에서 ReadTimeout) =
  **결함 F-002**(TDD 수정 `f9756d7`, 300요청 회귀) → 10 passed.

## Round 3 — 사용자 결정

| 결정 | 커밋 | RED | GREEN | fail-on-revert |
|---|---|---|---|---|
| 1 Redis → 503 (F-004) | `fd7d64d` | `test_redis_unavailable.py` 12 failed(응답 대신 예외) | 12 passed, e2e L5: 503·연결 유지·`[RedisUnavailable]` 1건 | RED 가 수정 전 코드 |
| 2 replica → primary (F-005) | `47161ac`, 타입 `676b245` | `test_db_replica_fallback.py` 재시도 1 failed(2003) | 4 passed, e2e L5: 200·WARNING 1줄·`/me` 200 | router.py 를 HEAD 로 → 1 failed, 복원 |
| 3 초기 로그 줄 (F-006) | `dcfa974` | 재현 안 됨(현재 코드 통과) | `test_log_early_lines.py` 2 passed, e2e L6 4경로 | `entry_process` 를 예전 동작으로 → 워커 경우 실패, 복원 |

결정 1 범위 밖으로 남긴 것: 관리 화면 쿠키 없는 첫 요청의 저장 실패 500(F-009, 문서화된 현행).

## Round 4 — 검증

| 검사 | 결과 |
|---|---|
| Windows `pytest -m e2e` | 309 passed, 1401 deselected, skip·xfail 0, 6분 47초 |
| Linux `.env` 없는 클론 `/tmp/itest-passive-linux` | 단위 1364 passed·37 deselected, e2e 309 passed, prefork `Warm shutdown` 확인, 클론 삭제 |
| L1 | 단위 1364 passed(skip 0), `-m mysql` 27, `-m browser` 10 |
| 정적 | ruff·format 클린, mypy(1.20.2 순수 Python) 223 파일 0 오류 |
| `review_gate --fast` | 7단계 통과(pip-audit 포함). 1회차는 mypy 가 내 코드의 타입 오류를 잡았다 → `676b245` |
| 인벤토리 | 59 항목, 빈 칸 0, N/A 64칸(사유 있음), 실행 344칸 |
| 비밀값 grep | 0 — 앱·worker·beat·스크립트 출력, 프로세스 파일, compose 로그 |

**CSRF 본문 측정**(익명 `POST /admin/login`, 토큰 없음):

| 모양 | 크기 | Windows 응답·시간 | Linux 응답·시간 | 최대 RSS 증가 |
|---|---|---|---|---|
| 512 KiB 필드 여러 개 | 1 / 10 / 50 MiB | 403 · 0.008 / 0.062 / 0.381초 | 403 · 0.006 / 0.036 / 0.175초 | 50 MiB 에서 +101(Win)·+85(Linux) MiB |
| 필드 하나 | 1 / 10 / 50 MiB | 500·연결 끊김 · 0.006 / 0.05 / 0.276초 | 500·연결 끊김 · 0.003 / 0.019 / 0.147초 | 50 MiB 뒤 RSS +54(Win)·+59(Linux) MiB 잔존 |

## Round 5 — 2026-10-21 · e2e 정책 결정 2차 (e2e-policy-2, 브랜치 `fix/e2e-policy-2`)

**해당 여부 확인** — 결정 1~7 모두 이 저장소에 해당했다. 결정 4 만 이미 충족(`create_superuser --set-password` 가 커밋 뒤 refresh·관리 세션을
폐기, Redis 실패면 종료 코드 1) → 계약 테스트로 고정. 결정 2 는 한때 보류됐다가 사용자가 ①(미들웨어로 직접 받기)로 확정했다.

| 결정 | 커밋 | RED(수정 전) | fail-on-revert |
|---|---|---|---|
| 1 422 문서 | `371d896`·`95ae048`(mypy) | 계약 2 failed(`HTTPValidationError` 광고) | 후처리 호출 제거 → 3 failed, 복원 |
| 2 처리기 없는 예외 | `8665236` | 실제 uvicorn: traceback 2·`Exception in ASGI application` 1·연결 종료(ConnectionResetError), TestClient 로 예외 재던짐 | HEAD 로 되돌림 → 4 failed, 복원 |
| 3 401 헤더 | `6788468`·`62da6f6`(mypy) | 4 failed(로그인·refresh·logout·비활성 `/me`·헤더 없는 401) | `_challenge` 무력화 → 52 failed, 복원 |
| 4 CLI 폐기 | `ddaadc7` | 이미 충족(통과) | 폐기 호출 제거 → 3 failed, 폐기를 커밋 앞으로 → 1 failed, 복원 |
| 5 primary 조회 | `4743b1c` | 2 failed(지연 중 200 대신 401, 비활성 직후 401 대신 200) | `using_writer` 제거 → 2 failed, 복원 |
| 6 저장 실패 503 | `c3e8280` | 500 | HEAD 로 → 1 failed, 복원 |
| 7 CSRF 상한 | `6bfc431` | 5 failed(MultiPartException 이 미들웨어 밖으로) | HEAD 로 → 5 failed, 복원 |
| 의존성 `aiomysql[rsa]` | `ab7f15d` | 1 failed(선언) | RED 가 수정 전 선언 |

- systematic-debugging: (a) 결정 6 첫 GREEN 실패 — 테스트 대역(`__getattr__` 코루틴)이 `pipeline()` 의 동기 컨텍스트 관리자 계약을 어겨
  `TypeError` → 대역을 닫힌 포트(127.0.0.1:1)의 실제 Redis 클라이언트로 바꿈. (b) `-m mysql` 1 failed — 내가 만든 테스트 DB 의
  `CHARACTER SET` 만 지정해 기본 콜레이션 `utf8mb4_0900_ai_ci` → `ALTER DATABASE … COLLATE utf8mb4_unicode_ci`(환경 원인, 코드 무관).
  (c) mypy 2건(결정 1·3 타입) → 결정별 커밋. (d) 결정 2 첫 GREEN 실패 — pytest env 가 `DEBUG=true` 라 재던짐 분기 → 테스트가 DEBUG 를 끈다.
- 결정 2 원인 위치: Starlette `ServerErrorMiddleware.__call__`(`starlette/middleware/errors.py` 164~186, 처리기 응답 뒤 `raise exc`),
  FastAPI `build_middleware_stack`(`fastapi/applications.py` 1027~1031, `Exception` 키는 `ServerErrorMiddleware` 처리기로),
  uvicorn `run_asgi`(`uvicorn/protocols/http/httptools_impl.py` 424~430, `Exception in ASGI application` 기록 후 응답 시작됐으면 `transport.close()`).
  미들웨어 순서(바깥→안): ServerErrorMiddleware → UserInfoMiddleware → CORSMiddleware → ExceptionMiddleware → 라우터. 수정 뒤 맨 바깥 사용자 미들웨어가 `answer_unhandled_exception`.

| 검사 | 결과 |
|---|---|
| `pytest -m e2e`(Windows) | 309 passed, skip·xfail 0, 7분 7초 |
| 인프라 제외 `-m "not mysql and not browser"` | 1386 passed, 37 deselected |
| `-m mysql`(e2e primary 13341 안 전용 DB `fastapi_passive_test`) | 27 passed |
| ruff·format·mypy(1.20.2 순수 Python) | 클린, 223 파일 0 오류 |
| `review_gate --fast` | 7단계 통과(pip-audit 포함) |

**CSRF 본문 상한 재측정**(익명 `POST /admin/login`, 토큰 없음, Windows):

| 모양 | 크기 | 응답 | 시간 | 연결 | RSS(전→후) |
|---|---|---|---|---|---|
| 512 KiB 필드 여러 개 | 1 / 10 / 50 MiB | 403 / 413 / 413 | 0.043 / 0.007 / 0.027초 | 유지 | 112.7→113.3 / 114.3→114.3 / 114.3→114.3 MiB |
| 필드 하나 | 1 / 10 / 50 MiB | 400 / 413 / 413 | 0.007 / 0.005 / 0.035초 | 유지 | 113.3→114.3 / 114.3→114.3 / 114.3→114.3 MiB |

최대 RSS 증가는 6건 모두 0 MiB(이전 최고치를 넘지 않음) — 수정 전 50 MiB 에서 +101 MiB 였다.
