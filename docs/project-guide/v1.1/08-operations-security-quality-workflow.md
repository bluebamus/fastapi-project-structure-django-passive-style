# 운영·보안·품질 워크플로

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.1.0 |
| 작성일 | 2026-08-20 |
| 대상 프로젝트 | fastapi-project-structure-django-passive-style 0.1.0 |
| 적용 코드 기준 | Git `b88f654` |

## 1. 로컬 개발 흐름

```powershell
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn main:app --reload
```

기본 `DEBUG=true`에서는 시작 시 `create_all`도 실행되지만, migration과 실제 스키마의 차이를 조기에 확인하려면 로컬에서도 Alembic 적용을 권장한다. 상세 설치 변수는 [빠른 시작 문서](../../QUICKSTART.md)를 따른다.

## 2. 운영 배포 전 필수 설정

| 항목 | 운영 기준 |
|---|---|
| `DEBUG` | `false`; 상세 오류, Scalar와 OpenAPI 비활성 |
| `ADMIN` | `false` 권장; 활성 시 프록시 접근 통제 필수 |
| JWT secrets | Access/Refresh를 서로 다른 충분히 긴 비밀값으로 주입 |
| DB credentials | 기본값을 사용하지 않고 secret store에서 주입 |
| CORS | 실제 frontend origin만 허용 |
| Redis | 인증·네트워크 접근 통제와 TLS/사설망 정책 검토 |
| `SERVER_HOST` | 노출 범위에 맞게 지정하고 reverse proxy 사용 검토 |
| Migration | 애플리케이션 시작 전 `alembic upgrade head` 적용 |
| Log | 민감값 필터와 보존·회전 정책 확인 |

<!-- VERIFY: 실제 운영 플랫폼의 secret store, TLS 종료, 프록시 ACL, backup/restore 정책은 저장소에서 확인할 수 없으므로 배포 환경에서 별도 검증해야 한다. -->

## 3. 주요 보안 경계

### Admin

현재 SQLAdmin에는 인증 backend가 없다. `ADMIN=true`이면 `/admin`에서 게시글, 댓글, 사용자, 접속 로그 등의 조회·수정·삭제와 CSV export가 가능하다. 운영에서는 `ADMIN=false`가 기본 운영 원칙이며, 불가피하게 켤 경우 외부 인증 proxy, IP allowlist 또는 private network로 차단해야 한다.

### API 문서와 오류 상세

`DEBUG=false`는 `/docs`, `/openapi.json`과 처리되지 않은 예외 상세를 비활성화한다. 이는 운영 정보 노출을 줄이는 조건이므로 배포 환경에서 강제해야 한다.

### JWT와 비밀번호

- 비밀번호는 bcrypt hash로 저장한다.
- Access/Refresh Token은 별도 secret과 token type을 사용한다.
- 운영 secret을 저장소나 문서에 기록하지 않는다.
- 현재 token blacklist가 없으므로 유출 token의 즉시 폐기 요구가 있으면 별도 저장·회수 설계가 필요하다.

### CORS

credential을 허용하면서 광범위한 origin을 설정하지 않는다. 브라우저 CORS는 서버 간 호출이나 인증·권한 검사를 대체하지 않는다.

### 접속 로그와 Proxy header

middleware는 `X-Forwarded-For`, `X-Real-IP`를 우선 사용한다. 신뢰할 수 있는 reverse proxy가 해당 header를 제거·재작성하도록 구성하지 않으면 클라이언트가 IP 값을 위조할 수 있다. Query string, Referer, User-Agent 등이 저장되므로 개인정보·민감정보 수집 및 보존 정책도 확인해야 한다.

## 4. 기동·가용성 검사

- `GET /health`는 프로세스 상태와 버전을 반환하는 liveness 성격의 endpoint다.
- 현재 `/health`는 DB나 Redis 연결을 검사하지 않는다.
- 현재 `/ready` endpoint는 없다.

<!-- VERIFY: 배포 오케스트레이터의 readiness 조건과 DB/Redis 의존성 검사 방식은 운영 플랫폼에서 별도 정의해야 한다. -->

## 5. Background와 Celery 운영

### In-process 접속 로그

