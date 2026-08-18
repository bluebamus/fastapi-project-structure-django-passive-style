# 프로젝트 개요

| 항목 | 값 |
|---|---|
| 문서 버전 | 1.0.0 |
| 작성일 | 2026-08-18 |
| 대상 프로젝트 | fastapi-default-project-structure 0.1.0 |
| 적용 코드 기준 | Git `9c93803` |

## 1. 프로젝트 정의

이 저장소는 FastAPI, SQLAlchemy 2 비동기 ORM, Pydantic v2를 기반으로 한 백엔드 템플릿이다. 일반적인 계층형 구조인 `Router → Service → Repository → Database`에 Django의 `INSTALLED_APPS`와 `AppConfig` 개념을 결합했다.

핵심 원칙은 다음과 같다.

- 기능 디렉터리가 존재하는 것만으로는 활성화되지 않는다.
- `config.py`의 `INSTALLED_APPS`가 설치 앱의 유일한 진실 공급원이다.
- 설치 앱 순서가 모델 로드, `ready()`, Router, Admin 등록 순서를 결정한다.
- Router는 요청·응답과 커밋 경계를, Service는 유스케이스를, Repository는 영속성 연산을 담당한다.
- 조회와 쓰기를 구분하고, 필요하면 primary/replica 라우팅을 활성화할 수 있다.
- 요청 밖 작업은 별도 DB 풀을 사용한다.

## 2. 주요 기술

| 영역 | 기술 | 현재 역할 |
|---|---|---|
| Web API | FastAPI 0.141 계열 | 라우팅, DI, OpenAPI, 수명주기 |
| ORM | SQLAlchemy 2.0 | 비동기 모델·쿼리·세션 |
| Migration | Alembic | 운영 스키마 변경 |
| Validation | Pydantic 2 | 요청·응답·환경 설정 검증 |
| Database | MySQL + aiomysql | 기본 비동기 데이터 저장소 |
| Admin | SQLAdmin | 조건부 `/admin` 관리 화면 |
| API Docs | Scalar | DEBUG 환경의 `/docs` UI |
| Background | Celery + Redis | 요청 밖 분산 작업 |
| Logging | python-json-logger | 콘솔·파일 구조화 로그 |
| Test/Quality | pytest, Ruff, mypy, Bandit | 회귀·정적·보안 검사 |
| Runtime | Python 3.12 이상, uv | 실행 환경과 의존성 관리 |

## 3. 현재 설치 기능 앱

`config.INSTALLED_APPS`의 현재 순서는 아래와 같다.

| 순서 | 앱 | 주 기능 | 기본 API prefix |
|---:|---|---|---|
| 1 | home | 접속 로그 조회·통계, 로그 sink 결선 | `/api/v1/home` |
| 2 | blog | 블로그 게시글 CRUD | `/api/v1/blog` |
| 3 | reply | 댓글 CRUD | `/api/v1/reply` |
| 4 | sns | SNS 피드 게시물 CRUD | `/api/v1/sns` |
| 5 | user | 사용자 CRUD | `/api/v1/user` |
| 6 | auth | 회원가입, 로그인, 토큰 갱신, 현재 사용자 | `/api/v1/auth` |

공통으로 `/health`가 제공된다. `/docs`와 `/openapi.json`은 `DEBUG=true`일 때만 제공된다. `/admin`은 `ADMIN=true`일 때만 설치된다.

## 4. 저장소 구조

```text
.
├── main.py                       # 실행 진입점
├── config.py                     # 설정과 INSTALLED_APPS
├── app/
│   ├── core/                     # 조립, 앱 registry, DB, 예외, middleware
│   ├── features/                 # 도메인별 기능 앱
│   ├── celery/                   # 중앙 Celery 앱과 태스크
│   └── utils/                    # 인증, 로그, 페이지네이션, 검증
├── migrations/                   # Alembic 환경과 revision
├── scripts/new_app.py            # 신규 기능 앱 scaffold
├── tests/                        # 공통·통합·계약 테스트
└── docs/                         # 설계·사용·계획 문서
```

기능 앱의 대표 구조는 다음과 같다.

```text
app/features/<feature>/
├── apps.py                       # AppConfig
├── api/routers/                  # 모듈 Router와 v1 엔드포인트
├── dependencies/                 # 세션을 Service로 결합하는 FastAPI DI
├── services/                     # 유스케이스와 비즈니스 규칙
├── repositories/                 # SQLAlchemy 영속성 연산
├── models/                       # SQLAlchemy 모델(선택)
├── schemas/                      # Pydantic 요청·응답 모델
├── admin.py                      # SQLAdmin view(선택)
├── exceptions.py                # 기능별 예외
└── tests/                        # 기능 단위·통합 테스트
```

## 5. 실행 프로필

| 프로필 | 핵심 설정 | 동작 |
|---|---|---|
| 로컬 개발 | `DEBUG=true` | 시작 시 테이블 생성, Scalar/OpenAPI 활성 |
| 운영 | `DEBUG=false` | 자동 테이블 생성과 API 문서 비활성, Alembic 사용 |
| Admin 사용 | `ADMIN=true` | 인증 없는 SQLAdmin이 `/admin`에 설치됨 |
| 단일 DB | `DB_ROUTER_ENABLED=false` | 모든 구문이 primary 엔진 사용 |
| 읽기 분리 | Router·replication·replica 설정 활성 | SELECT를 replica로 분산, 쓰기는 primary |

## 6. 현재 범위와 계획 문서의 구분

현재 구현은 SQLAlchemy ORM 기반 `BaseRepository`를 사용한다. `docs/orm-raw-repository/`의 ORM/Raw 이중 Repository, 새 세션 이름, Raw SQL 안전 API 등은 고도화 계획이며 기준 커밋의 런타임 기능이 아니다. 구현 여부를 판단할 때는 문서 제목이 아니라 실제 코드와 테스트를 우선한다.

## 7. 다음 문서

- 구조와 경계: [시스템 설계](02-system-design.md)
- 기능 목록: [핵심 구성요소와 기능](03-core-components-and-features.md)
- 첫 요청 추적: [전체 요청 워크플로](04-request-workflow.md)

## 변경 이력

| 문서 버전 | 작성일 | 변경 내용 |
|---|---|---|
| 1.0.0 | 2026-08-18 | 현재 프로젝트 범위와 기술·기능·구조 최초 정리 |
