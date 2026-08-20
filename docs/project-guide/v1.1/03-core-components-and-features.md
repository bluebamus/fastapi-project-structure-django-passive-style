# 핵심 구성요소와 기능

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.1.0 |
| 작성일 | 2026-08-20 |
| 대상 프로젝트 | fastapi-project-structure-django-passive-style 0.1.0 |
| 적용 코드 기준 | Git `b88f654` |

## 1. 진입점과 설정

| 구성요소 | 경로 | 역할 |
|---|---|---|
| 실행 진입점 | `main.py` | 전역 `app` 생성, 직접 실행 시 Uvicorn 시작 |
| 앱 factory | `app/core/bootstrap.py` | Registry population부터 Router/Admin까지 조립 |
| 설정 | `config.py` | 앱·DB·CORS·로그·Redis·JWT·세션·SMTP·업로드 설정 |
| 설치 앱 목록 | `config.INSTALLED_APPS` | 활성 앱과 로딩 순서의 단일 기준 |

주요 조건부 기능은 `DEBUG`, `ADMIN`, `DB_ROUTER_ENABLED`, `DB_REPLICATION_ENABLED`, `ACCESS_LOG_ENABLED`로 제어된다.

## 2. 앱 관리 구성요소

| 구성요소 | 공개 책임 |
|---|---|
| `AppConfig` | 설치 항목 해석, 앱 metadata와 선택 모듈 import |
| `Apps` | config·model·ready lifecycle과 조회 API |
| `install_routers()` | 설치 앱 Router를 순서대로 `/api`에 마운트 |
| `install_admin()` | 설치 앱의 `admin_views` 등록 |
| `create_admin()` | SQLAdmin 지연 import와 `/admin` 생성 |
| 앱 예외 | 중복 label, 준비 전 조회, 잘못된 config와 route 충돌을 명시적으로 실패 처리 |

## 3. 데이터 구성요소

| 구성요소 | 역할 |
|---|---|
| `Base` | 모든 SQLAlchemy model의 declarative base |
| `CRUDBase` | 내부 단건 add/get/update/delete 기본 연산 |
| `BaseRepository` | CRUD, bulk, 필터, eager/partial load, batch, join, upsert 계열 기능 |
| `BaseService` | session 보관과 공통 `commit()`·`rollback()` |
| `DatabaseRouter` | statement 성격과 세션 표시에 따른 writer/reader 선택 |
| `get_routed_db_session()` | 일반 요청 세션, 예외 시 rollback |
| `get_read_only_db_session()` | Router 활성 시 쓰기 차단 및 reader 사용 |
| `get_writer_db_session()` | 처음부터 writer에 고정 |
| `background_session()` | 요청 밖 별도 풀 세션 context manager |

## 4. Web 공통 기능

### 예외 응답

전역 handler는 애플리케이션 예외, Pydantic 요청 검증 예외, Starlette HTTP 예외, 처리되지 않은 예외를 공통 `ErrorResponse` 형태로 변환한다. 처리되지 않은 예외 상세는 `DEBUG=true`에서만 응답에 포함된다.

### API 문서와 헬스체크

- `GET /health`: 상태와 애플리케이션 버전을 반환한다.
- `GET /docs`: DEBUG 환경에서 Scalar UI를 반환한다.
- `/openapi.json`: DEBUG 환경에서만 제공한다.
- Swagger UI와 ReDoc은 비활성화되어 있다.

### Middleware

| Middleware/지원 객체 | 기능 |
|---|---|
| `CORSMiddleware` | 설정 기반 origin, credential, method, header 정책 |
| `UserInfoMiddleware` | IP, User-Agent, 경로, method, 응답 상태·시간 수집 |
| `AccessLogSink` | core에서 저장 구현을 분리하는 Protocol |
| `BackgroundTaskRunner` | 접속 로그 task 상한, drop 집계, shutdown drain |

## 5. 인증 기능

- bcrypt로 비밀번호를 해시·검증한다.
- Access Token과 Refresh Token에 서로 다른 secret과 만료 설정을 사용한다.
- JWT payload에 subject, token type, issued-at, expiry를 기록한다.
- OAuth2 password form으로 로그인한다.
- Bearer Access Token으로 `/me`의 현재 사용자를 해석한다.
- 비활성 또는 존재하지 않는 사용자는 인증 실패 처리한다.

현재 코드에는 token blacklist, refresh token 저장소, 강제 로그아웃 endpoint가 없다.

## 6. 도메인 기능

| 앱 | Model | Service/Repository 기능 |
|---|---|---|
| home | `UserAccessLog` | 접속 로그 목록·최근·IP·사용자·기간 조회와 장치/OS/브라우저 통계 |
| blog | `Post` | 게시글 생성·목록·단건·수정·삭제 |
| reply | `Reply` | 댓글 생성·목록·단건·수정·삭제 |
| sns | `SnsPost` | 피드 게시물 생성·목록·단건·수정·삭제 |
| user | `User` | 사용자 생성·목록·단건·수정·삭제, username 조회 |
| auth | `User` 재사용 | 가입·자격 검증·토큰 발급·현재 사용자 조회 |

## 7. 운영 지원 기능

| 기능 | 구현 위치 | 설명 |
|---|---|---|
| Alembic metadata 결선 | `migrations/env.py` | 설치 앱 model만 autogenerate 대상에 포함 |
| 신규 앱 scaffold | `scripts/new_app.py` | 표준 패키지를 임시 경로에 만든 뒤 원자적으로 이동 |
| 중앙 Celery | `app/celery/` | Redis broker/backend, JSON serializer, 앱 timezone |
| 구조화 로그 | `app/utils/logs/` | 콘솔·회전 파일·JSON 포맷과 Uvicorn 연동 |
| 페이지네이션 | `app/utils/pagination/` | 목록 endpoint 공통 offset/limit 응답 지원 |

## 8. 현재 제공하지 않는 기능

- Admin 인증 backend
- `/ready` 데이터베이스 readiness probe
- 자동 기능 디렉터리 탐색
- Raw SQL Repository 기반
- ORM/Raw 공통 dual-backend 계약
- API rate limiting

위 항목을 구현된 기능으로 전제하지 않아야 한다.

## 9. 관련 문서

- [기능별 워크플로](07-feature-workflows.md)
- [운영·보안·품질 워크플로](08-operations-security-quality-workflow.md)

## 변경 이력

| 문서 버전 | 작성일 | 변경 내용 |
|---|---|---|
| 1.0.0 | 2026-08-18 | 핵심 구성요소와 현재 기능·비기능 범위 최초 정리 |
