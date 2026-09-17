# QUICKSTART — 처음 보는 사용자를 위한 최소 실행 경로

이 저장소는 MySQL·Redis·Celery·SQLAdmin·JWT·DB read/write 라우팅을 모두
포함한다. 전부 이해하고 시작할 필요는 없다. 이 문서는 **가장 먼저 무엇만 알면 되는지**만
다룬다. 전체 구조는 [ARCHITECTURE.md](./ARCHITECTURE.md), 전체 설정은 [../../README.md](../../README.md).

검토 기준: **2026-09-17 현재 작업 트리**. 설정·자원·요청·종료는
[서버 수명 HTML 안내서](./server-lifecycle-guide.html), MVC·주입·비동기·신규 뷰/테이블 작성은
[개발 HTML 지침서](./feature-development-guide.html)를 함께 읽는다.

---

## 1단계 — Redis를 준비해 최소 HTTP 배선 확인

MySQL 없이 앱 배선부터 확인할 수 있지만, startup 단계의 연결 검증을 통과하려면 Redis는 필요하다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
uv sync
DEBUG=false uv run uvicorn main:app --port 8000
```

위 환경변수 지정은 Bash 문법이다. PowerShell에서는 다음처럼 실행한다.

```powershell
$env:DEBUG = "false"
uv run uvicorn main:app --port 8000
# 서버 종료 후 필요하면 개발 기본값으로 복원
Remove-Item Env:DEBUG
```

저장소 루트에서 실행한다. 실제 `.env`가 있으면 DB·Redis 값이 기본값과 다를 수 있다.
운영체제 환경변수는 `.env`보다 우선하며 `.env.example`은 자동 fallback이 아니다.

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"0.1.0"}
```

앱은 시작하면서 `REDIS_HOST`/`REDIS_PORT`로 `ping()`을 호출하며, 연결되지 않으면 startup을
중단한다. 위 단계는 Redis만 사용해 HTTP 배선이 정상인지 확인하는 용도다.

### 이 상태에서 되는 것 / 안 되는 것

| | 동작 | 이유 |
|---|---|---|
| `GET /health` | ✅ | DB를 건드리지 않는다 |
| `GET /ready` | ❌ 503 | writer DB의 SELECT 1 검사가 실패한다. Redis runtime 가용성은 검사하지 않는다 |
| `GET /api/v1/blog/posts` 등 기능 API | ❌ 500 | MySQL 연결이 필요하다 |
| `GET /docs` (Scalar), `/openapi.json` | ❌ 404 | **`DEBUG=false` 가 문서를 끈다** (운영 보안 기본값) |

> API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL을 요구한다(2단계).
> 이 둘이 한 스위치에 묶여 있다는 점이 첫 실행에서 가장 헷갈리는 부분이다.

`/health`는 liveness, `/ready`는 DB readiness이다. startup Redis ping 성공이 이후의 Redis
정상 상태까지 보장하지는 않는다. `DEBUG=false`에서 DB 없이 확인 가능한 것은 최소 HTTP
배선이며, 실제 기능·관리 화면·접속 로그 저장에는 DB가 필요하다.

---

## 2단계 — 기능 API까지 쓰려면 MySQL 추가

### 왜 필요한가

`DEBUG=true`(기본값)면 앱 시작 시 `create_db_tables()` 가 실행된다. 이 함수는 디렉터리를
훑지 않고 **이미 populate 된 App Registry 의 모델 metadata** 로 테이블을 만든다 —
`INSTALLED_APPS` 에 없는 앱의 테이블은 개발 DB 에도 생기지 않는다. 즉 **아무 설정 없이
`uvicorn main:app` 을 그냥 실행하면 MySQL이 없어서 startup 단계에서 실패한다.**

```text
[startup] 테이블 생성 단계의 연결 오류 예시 (표현은 드라이버·버전에 따라 다름)
(2003, "Can't connect to MySQL server on 'localhost'")
```

Redis ping이 먼저 성공해야 DB 생성 단계까지 도달한다. DB 서버 미기동뿐 아니라
호스트·포트·방화벽·인증 설정도 확인한다.

### MySQL 띄우기

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8.4
```

기본 설정값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_PASSWORD=""`,
`MYSQL_DATABASE=fastapi_db`)에 맞춘 로컬 예시다. 이미지 버전은 테스트용
`compose.test.yaml`과 같은 MySQL 8.4로 맞췄다(기본 인증 `caching_sha2_password`는 의존성의
`cryptography`로 처리된다). DB 준비 완료·접속 권한과 Redis 가용성도 확인한다. 빈 root
비밀번호는 로컬 전용이며 운영에 사용하지 않는다. `.env`를 복사해 쓰면 `.env.example`의
`MYSQL_PASSWORD=your_password`가 들어가므로 컨테이너 설정과 맞춰 고친다.

```bash
uv run uvicorn main:app --reload --port 8000
```

- API 문서: <http://127.0.0.1:8000/docs>
- 기능 API: `GET /api/v1/blog/posts`

---

## 환경 변수 — 무엇이 필수인가