- 동시 task 상한: 256
- 상한 초과: 원 요청을 막지 않고 drop count 증가
- 종료 drain timeout: 5초
- 전용 DB 풀: pool 10 + overflow 10

drop과 drain timeout log를 모니터링해야 한다. 접속 로그가 감사 목적의 필수 데이터라면 현재의 best-effort fire-and-forget 방식만으로는 충분하지 않으며 durable queue 전환을 검토해야 한다.

### Celery

- broker/backend: Redis
- serializer: JSON만 허용
- task 상태 추적 활성
- timezone: 애플리케이션 `TIME_ZONE`

Worker와 API 프로세스의 코드·환경 설정 버전을 맞추고, task retry/idempotency 정책은 실제 업무 task별로 정의해야 한다.

## 6. 로그 운영

로그 설정은 console/file 활성, level, 경로, 파일명, 최대 크기, backup 수, 포맷을 환경변수로 제어한다. DSN은 마스킹된 표현만 기록한다. 다음 값은 로그에 직접 남기지 않는다.

- Authorization header와 JWT 원문
- 비밀번호·hash·session secret
- DB/Redis/SMTP credentials
- 필요 이상으로 상세한 요청 body와 개인정보

## 7. 품질 게이트

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app config.py main.py scripts
uv run pytest
uv run bandit -r app config.py main.py scripts
```

| 게이트 | 확인 내용 |
|---|---|
| pytest | 앱 Registry 계약, route, CRUD, 트랜잭션, DB Router, migration, 문서 링크 |
| Ruff | 문법·import·일반 결함과 format |
| mypy | 주요 애플리케이션 코드의 타입 계약 |
| Bandit | Python 정적 보안 패턴 |

현재 pytest 설정은 `tests`와 `app`의 `test_*.py`를 수집하고 strict marker를 사용한다. 변경 범위의 기능 테스트를 먼저 실행한 뒤 전체 suite를 실행한다.

## 8. 변경 유형별 검증

| 변경 | 최소 검증 |
|---|---|
| 신규 AppConfig/Router | registry, wiring, route inventory, 신규 앱 테스트 |
| Model/Repository | 기능 DB 테스트, repository test, Alembic chain |
| 세션/DB Router | transaction boundary, read path, DB router 전체 테스트 |
| 인증 | auth endpoint, token utility, 비밀번호·email validation |
| Middleware | access-log decoupling, background task, CORS 테스트 |
| 문서 | `tests/test_docs_consistency.py`와 상대 링크 검사 |

## 9. 배포 흐름

```mermaid
flowchart LR
    A[Dependency lock 확인] --> B[정적 검사와 전체 테스트]
    B --> C[운영 secret/config 주입]
    C --> D[Alembic migration 적용]
    D --> E[API/Worker 배포]
    E --> F[/health 확인]
    F --> G[로그·DB pool·background drop 모니터링]
```

<!-- VERIFY: 무중단 migration 순서, rollback 전략, backup 복구 시험은 실제 배포 인프라와 데이터 중요도에 맞춰 승인해야 한다. -->

## 10. 알려진 제한과 후속 개선 후보

1. Admin 인증 부재: 운영 기본 비활성 유지 또는 인증 gateway 도입
2. Readiness probe 부재: DB·Redis 의존성을 포함한 `/ready` 설계
3. JWT 즉시 폐기 부재: refresh token rotation과 revoke 저장소 검토
4. 접속 로그 best-effort: 감사 요건이 있으면 durable queue 사용
5. Proxy header 신뢰 범위: trusted proxy 목록과 header 정규화 도입
6. Raw Repository: 계획 문서 검토·구현·회귀 검증 전까지 현재 기능으로 안내하지 않음

## 11. 관련 문서

- [프로젝트 개요](01-project-overview.md)
- [앱 등록 및 기동 워크플로](05-app-registry-and-startup-workflow.md)
- [데이터 접근 및 트랜잭션 워크플로](06-data-and-transaction-workflow.md)

## 변경 이력

| 문서 버전 | 작성일 | 변경 내용 |
|---|---|---|
| 1.0.0 | 2026-08-18 | 개발·배포·보안·로그·품질과 제한사항 최초 정리 |
