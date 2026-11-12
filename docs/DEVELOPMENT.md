# 개발 가이드

## 1. 새 기능 추가

### 골격 만들기

```bash
uv run python -m scripts.new_app orders                              # apps.py·라우터·서비스·테스트 + 빈 계층 package
uv run python -m scripts.new_app orders --with-models --with-admin   # models·admin_views 까지
```

`app/features/orders/` 에 표준 구조와 `apps.py`(`OrdersConfig`)가 생긴다. 이름은 snake_case 식별자여야 하고, 이미 있는
경로는 덮어쓰지 않는다(임시 디렉터리에 다 만든 뒤 옮기므로 실패해도 반쯤 만든 앱이 남지 않는다).
**생성기는 설정 파일을 고치지 않는다** — 출력에 나온 두 항목을 직접 붙인다.

1. `config.py` 의 `INSTALLED_APPS` 에 `"app.features.orders.apps.OrdersConfig",` 를 추가한다. 순서가 라우터·Admin 등록 순서다.
2. `app/core/tags_metadata.py` 에 태그 `{"name": "Orders", "description": ...}` 를 추가한다 — 선언하지 않은 태그와
   쓰지 않는 태그는 OpenAPI 계약 테스트가 실패시킨다.

등록하면 `GET /api/v1/orders/ping` 이 열린다. Celery 태스크가 필요하면 기능 루트에 `tasks.py` 를 두면 워커가 include 한다.

### 계층별로 채우기

