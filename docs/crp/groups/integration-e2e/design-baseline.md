# Design Baseline — integration-e2e (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-20 · 변경 이력: (없음)

> 핵심 갈림길은 사용자가 확정한 통합 테스트 계획서(§0 결정·§5 확인 결과)와 e2e 정책 결정 3건이 정했다.

## 1. 목적 / 배경

단위·`mysql`·`browser` 마커 테스트는 층 하나씩을 본다. 실제 MySQL 복제·Redis·uvicorn·Celery worker·Chromium 을 한꺼번에 띄운
상태에서 **모든 API operation·관리 뷰·백그라운드 태스크·Redis 키**가 계약대로 동작하는지, 장애에서 어떻게 무너지고 회복하는지는
아무도 보지 않았다. 이 그룹은 그것을 영구 스위트(`tests/e2e/`, 마커 `e2e`)로 만들고, 그 스위트가 찾은 결함을 고친다.

## 2. 요구사항 (append-only)

| ID | 날짜 | 원문 요지 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-20 | "통합 테스트 진행해줘" (계획서 §0·§2 W1~W9·§3 L1~L6) | ① `compose.e2e.yaml`(MySQL 8.4 primary 13341 + GTID replica 13342 + Redis 7.4 16393, 앱 18093, 프로젝트 `itest-passive`) ② 하네스·인벤토리 대조기·L2~L6 ③ CI job `e2e`(매 push, skip·xfail·0건 실패) ④ 결함은 테스트를 먼저 고정하고 별도 커밋으로 고친다 — 정책을 바꾸는 수정은 멈추고 보고 ⑤ passive 전용: CSRF 본문 버퍼링 상한은 측정만(결정은 사용자) | Active |
| REQ-002 | 2026-10-20 | W0 — 테스트가 남의 Redis 에 붙는 구조 제거 | Redis 가 필요한 fixture 는 `REDIS_HOST`·`REDIS_PORT` 가 명시되지 않으면 `pytest.fail`, 자식 서버 env 에 그 값을 넘긴다, CI 에도 명시 | Active |
| REQ-003 | 2026-10-20 | e2e 정책 결정 1 — Redis 장애 → 503 | Redis 를 필수로 쓰는 API 경로(로그인·refresh·logout·가입·사용자 비활성화/강등/삭제)와 관리 화면이 Redis 연결 오류 때 500 대신 503(기존 오류 형식 `SERVICE_UNAVAILABLE`), 내부 정보 0, traceback 한 번, keep-alive 유지. 한 곳(예외 핸들러)에서 | Active |
| REQ-004 | 2026-10-20 | e2e 정책 결정 2 — replica 장애 → primary 재시도 | replica 로 가는 읽기가 연결 계열 오류로 실패하면 primary 로 한 번 다시 실행 + WARNING(비밀값 없이). `/ready` 불변. 읽기 전용 세션에만. 단일 DB 구성은 변화 0 | Active |
| REQ-005 | 2026-10-20 | e2e 정책 결정 3 — import 중 로그 줄이 파일에 빠짐 → 고친다 | 설정 로드 직후 파일 핸들러까지 붙여 기동 초기 줄도 프로세스별 파일에. 웹·`python main.py`·`uvicorn main:app`·worker·beat 모두. 핸들러 중복·줄 중복 없음 | Active |
| REQ-006 | 2026-10-21 | e2e 정책 결정 2차(사용자 확정) — 결정 1~7 + 추가 결정(결정 2 ①·`aiomysql[rsa]`) | ① 422 OpenAPI = 실제 `ErrorResponse`(F-010) ② 처리기 없는 예외 500: 기록 1번·keep-alive 유지(F-013) ③ 이 앱의 모든 401 에 `WWW-Authenticate: Bearer`(F-012) ④ `create_superuser --set-password` 세션 폐기(이미 충족 → 계약 고정) ⑤ 인증 사용자 조회는 primary(F-008) ⑥ 관리 화면 Redis 장애는 응답 직전 저장 실패까지 503(F-009) ⑦ CSRF 폼 본문 10 MiB 초과 413·필드 1 MiB 초과 400(F-007) ⑧ cryptography 를 `aiomysql[rsa]` 로 선언(F-014). 결정마다 TDD·fail-on-revert·별도 커밋 | Active |