설정 문자열은 모두 기본값이 있어 `.env` 없이도 읽히지만, 기본 주소의 Redis 서버는 반드시
접속 가능해야 한다. 처음에 의미 있는 것은 아래 정도이고, 나머지는 나중에 봐도 된다.

| 변수 | 기본값 | 첫 실행에서의 의미 |
|---|---|---|
| `DEBUG` | `true` | true=개발 테이블 생성 + `/docs` 켜짐 / false=둘 다 꺼짐. false여도 DB API·`/ready`·접속 로그 저장에는 MySQL 필요. Redis ping은 양쪽 모두 필수 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | startup `ping()` 대상. 연결 실패 시 서버가 시작되지 않는다 |
| `ADMIN` | `true` | `/admin` 관리 화면이 **기본으로 켜진다**. ⚠️ **인증이 없다** — 아래 주의 참고 |
| `ENV` | `development` | `production`/`staging`에서 `ADMIN=true`면 `ADMIN_UNAUTHENTICATED_ACK=true`가 없는 한 설정 로드가 실패한다 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / `""` / `fastapi_db` | 위 docker 명령과 맞춰져 있다 |
| `DB_ROUTER_ENABLED` | `false` | 기본은 단일 엔진. read/write 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 둬도 되지만 **배포 전 반드시 교체** |

> **⚠️ `ADMIN=true` 가 기본값이고 `/admin` 에는 인증이 없습니다.**
> 로컬 개발에서 바로 DB 를 들여다볼 수 있도록 한 **의도된 기본값**이지만, 그 말은
> 앱에 도달할 수 있는 누구나 사용자·게시글·접속로그를 조회·수정·삭제하고 CSV 로
> 내보낼 수 있다는 뜻입니다(비밀번호 해시만 제외). **운영·스테이징은 `ADMIN=false`**
> 를 명시하거나 리버스 프록시에서 `/admin` 을 막으세요.

전체 목록은 [`.env.example`](../../.env.example).

`.env` 를 쓰려면:

```bash
cp .env.example .env
```

PowerShell: `Copy-Item -LiteralPath .env.example -Destination .env`.
기존 `.env`가 있으면 덮어쓰지 않고 필요한 항목만 확인한다.
`DEBUG=false`의 미지정 로그 레벨은 INFO이다. `LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 명시값은
DEBUG보다 우선하므로 false여도 DEBUG 로그가 출력될 수 있다. 시작 로그의 `(DEBUG=%s)`는
메시지의 표시값이지 출력 조건문이 아니다.

---

## 선택 기능 — 지금은 몰라도 된다

기본 실행 경로에 **필요 없는** 것들이다. 필요해질 때 해당 문서를 보면 된다.

| 기능 | 필요 인프라 | 기본 상태 | 언제 보면 되나 |
|---|---|---|---|
| Celery 비동기 태스크 | startup에서 확인한 Redis | 꺼짐(워커 미기동) | 백그라운드 작업이 필요해질 때 |
| DB read/write 라우팅 | replica MySQL | 꺼짐 | 읽기 부하 분리가 필요할 때 |
| Alembic 마이그레이션 | MySQL | — | 운영 배포 시 (`DEBUG=false` 면 테이블 자동 생성이 꺼진다) |
| SQLAdmin 관리자 화면 | (앱 내장) | **켜짐** | `/admin` 으로 바로 접근. 인증 없음(위 주의) |

---

## 테스트 — 인프라 불필요

단위 테스트는 in-memory SQLite와 가짜 Redis를 쓰므로 외부 인프라 없이 돌아간다.
인프라가 필요한 두 마커(`mysql`, `browser`)는 빼고 돌린다.

```bash
uv run python -m pytest -m "not mysql and not browser" --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

마커를 빼지 않으면 `mysql` 테스트는 MySQL이 없을 때 skip되지만, `browser` 테스트는 skip하지
않고 **실패**한다. browser 테스트는 Chromium(`uv run python -m playwright install chromium`),
`compose.test.yaml`의 MySQL(`docker compose -f compose.test.yaml up -d --wait`), 그리고 startup
`ping()`이 통과할 Redis가 모두 있어야 한다. 검사 전체를 한 번에 돌리려면
`uv run python -m scripts.review_gate`(MySQL 통합 제외는 `--fast`)를 쓴다.

> `pytest` 가 아니라 **`python -m pytest`** 를 쓴다. 콘솔 스크립트(`uv run pytest`)가
> 다른 인터프리터를 집어 import 가 어긋난 전례가 있어 이쪽을 표준으로 삼는다.
> CI(`.github/workflows/ci.yml`)도 `python -m pytest -m "not mysql and not browser"`에
> 커버리지 85% 게이트를 붙여 돌리고, MySQL·browser 테스트는 별도 job에서 skip 금지로 돌린다.
>
> `--cache-dir .mypy_tmp` 는 로컬 편의용이다. **게이트 판정용 mypy 는 캐시를 지우고**
> 돌린 결과만 유효하다 — 따뜻한 캐시가 통과로 잘못 기록된 전례가 있어 CI 는 캐시를
> 복원하지 않는다.

