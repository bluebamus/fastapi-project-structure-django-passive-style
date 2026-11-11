# FastAPI Project Structure — Django Passive Style

Django 식 **수동 앱 설치**를 보여 주는 FastAPI 프로젝트 골격입니다. 설치할 기능 앱은
`config.INSTALLED_APPS` 한 곳에 적고, 적힌 앱만 Router·Model·Admin·`ready()`·Celery 태스크가 붙습니다.
`app/features/` 아래에 디렉터리를 만드는 것만으로는 아무것도 켜지지 않습니다 — 자동 발견을 하지 않는
것이 이 스켈레톤이 보여 주려는 성질입니다. 새 기능의 골격은 `scripts/new_app.py` 가 만들고, 등록은 사람이 합니다.

이 저장소가 함께 보여 주는 것:

- 계층 분리 — Router → Dependency → Service → Repository → DB, 기능마다 `app/features/<name>/`
- 명시적 트랜잭션 경계 — 조회는 읽기 전용 세션, 쓰기는 writer 세션 + 핸들러 본문의 커밋
- 같은 구조의 두 데이터 접근 예제 — `catalog`(ORM) · `reports`(Raw SQL)
- 선택적 primary/replica 읽기·쓰기 라우팅
- JWT 인증(access/refresh 회전) · 슈퍼유저 전용 SQLAdmin(`/admin`, Redis 서버 세션 + CSRF)
- 운영 기본기 — `/health`·`/ready`, 불투명한 500, SQL·비밀값 로그 차단, 기동 시 설정 검증

## 기술 스택

Python ≥ 3.13(로컬·CI 는 `.python-version` 의 3.14) · uv · FastAPI · SQLAlchemy 2.0 async · Alembic ·
MySQL(aiomysql, 마이그레이션은 PyMySQL) · Redis 7.0 이상(필수) · Celery 5 · Pydantic v2 · SQLAdmin · Scalar.
정확한 버전은 `pyproject.toml` 과 `uv.lock` 이 정합니다.

## 빠른 시작

```bash
uv sync
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # 비밀 키마다 한 번씩
```

`.env` 에서 최소한 다음을 채웁니다. 예시 값 그대로면 **개발 환경에서도 기동하지 않습니다**.

| 설정 | 할 일 |
|---|---|
| `ACCESS_TOKEN_SECRET_KEY` · `REFRESH_TOKEN_SECRET_KEY` · `SESSION_SECRET_KEY` | 서로 다른 32자 이상 무작위 값 |
| `MYSQL_HOST` · `MYSQL_USER` · `MYSQL_PASSWORD` · `MYSQL_DATABASE` | 사용할 MySQL. 비밀번호는 비우거나 예시 값이면 거부된다 |
| `REDIS_HOST` · `REDIS_PORT` | Redis 7.0 이상. 기동 시 ping·버전을 확인하고 실패하면 시작하지 않는다 |

`.env` 없이 환경 변수만으로 주입하는 배포(컨테이너)는 `ENV`, 비밀 키 3종, `MYSQL_HOST/USER/PASSWORD/DATABASE` 가
모두 있어야 기동합니다. 전체 설정 키와 설명은 `.env.example` 에 있습니다(자동으로 읽히지는 않습니다).

## 실행

```bash
uv run uvicorn main:app --reload --port 8000     # 또는 uv run python main.py
```

- `DEBUG=true`(기본)는 기동 시 설치 앱의 테이블을 `create_all` 로 만들고 `/docs`(Scalar)·`/openapi.json` 을 엽니다.
- `DEBUG=false` 는 둘 다 끕니다. 스키마는 `uv run alembic upgrade head` 로 만듭니다.
- 헬스체크: `/health`(프로세스만), `/ready`(DB·Redis 확인, 실패 시 503).
- 관리 화면 `/admin` 은 활성 슈퍼유저만 들어갑니다. 첫 계정:
  `uv run python -m scripts.create_superuser --username admin --email admin@example.com`
  (비밀번호는 대화형으로 묻거나 `--password-stdin`). 관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true`.
- Celery(접속 로그 통계·보존 삭제 태스크):
  `uv run celery -A app.celery.app worker --loglevel=info`, 주기 작업은 `uv run celery -A app.celery.app beat --loglevel=info` 를 하나만 띄웁니다.

배포 전에는 `TRUSTED_PROXY_HOPS`(프록시 뒤면 앞단 프록시 단 수), `ACCESS_LOG_RETENTION_DAYS`, `ENV=production` 을 확인합니다.
production/staging 에서는 `DEBUG=true`·`LOG_LEVEL=DEBUG`·`LOG_SQL_ECHO_ENABLED=true` 로는 기동하지 않습니다.

## 테스트

테스트는 SQLite(in-memory)와 fakeredis 로만 돌며 외부 인프라가 필요 없습니다.

```bash
uv run python -m pytest                    # 전체
uv run ruff check . && uv run ruff format --check .
uv run python -m scripts.review_gate       # 로컬 게이트 일괄 (ruff·mypy·bandit·pip-audit·pytest·OpenAPI 규칙 검사)
```

## 문서

| 문서 | 내용 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 디렉터리 구조, 계층, 세션·라우팅, 인증·권한, 관리 화면, 미들웨어, 로깅, Celery, 수명주기 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 새 기능 추가, 테스트 구조와 작성 규칙, 마이그레이션, 게이트·CI |