## 3. 설계 결정 (ADR)

| ID | 날짜 | 결정 | 이유 | 상태 |
|---|---|---|---|---|
| ADR-001 | 2026-10-20 | e2e 환경은 기존 `compose.test.yaml` 과 **분리한** `compose.e2e.yaml`(프로젝트 `itest-passive`) | `compose.test.yaml` 은 `mysql`·`browser` 마커의 단일 MySQL 이고 CI `mysql` job 이 쓴다. 복제·장애 주입을 섞으면 그 테스트가 흔들린다. 포트·프로젝트 이름으로 완전히 격리 | Active |
| ADR-002 | 2026-10-20 | MySQL 장애는 컨테이너 `stop` 이 아니라 `SET GLOBAL offline_mode=ON` 으로 주입한다. Redis·worker 는 실제로 멈췄다 올린다 | 데이터가 tmpfs 라 `stop` 하면 스키마가 사라진다(재기동 = 빈 DB, replica 는 복제 기준점도 잃는다). `offline_mode` 는 SUPER 가 아닌 연결(앱)을 끊고 새 연결을 거부한다 — 앱 쪽에서 보면 서버가 사라진 것과 같다(MySQL 3032). 복제 지연은 `STOP REPLICA SQL_THREAD` | Active |
| ADR-003 | 2026-10-20 | `tests/e2e` 는 `-m` 식에 `e2e` 가 있을 때만 **수집**한다(루트 `conftest.py` `pytest_ignore_collect`) | 기존 게이트·CI 마커식(`not mysql and not browser`)을 그대로 두면서, 마커 없이 `pytest` 를 돌려도 compose·브라우저를 띄우지 않게 한다. deselect 가 아니라 비수집이라 deselected 수도 늘지 않는다 | Active |
| ADR-004 | 2026-10-20 | 앱·worker 는 **`.env` 없는 실행 디렉터리**에서 `ENV=production`·`DEBUG=false`·`LOG_FILE_ENABLED=true` 로, 설정은 전부 환경 변수로 띄운다. OS 변수는 허용 목록만 넘긴다. 하네스는 시작 전에 모든 DSN·Redis 의 host=127.0.0.1·포트=전용 값을 검사해 아니면 `pytest.exit` | 저장소 `.env`(예: `TRUSTED_PROXY_HOPS=1`)가 접속 대상·결과를 바꾸지 못하게 한다. 운영 설정 검증·파일 로그·Alembic 전용 스키마·Secure 쿠키를 그대로 탄다 | Active |
| ADR-005 | 2026-10-20 | 기존 `browser` 마커는 **병존**한다(e2e 로 흡수하지 않는다) | `browser` 는 `compose.test.yaml`·`DEBUG=true` 로 Scalar 문서 렌더링을 보는 별개 계약이고 CI `mysql` job 이 돌린다. e2e 는 운영 모드(문서 꺼짐)라 그 계약을 대신하지 못한다 | Active |
| ADR-006 | 2026-10-20 | dev 의존성 `pytest-timeout` 추가 | 브라우저 대기(리다이렉트 중 `goto`·`close`)가 멈추면 스위트 전체가 매달린다. 테스트마다 상한을 둔다(`pytest.mark.timeout`) | Active |
| ADR-007 | 2026-10-20 | Redis 최소 버전 기동 거부는 가짜 서버가 아니라 실제 `redis:6.2-alpine`(compose profile `redis-old`, 같은 포트)으로 본다 | Windows 에서는 WSL 포트 전달기가 16393 을 잡고 있어 가짜 서버를 바인딩할 수 없다(WinError 10048). 실제 6.2 가 더 정확하기도 하다 | Active |
| ADR-008 | 2026-10-20 | Playwright 의 `page.request` 대신 브라우저 안 `fetch` 로 부가 요청(내보내기·거부 확인)을 한다 | 앱이 production 이라 관리 세션 쿠키가 `Secure` 다. Chromium 은 `http://127.0.0.1` 을 안전한 출처로 보고 싣지만 Playwright APIRequestContext 는 싣지 않는다(실측) | Active |
| ADR-009 | 2026-10-20 | (REQ-003) Redis 오류는 **`RedisError` 전용 예외 핸들러** 한 곳에서 503(`SERVICE_UNAVAILABLE`)으로 바꾼다 | 처리되지 않은 예외를 `Exception` 핸들러가 받으면 Starlette `ServerErrorMiddleware` 가 응답 뒤 예외를 다시 던져 traceback 이 두 번 남고 uvicorn 이 keep-alive 를 끊는다. 클래스 전용 핸들러는 `ExceptionMiddleware` 에서 끝나 다시 던지지 않는다. 연결 계열(`ConnectionError`·`TimeoutError`)만 — 명령 오류는 결함이라 500. 관리 화면은 sqladmin 하위 앱의 미들웨어(세션)가 앱 핸들러 바깥이라 이 핸들러가 닿지 않는다 — 세션 **로드** 실패는 이미 미들웨어가 503, 쿠키 없는 첫 요청의 응답 직전 **저장** 실패는 문서화된 현행 500 으로 남긴다(바꾸려면 정책 결정, residual-risk R-004) | Active |
| ADR-010 | 2026-10-20 | (REQ-004) replica 재시도 범위 | 아래 §3.1 | Active |
| ADR-011 | 2026-10-20 | (REQ-005) 로깅 구성 시점 | 아래 §3.2 | Active |
| ADR-012 | 2026-10-21 | (REQ-006) 정책 결정 2차의 반영 위치 | 아래 §3.3 | Active |
| ADR-013 | 2026-10-21 | (REQ-006) cryptography 는 드라이버 추가 옵션 `aiomysql[rsa]` 로 선언한다(직접 줄 삭제, `pymysql` 은 Alembic 용으로 유지) | 유일한 사용처가 MySQL 8.4 `caching_sha2_password` 전체 인증(TLS 아닌 연결)의 RSA 암호화다 — 사용처와 같은 줄에 두면 드라이버를 바꿀 때 함께 사라진다. `uv lock` 결과 표기만 바뀌고 cryptography 50.0.0 은 그대로. `tests/core/test_dsn.py::test_mysql_rsa_auth_dependency_is_declared_through_the_driver` | Active |