- **models/**: `Base` 와 공통 Mixin(`UUIDPrimaryKeyMixin`·`TimestampMixin` 등, `app/core/models/models_base.py`)을 조합한다.
  시각 컬럼은 `Mapped[datetime]`(자동으로 `UTCDateTime`) — 값은 aware datetime 으로 넣는다.
- **repositories/**: ORM 이면 `BaseRepository[Model, PK]`, Raw SQL 이면 `RawRepositoryBase`.
  Raw 는 `query_name` 을 코드 상수로 주고 값은 bind parameter 로만 넘긴다(f-string·`%`·`.format()`·문자열 연결 금지).
  조회는 `read_intent()`, 쓰기는 `write_intent()` 를 붙인다. Repository 는 커밋하지 않는다.
- **services/**: `BaseService` 상속. 업무 규칙만, 커밋하지 않는다. Raw 결과(`RowMapping`)는 여기서 DTO 로 검증한다.
- **dependencies/**: 조회용 provider 는 `get_read_only_db_session`, 쓰기용은 `get_writer_db_session` 으로 Service 를 만든다.
- **schemas/**: 요청·응답 DTO. 부분 수정 스키마는 `PatchSchema` 를 상속한다. 공개 DTO 클래스 이름은 프로젝트 전체에서 고유해야 한다.
- **api/routers/v1/**: path operation. 규칙:
  - 접근 수준을 하나 선언한다 — `dependencies=[Public]`·`[PublicWrite]`·`[LoginRequired]`·`[SuperuserRequired]` 또는
    인자 `CurrentPrincipal`·`SuperuserPrincipal`. 없으면 앱이 기동하지 않는다.
  - `operation_id`·`summary`·`description`·`response_model` 을 쓰고, path·query 파라미터에 `description` 을 단다.
    오류 응답은 `ErrorResponse` 를 참조한다.
  - 쓰기 핸들러는 응답 DTO 를 만든 뒤 `await service.commit()` 을 한 번 부른다.
  - 소유권이 있는 리소스는 `OwnershipPolicy` 로 판정하고 작성자는 인증 주체로 채운다.
- **admin.py**: 모델이 있으면 `admin_views` 를 노출한다. 비밀번호 같은 민감 컬럼은 목록·상세·폼·내보내기에서 제외한다.
- **apps.py**: 기동 시 결선이 필요하면 `ready()` 를 쓴다 — DB·네트워크·subprocess 를 부르지 않는다.

참고 구현은 `catalog`(ORM)과 `reports`(Raw SQL)다. 두 기능은 Repository 만 다르고 나머지 구조가 같다.

## 2. 마이그레이션

`migrations/env.py` 는 `config.db_settings.ALEMBIC_URL` 로 접속한다 — 기본은 primary DSN 의 드라이버를 PyMySQL 로 바꾼 값이고,
`ALEMBIC_DATABASE_URL` 이 있으면 그 값을 쓴다. 대상 테이블은 `INSTALLED_APPS` 에 등록된 앱의 models 뿐이다.

```bash
uv run alembic revision --autogenerate -m "add orders"   # 모델 변경 후
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic check                                     # 모델과 DB 차이가 없는지
```

- `UTCDateTime` 은 autogenerate 가 `sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql')` 로 적는다(`render_item`) —
  migration 파일이 앱 모듈을 import 하지 않게 하기 위해서다.
- 리비전은 `migrations/versions/0001_baseline_schema.py`(현재 모델 전체) 하나에서 시작한다. 새 리비전은 이 위에 쌓는다.
- 생성된 파일은 MySQL 기준으로 읽어 본다. 모델에 `server_default` 가 있으면 방언 중립 표현(`sa.false()` 등)인지 확인한다.
- 외부 DB 없이 확인하려면 빈 SQLite 를 대상으로 돌린다:
  `ALEMBIC_DATABASE_URL=sqlite:///./tmp.sqlite3 ENV=test uv run alembic upgrade head`.

## 3. 테스트

### 실행

```bash
uv run python -m pytest                              # 전체 (pyproject: ENV=test, DEBUG=true, asyncio auto)
uv run python -m pytest app/features/catalog         # 기능 하나
uv run python -m pytest --cov=app --cov-report=term-missing
```

테스트는 in-memory SQLite(aiosqlite)와 fakeredis 로만 돈다. `DeprecationWarning` 은 실패로 취급하고(`filterwarnings`),
skip·xfail 은 게이트가 실패로 본다 — 조건부로 건너뛰는 테스트를 만들지 않는다.

**MySQL 테스트(`tests/mysql`)는 CI 전용**이다(`mysql` 잡이 `mysql:8.4` 서비스로 돈다). 평소 `pytest`·게이트는 이 폴더를
수집하지 않는다(pyproject `norecursedirs`). 로컬에서 돌리려면 **자기 소유의 빈 MySQL** 을 주고 경로를 직접 지정한다 —
테스트가 DB·사용자를 만들고 지우므로 그 권한이 필요하다. 변수가 없으면 접속 시도 없이 실패한다.

```bash
MYSQL_TEST_URL=mysql+aiomysql://root:<pw>@<host>:<port> uv run python -m pytest tests/mysql
```

### 구조

| 위치 | 대상 |
|---|---|
| `app/features/<name>/tests/` | 그 기능의 API(상태 코드·검증·응답·권한·페이지네이션)와 트랜잭션 경계 |
| `tests/core/apps/` | App Registry — 등록·population 순서·오류·결선 (`_fixtures/` 는 가짜 앱 package) |
| `tests/core/security/` | 비밀번호·토큰·refresh 저장·레이트 리밋·접근 정책·관리 화면 인증·세션 |
| `tests/core/admin/` | 관리 화면 — CSRF·로그인 흐름·뷰·날짜 필터·비활성화·결선 |
| `tests/core/db/` | 세션·라우팅·읽기 전용 차단·DB 오류 변환·DSN·시각 타입·마이그레이션·엔진 수명 |
| `tests/core/` | 그 밖의 core — 조립·lifespan·미들웨어·예외 처리·Redis·설정 검증·Repository·Celery |
| `tests/utils/` | 로깅(구성·회전·가리기)·페이지네이션 |
| `tests/scripts/` | `scripts/` 동작(생성기·첫 관리자·게이트 판정) |
| `tests/*.py` | 여러 기능을 가로지르는 계약 — 인가 정책·소유권·OpenAPI·라우트 목록·트랜잭션 배선 |

공용 헬퍼:

- `tests/session_overrides.py` — `sqlite_session_overrides(app)`: 두 세션 의존성을 운영과 같은 표시(`mark_read_only`·`using_writer`)를
  붙인 SQLite 세션으로 바꾼다. 엔드포인트 테스트는 세션 의존성을 손으로 override 하지 않고 이 헬퍼를 쓴다.
- `tests/auth_headers.py` — 실제 `TokenService` 로 발급한 Bearer 헤더(`admin_headers()` 등). 인증 의존성을 override 하지 않는다.
- `tests/admin_login.py` — 브라우저처럼 CSRF 토큰을 실어 `/admin` 에 로그인·로그아웃한다.
- `tests/openapi_check.py` — 응답 값을 앱의 OpenAPI 스키마와 대조한다.
- 루트 `conftest.py` — SQLite 날짜 어댑터 등록, `restore_config`(설정 reload 후 원래 객체로 복구).
  가까운 디렉터리의 `conftest.py` 에 그 범위의 픽스처를 둔다(`tests/core/apps/`, `tests/utils/`).

### 작성 규칙

- 사용자가 관찰하는 동작이나 깨지면 사고가 나는 불변식을 검증한다 — 상태 코드·응답 본문·DB 에 남은 값·로그 출력·커밋 횟수.
  문서 문구나 파일 이름·위치를 검사하는 테스트는 만들지 않는다.
- 엔드포인트는 `httpx.AsyncClient(transport=ASGITransport(app=...))` 로 부른다.
- Redis 가 필요한 부품은 `fakeredis` 로 실물 클래스를 돌린다.
- 설정을 바꾸는 테스트는 `monkeypatch.setenv` + `importlib.reload(restore_config)` 를 쓴다.
- 보안 검사처럼 "아무것도 못 찾아서 통과" 할 수 있는 정적 검사는 탐지기가 실제로 잡는지도 함께 확인한다.
- 같은 동작을 여러 파일에서 다시 검증하지 않는다.

## 4. 게이트와 CI

로컬 게이트:

```bash
uv run python -m scripts.review_gate          # 전체
uv run python -m scripts.review_gate --list   # 단계 목록만
```

단계: `ruff format --check` → `ruff check` → `mypy` → bandit(MEDIUM 이상, `scripts.bandit_gate`) → `pip-audit --strict` →
pytest(커버리지 측정, skip·xfail·xpass 가 있으면 실패) → OpenAPI 규칙 fail-on-revert(`scripts.openapi_revert_check`).
실패해도 끝까지 돌고 마지막에 요약한다. 커버리지 하한은 `pyproject.toml` 의 `fail_under` 하나가 정한다.

`scripts.openapi_revert_check` 는 OpenAPI 규칙 테스트(`tests/test_openapi_contract.py`)마다 그 규칙이 막으려는 결함을 소스에
실제로 넣어 보고, 해당 테스트가 실패하는지 확인한 뒤 원본으로 되돌린다. 규칙 테스트를 추가·이름 변경하면 이 스크립트의
`CASES` 도 함께 고친다. 같은 저장소에서 동시에 두 번 돌지 않도록 temp 의 락 파일로 순서를 맞춘다.

CI(`.github/workflows/ci.yml`)는 push·PR·주 1회 일정으로 같은 검사를 단계별로 돈다:
`uv sync --locked` → ruff(lint·format) → mypy → bandit gate → pip-audit → pytest(커버리지) → skip·xfail 0건 확인 →
OpenAPI fail-on-revert → alembic 단일 head → 빈 SQLite 에 `alembic upgrade head` + `alembic check`.
별도 `mysql` 잡이 `tests/mysql` 을 MySQL 8.4 서비스 컨테이너에서 돌리고 skip·xfail 0건을 확인한다(로컬 게이트에는 없다).
의존성을 바꾸면 `uv lock` 으로 `uv.lock` 을 함께 갱신한다(`--locked` 가 어긋나면 실패한다).