---

## 새 기능 추가

골격을 만들고 `config.INSTALLED_APPS` 에 한 줄을 추가한다.

```powershell
uv run python -m scripts.new_app orders --with-models --with-admin
```

```python
# config.py
INSTALLED_APPS: list[str] = [
    # 기존 설치 앱 항목은 유지하고 아래 항목을 추가
    "app.features.orders.apps.OrdersConfig",   # ← 이 한 줄이 '설치'다
]
```

이 줄을 넣기 전까지 앱은 존재하지만 설치되지 않은 상태다 — 디렉터리가 있어도 route·모델·
Admin·`ready()` 어디에도 나오지 않는다. `main.py`·`migrations/env.py`·`session.py` 는
손대지 않는다. 미등록 상태는 `tests/core/apps/test_manual_registration.py` 가 고정한다.

생성기가 출력하는 안내대로 골격의 태그(`"Orders"`)도 `app/core/tags_metadata.py` 에 추가한다.
선언되지 않은 태그는 OpenAPI 계약 테스트에서 실패한다. 등록 후 `GET /api/v1/orders/ping` 으로
마운트를 확인하고 `uv run python -m pytest app/features/orders` 로 골격 테스트를 돌린다.

### 그다음 정할 것 — ORM 인가 Raw 인가

골격을 만들었으면 데이터 접근 방식을 고른다. 이 구조에서 **갈라지는 지점은 Repository
구현 하나뿐**이고 나머지 파일의 작성 방식은 같다.

- **기본값은 ORM** — `BaseRepository` 를 상속한다. 예제:
  `app/features/catalog/repositories/product_repository.py`
- **집계·리포트처럼 ORM 이 버거우면 Raw** — `RawRepositoryBase` 를 상속한다. 예제:
  `app/features/reports/repositories/sales_report_repository.py`

판단 기준과 Raw 전용 제약(bind parameter 강제, `query_name` 코드 상수, 방언 함수 배제)은
[ORM vs Raw 결정 가이드](../project-guide/v1.1/09-orm-vs-raw-decision.md) 에 있다.
심화 가이드 전체는 [docs/project-guide/v1.1/](../project-guide/v1.1/README.md).

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동·주소/포트/인증 오류 | REDIS_* 설정과 서버 가용성 확인. DEBUG=false로 우회되지 않음 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` 에서는 문서가 꺼진다 | `DEBUG=true` (MySQL 필요) |
| 기능 API만 500 | 앱은 떴지만 DB가 없다 | 2단계 진행 |
| 새 기능이 마운트 안 됨 | `config.INSTALLED_APPS` 에 `AppConfig` 미등록 | `config.py` 의 `INSTALLED_APPS` 에 `"app.features.<name>.apps.<Name>Config"` 추가 후 재기동. `main.py` 는 손대지 않는다 |
| 앱은 등록했는데 route 가 안 뜸 | `api/routers/router.py` 의 `<name>_router` 컨벤션 이름 불일치, 또는 내부 import 실패 | 이름 확인. module 은 있는데 공개 이름이 없거나 import 가 깨지면 **기동이 실패**한다 |

---

## 과거 실행 기록과 현재 검토 범위

**2026-09-17:** 현재 코드·설정·문서 연결을 검토했다. 이번에 실제로 실행한 것은
`uv run python -m pytest -m "not mysql and not browser"`(609 passed, 22 deselected),
`python -m scripts.new_app --help`, `create_app()` 조립 후 OpenAPI 경로 목록 확인까지다.
아래 실행 수치와 HTTP 결과는 **Redis 필수 startup 검증 도입 전의 과거 기록**이며 현재
테스트 수나 Redis 없이 기동할 수 있다는 근거가 아니다. 현재 실제 서버·MySQL·Redis 성공
연결 검증을 새로 수행한 기록은 아니다.

**과거 확인: 2026-08-12** (FastAPI 0.141.x, Python 3.14). 아래는 당시 실제로 실행하거나
설정값을 읽어 대조한 결과다.

| 항목 | 방법 | 결과 |
|---|---|---|
| `DEBUG=false` 기동 → `/health` | 요청 | **200** `{"status":"healthy","version":"0.1.0"}` — 위 응답 예시와 일치 |
| `DEBUG=false` → `/docs` · `/openapi.json` | 요청 | **404** 둘 다 |
| 기본값(`DEBUG=true`) + MySQL 없음 → startup 실패 | 기동 | 확인 |
| 표의 기본값 전부 | `config.py` 필드 기본값 직접 읽기 | 일치 (`DEBUG`·`ADMIN`·MySQL 4종·`DB_ROUTER_ENABLED`·토큰 키 2종) |
| pytest / ruff / mypy | 실행 | 186 passed · 청정 · 146 files Success |

MySQL `docker run` 이후 경로는 이 환경에 Docker 가 없어 **실행 확인하지 못했다.** 설정
기본값과 대조해 작성했으므로, 다를 경우 이 문서를 고쳐 주기 바란다.