### 3.1 ADR-010 — replica 읽기 재시도 범위

- **어디서**: 라우팅 세션 클래스(`make_routing_session_class`)의 `do_orm_execute` 수신자 한 곳. ORM·Core·Raw(`text()`)가 모두
  `Session.execute` 를 지나므로 기능 코드는 바뀌지 않는다. `state.invoke_statement()` 를 감싸고, 실패하면
  `invoke_statement(bind_arguments={"bind": writer})` 로 한 번 더 부른다.
- **무엇을**: `mark_read_only` 된 세션(기능 앱의 조회 의존성 `get_read_only_db_session`·`get_current_user` 등)이 replica 에 묶인
  읽기만. writer 에 고정된 세션·일반 라우팅 세션(쓰기와 같은 트랜잭션일 수 있다)은 제외 — 트랜잭션 중간에 서버를 바꾸면 의미가 깨진다.
- **어떤 오류**: 연결 계열만(`DBAPIError.connection_invalidated` 또는 드라이버 코드 1053·2002·2003·2006·2013·2055·3032·4031).
  문법·제약·없는 테이블 같은 쿼리 오류는 primary 로 숨기지 않는다.
- **몇 번**: 한 번. 재시도 뒤 그 세션은 writer 에 고정한다(같은 요청이 죽은 replica 를 다시 두드리지 않고, 스냅샷도 한 서버).
- **로그**: WARNING, 예외 종류와 드라이버 코드만(메시지에는 DSN 이 들어 있다).
- **바꾸지 않은 것**: `/ready`(writer 만 본다), replica 가 없는 구성(수신자가 아무것도 하지 않는다), 쓰기 경로.
- **알려진 한계**: replica 가 "느린" 경우(연결은 되지만 지연)는 대상이 아니다 — 복제 지연 중 읽기는 여전히 오래된 값을 본다(L3-8).

### 3.2 ADR-011 — 기동 초기 로그 줄

- **결정 3 은 이 저장소에서 이미 충족돼 있다 — 코드 변경 없이 계약으로 고정한다.** 첫 `get_logger()`(설정 로드 직후, 첫 모듈 import)가
  `configure_logging()` 을 부르고, 그때 `entry_process()` 가 진입 명령(`celery … worker|beat` 면 워커·beat, 아니면 웹)으로 프로세스
  종류를 정해 **파일 핸들러까지** 붙인다(logging-overhaul 의 c68e246·28ca635). Celery `setup_logging` 수신자는 같은 dictConfig 를
  `force=True` 로 다시 적용한다 — 핸들러는 교체될 뿐 둘이 되지 않는다.
- **확인**: 실제 프로세스 네 경로(`uvicorn main:app`·`python main.py`·worker·beat)에서 콘솔의 형식 줄이 모두 자기 파일에 있다(e2e L6
  `test_every_entry_path_logs_the_same_format_into_its_own_file`). 단위 회귀 `tests/utils/test_log_early_lines.py` 는 import 중 줄이
  파일에 **한 번씩** 있고 다른 프로세스 파일에 섞이지 않음을 본다 — `entry_process()` 를 예전 동작(진입 명령 무시)으로 되돌리면 워커
  경우가 실패한다(fail-on-revert).
- **대체 관계**: logging-overhaul ADR-003(프로세스별 파일)을 대체하지 않고, "기동 초기 줄도 파일에" 를 그 위의 계약으로 명시한다
  (그 그룹 문서는 append-only 라 고치지 않는다 — ARCHITECTURE §5 에 한 줄을 더했다).

### 3.3 ADR-012 — 정책 결정 2차의 반영 위치

- **결정 1(422)**: `create_app()` 의 OpenAPI 후처리 한 곳(`_document_real_validation_error`)에서 모든 operation 의 422 스키마를
  `ErrorResponse` 로 바꾸고 `HTTPValidationError`·`ValidationError` 컴포넌트를 걷어낸다. 실제 응답은 그대로다.
- **결정 2(처리기 없는 예외)**: `@app.middleware("http")` `answer_unhandled_exception` 을 사용자 미들웨어 중 **가장 바깥**(마지막 등록)에 둔다.
  `call_next` 의 예외를 기존 `Exception` 처리기로 응답해 `ServerErrorMiddleware` 의 재던짐(→ uvicorn `Exception in ASGI application`·연결
  종료)을 막는다. `DEBUG=true` 는 다시 던진다. 응답이 시작된 뒤(스트리밍 본문 중)의 예외는 `call_next` 밖이라 오지 않는다 — 확인만 했다
  (기존대로 1건 기록 후 재던짐).
- **결정 3(401)**: `AppException`·`HTTPException` 핸들러가 401 이면 도전 헤더를 붙인다(`_challenge`). F-001 때 `get_current_principal` 에
  붙이던 개별 부착은 지웠다 — 한 곳이다.
- **결정 4**: 코드 변경 없음. `ensure_superuser` 는 커밋 뒤 폐기, Redis 실패면 종료 코드 1(새 비밀번호는 남는다 — 순서 명시). 계약 테스트만 더했다.
- **결정 5**: `get_current_user` 가 읽기 전용 세션을 `using_writer` 로 primary 에 고정한다(읽기 전용 표시는 유지). 다른 읽기 라우팅은 그대로.
- **결정 6**: `RedisSessionMiddleware` 가 응답 시작 전 저장(`_commit`)의 `RedisError` 를 받아 앱 응답 대신 읽기 실패와 같은 503 을 낸다.
- **결정 7**: `AdminCsrfMiddleware` — `Content-Length` 로 먼저, 없거나 거짓이면 읽는 도중 누적으로 10 MiB 초과를 413, 폼 파서의 필드 상한
  예외(1 MiB)를 미들웨어 안에서 400. 상한은 **모듈 상수**다 — 이 저장소의 미들웨어 상수 관례(`SAFE_METHODS`·`_FORM_TYPES`)를 따랐고
  운영에서 바꿀 이유가 없다.

## 4. 불가침 제약

| ID | 제약 |
|---|---|
| C-1 | 포트는 계획서 §0 의 passive 행만(13341·13342·16393·18093), 모두 127.0.0.1. 남의 컨테이너(`*-testdb`·`sp-eval-redis` 등)·외부 DB 에 접속하지 않는다 |
| C-2 | `docker compose down -v` 금지 — 볼륨은 tmpfs 라 `down` 만으로 정리된다 |
| C-3 | 통과 기준: 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 로그 비밀값 0 |
