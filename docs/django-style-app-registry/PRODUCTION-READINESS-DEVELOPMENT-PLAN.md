# 운영 준비도 문제 분석 및 개발 작업 계획

## 1. 문서 정보

- 작성일: 2026-08-11
- 검토 기준 커밋: `0db2523`
- 대상: `fastapi-project-structure-django-passive-style`
- 목적: Django의 `INSTALLED_APPS`와 유사한 수동 앱 등록 구조를 유지하면서, 현재 구현을 안전하게 운영 배포할 수 있는 수준으로 보완한다.
- 기준 문서: `README.md`, `docs/ARCHITECTURE.md`

## 2. 최종 판정과 의미

현재 프로젝트는 다음 구조적 목표를 대체로 충족한다.

- `config.INSTALLED_APPS`를 설치 앱 목록의 단일 진실 공급원으로 사용한다.
- 등록 순서를 명시적으로 통제하면서 Router, Model, Admin을 컨벤션으로 결선한다.
- `Router → Dependency → Service → Repository → DB` 계층을 기능 앱별로 일관되게 적용한다.
- 기능 Dependency가 요청 성공 시 커밋하고, 세션 계층이 예외 시 롤백한다.
- Alembic 환경이 Registry를 사용해 등록 앱의 SQLAlchemy metadata를 수집한다.

그러나 현재 상태는 **개발 구조는 양호하지만 운영 배포 준비는 완료되지 않은 상태**다. 이유는 다음과 같다.

1. 기본 설정만으로 인증 없는 SQLAdmin이 노출될 수 있다.
2. Alembic migration이 등록된 전체 모델을 생성하지 않는다.
3. 접근 로그 API가 인증 없이 개인정보성 데이터를 반환한다.
4. Registry가 앱 내부 import 오류를 선택 모듈 부재로 오인할 수 있다.
5. 신규 앱 생성 안내가 수동 등록 정책과 모순된다.
6. 접근 로그의 프록시 신뢰, 민감정보 저장, 보존 정책이 정의되지 않았다.
7. 일부 설정과 종료 처리의 잘못된 조합 또는 타임아웃 동작이 강제되지 않는다.
8. 테스트 수는 충분하지만 migration 완전성, 인증 경계, coverage 기준을 보장하는 품질 게이트가 부족하다.

따라서 기능 추가보다 **보안 경계와 배포 스키마를 먼저 완성**해야 한다.

## 3. 문제 상세 분석

### P0-1. SQLAdmin 기본 공개 및 인증 부재

#### 현재 상태

- `config.py`의 `AppSettings.ADMIN` 기본값은 `True`다.
- `app/core/bootstrap.py`는 `ADMIN=True`일 때 인증 백엔드 없이 `sqladmin.Admin`을 생성한다.
- User, Blog, Reply, SNS Admin View는 생성·수정·삭제·내보내기를 허용한다.
- Access Log Admin도 삭제와 내보내기를 허용한다.

#### 영향

- 운영 환경에서 설정 누락만으로 `/admin`이 공개될 수 있다.
- 데이터 열람뿐 아니라 변경·삭제·내보내기까지 허용될 수 있다.
- 템플릿을 복제한 프로젝트가 안전하지 않은 기본값을 그대로 배포할 위험이 크다.

#### 목표 상태

- Admin은 기본 비활성화한다.
- 활성화하려면 인증 백엔드와 필수 보안 설정이 반드시 존재해야 한다.
- 운영 환경에서는 인증 없는 Admin 구성을 시작 단계에서 거부한다.
- 권한은 최소 권한 원칙에 따라 View별로 정의한다.

### P0-2. Alembic migration과 모델 metadata 불일치

#### 현재 상태

Registry가 모델을 import한 뒤 `Base.metadata.tables`에는 다음 테이블이 등록된다.

- `blog_posts`
- `replies`
- `sns_posts`
- `user_access_logs`
- `users`

현재 baseline migration은 `user_access_logs`만 생성한다. 반면 `DEBUG=False`에서는 시작 시 `create_all`을 실행하지 않고 Alembic 사용을 전제로 한다.

#### 영향

- 빈 운영 DB에 `alembic upgrade head`를 실행해도 Blog, Reply, SNS, User 기능의 테이블이 없다.
- 애플리케이션 시작은 성공하더라도 해당 CRUD 요청이 런타임 DB 오류로 실패할 수 있다.
- 기존 `test_alembic_metadata.py`는 `user_access_logs` 존재만 확인하므로 이 회귀를 차단하지 못한다.

#### 목표 상태

- 빈 DB에서 migration head 적용 후 모든 등록 모델의 테이블과 핵심 제약조건·인덱스가 존재한다.
- metadata와 migration 결과의 차이를 CI가 탐지한다.
- 개발용 `create_all`과 운영용 Alembic의 결과가 기능적으로 동등하다.

### P0-3. 접근 로그 조회 API 인증·인가 부재

#### 현재 상태

`app/features/home/api/routers/v1/home.py`는 다음 정보를 조회할 수 있는 API를 제공한다.

- 전체·최근 접근 로그
- IP 기준 접근 로그
- 사용자 기준 접근 로그
- 접근 통계

각 endpoint는 `UserAccessLogService`만 주입받으며 인증 또는 관리자 권한 Dependency가 없다. 응답에는 IP 주소, 사용자 ID, 요청 경로, 접속 시각, 브라우저·장치 정보 등이 포함된다.

#### 영향

- 외부 사용자가 트래픽 패턴과 사용자 활동을 조회할 수 있다.
- IP와 사용자 ID의 결합은 개인정보 및 보안 감사 데이터에 해당할 가능성이 높다.
- SQLAdmin 문제와 결합하면 접근 로그의 조회·내보내기·삭제 경계가 모두 약해진다.

#### 목표 상태

- 접근 로그 조회는 인증된 관리자 또는 명시된 운영 역할만 가능하다.
- 일반 API 토큰과 관리자 권한을 구분한다.
- 권한 실패는 일관된 `401` 또는 `403` 응답으로 처리한다.
- 보안 endpoint가 OpenAPI 문서에 인증 요구 사항을 표시한다.

### P1-1. AppRegistry의 과도한 `ModuleNotFoundError` 무시

#### 현재 상태

`AppModule.load_router()`, `load_admin_views()`, `import_models()`는 대상 모듈 import 중 발생한 모든 `ModuleNotFoundError`를 무시한다.

#### 영향

- 선택적 `router`, `admin`, `models` 모듈이 실제로 없는 경우와, 해당 모듈 내부 의존성 import가 실패한 경우를 구분하지 못한다.
- 패키지 누락이나 잘못된 import가 있어도 앱의 일부가 조용히 비활성화된다.
- 시작 실패 대신 endpoint 또는 모델 누락으로 나타나 원인 추적이 어려워진다.

#### 목표 상태

- 실제 선택 모듈이 없을 때만 빈 결과를 반환한다.
- 모듈 내부 import 실패는 원래 traceback과 함께 다시 발생시킨다.
- 등록 앱 패키지 자체가 없으면 어떤 앱 등록값이 잘못됐는지 명확한 오류를 제공한다.

### P1-2. 접근 로그의 신뢰 경계와 개인정보 처리 미정의

#### 현재 상태

- 클라이언트가 보낸 `X-Forwarded-For`, `X-Real-IP`를 신뢰 프록시 확인 없이 사용한다.
- 원본 query string, Referer, session ID, user ID, IP 및 User-Agent 파생 정보를 저장한다.
- 민감 query parameter 마스킹, 데이터 보존 기간, 자동 삭제 정책이 없다.

#### 영향

- 공격자가 헤더를 조작해 감사 로그의 IP를 위조할 수 있다.
- URL query에 토큰, 이메일, 검색어 등이 포함되면 원문으로 저장될 수 있다.
- 세션 식별자 저장은 세션 탈취 피해를 확대할 수 있다.
- 데이터 보존 기간이 없으면 개인정보와 저장 공간이 계속 누적된다.

#### 목표 상태

- 직접 연결 주소와 신뢰 프록시 체인을 구분한다.
- 신뢰할 프록시 또는 프록시 hop 수를 설정으로 제한한다.
- 민감 query key, cookie, 인증 헤더는 저장 전에 제거하거나 마스킹한다.
- session ID 원문은 저장하지 않고 필요하면 비가역 해시를 사용한다.
- 보존 기간과 배치 삭제 정책을 설정·문서화한다.

### P1-3. 신규 앱 생성기와 passive-style 정책 불일치

#### 현재 상태

`scripts/new_app.py` 내부 설명 일부는 `config.INSTALLED_APPS` 등록 필요성을 안내하지만, 실행 완료 메시지는 자동 발견되며 중앙 파일 수정이 불필요하다고 출력한다.

#### 영향

- 생성된 앱이 서버에 결선되지 않아도 사용자는 정상 생성된 것으로 오인한다.
- passive-style 저장소와 active-style 저장소의 핵심 차이가 흐려진다.
- 신규 기여자가 첫 앱 생성 단계에서 불필요한 디버깅을 하게 된다.

#### 목표 상태

- 생성 완료 메시지와 docstring이 수동 등록 정책으로 통일된다.
- 생성기가 `INSTALLED_APPS`를 수정하지 않는다면 복사 가능한 설정 예제를 출력한다.
- 선택적으로 `--register`를 제공할 경우 AST 또는 구조화된 방식으로 중복 없이 등록한다.

### P2-1. 설정 검증 부족

#### 현재 상태

`CORS_ALLOW_ORIGINS=["*"]`와 `CORS_ALLOW_CREDENTIALS=True`가 유효하지 않은 조합이라는 주석은 있으나 설정 생성 단계에서 차단하지 않는다.

#### 영향

- 환경 변수 오설정이 시작 시 발견되지 않고 브라우저 요청 실패 또는 잘못된 CORS 정책으로 나타난다.

#### 목표 상태

- Pydantic `model_validator`로 잘못된 조합을 시작 단계에서 거부한다.
- production 환경의 wildcard Origin 사용 여부도 명시적으로 결정한다.

### P2-2. 백그라운드 로그 drain 타임아웃 처리 불완전

#### 현재 상태

`BackgroundTaskRunner.drain()`은 타임아웃 후 미완료 task를 경고하지만 취소하거나 완료를 기다리지 않는다. 이후 lifespan은 DB engine을 dispose한다.

#### 영향

- 느린 로그 task가 dispose된 engine과 경쟁할 수 있다.
- 종료 시 경고 외에 task 수명주기와 로그 유실 여부가 명확하지 않다.

#### 목표 상태

- 타임아웃 정책을 `cancel-and-gather` 또는 제한된 추가 대기 중 하나로 명확히 정한다.
- 취소된 task의 예외를 회수해 asyncio 경고를 방지한다.
- 종료 시 유실 허용 범위와 관측 지표를 정의한다.

### P2-3. 테스트 및 품질 게이트의 사각지대

#### 현재 상태

- Ruff, MyPy, Bandit은 통과했다.
- 전체 테스트 146건은 기능적으로 통과했다.
- `pyproject.toml`의 coverage branch 측정은 활성화되어 있지만 `fail_under`는 주석 처리되어 있다.
- 현재 Alembic 테스트는 전체 테이블 동등성을 검사하지 않는다.
- 인증이 아직 없으므로 Admin과 접근 로그 endpoint의 보안 회귀 테스트도 없다.

#### 영향

- 테스트 개수는 많지만 운영 차단 문제를 CI가 발견하지 못한다.
- coverage가 크게 하락해도 빌드가 성공할 수 있다.

#### 목표 상태

- 중요한 보안·migration 불변 조건을 별도 테스트로 고정한다.
- coverage 데이터 생성 방식을 하나로 통일하고 현실적인 최소 기준을 CI에서 강제한다.

## 4. 구현 원칙

1. **안전한 기본값**: 환경 설정이 누락되더라도 관리 기능과 민감 API가 공개되지 않아야 한다.
2. **시작 시 실패**: 잘못된 보안·DB·CORS 설정은 런타임 요청보다 애플리케이션 시작 단계에서 발견한다.
3. **수동 등록 SSOT 유지**: 앱 목록은 계속 `config.INSTALLED_APPS`만 사용한다. 디렉터리 자동 스캔은 도입하지 않는다.
4. **컨벤션 결선 유지**: 등록된 앱의 Router, Model, Admin 결선은 Registry가 담당한다.
5. **트랜잭션 경계 유지**: Service나 Repository에 임의 커밋을 추가하지 않고 기능 Dependency의 경계를 유지한다.
6. **작은 변경과 독립 검증**: 보안, migration, Registry, 도구 개선을 분리해 검토와 rollback이 가능하게 한다.

## 5. 단계별 개발 계획

### Phase 0. 안전 기준과 회귀 테스트 준비

#### 작업

- 현재 endpoint, Admin View, metadata table 목록을 테스트 fixture로 고정한다.
- 운영 보안 요구 사항을 테스트 이름과 acceptance criteria로 먼저 정의한다.
- coverage 실행 시 기존 데이터와 섞이지 않도록 CI에서 clean coverage file을 사용한다.

#### 대상 파일

- `tests/core/test_admin_views.py`
- `tests/core/test_alembic_metadata.py`
- `tests/core/` 신규 보안·설정 테스트
- `pyproject.toml`
- `.github/workflows/ci.yml`

#### 완료 조건

- 이후 Phase의 실패 조건을 보여주는 테스트가 추가되어 있다.
- 테스트가 단순 구현 세부사항이 아니라 외부 보안·스키마 계약을 검증한다.

### Phase 1. Admin 및 접근 로그 보안 경계 구축

#### 작업 1: 안전한 Admin 기본값

- `ADMIN` 기본값을 `False`로 변경한다.
- production에서 Admin 활성화 시 필수 인증 설정을 검증한다.
- SQLAdmin 인증 백엔드를 `app/utils/authenticator/` 또는 명확한 core security 모듈에 구현한다.
- 세션 secret, cookie secure, SameSite, HTTPS 요구 사항을 설정으로 정의한다.
- Admin View별 생성·수정·삭제·내보내기 권한을 재검토한다.

#### 작업 2: 공통 관리자 권한 Dependency

- API 인증 주체와 역할을 표현하는 공통 타입을 정의한다.
- `require_admin`과 같은 Dependency를 추가한다.
- 접근 로그의 모든 조회 endpoint에 인증·인가를 적용한다.
- 미인증은 `401`, 권한 부족은 `403`으로 검증한다.

#### 작업 3: 보안 테스트

- Admin 비활성 기본값 테스트
- 인증 없는 `/admin` 접근 차단 테스트
- 정상 관리자 로그인·로그아웃·세션 만료 테스트
- 접근 로그 endpoint의 anonymous/user/admin 역할별 테스트
- production 설정 누락 시 시작 실패 테스트

#### 대상 파일

- `config.py`
- `app/core/bootstrap.py`
- `app/utils/authenticator/`
- `app/features/home/api/routers/v1/home.py`
- `app/features/*/admin.py`
- 관련 `tests/`

#### 완료 조건

- 기본 설정에서 `/admin`은 노출되지 않는다.
- Admin 활성화는 유효한 인증 설정 없이는 불가능하다.
- 접근 로그 API는 관리자 이외의 요청을 거부한다.
- 인증 관련 모든 테스트와 Bandit 검사가 통과한다.

### Phase 2. Alembic 스키마 완전성 확보

#### 작업

- Registry로 모든 등록 앱 모델을 import한 상태에서 Alembic revision을 생성한다.
- `users`, `blog_posts`, `replies`, `sns_posts` 테이블과 제약조건·인덱스를 migration에 반영한다.
- 기존 배포 DB가 있을 가능성을 고려해 baseline 수정과 신규 revision 중 전략을 결정한다.
  - 이미 배포된 migration ID라면 기존 파일을 변경하지 않고 신규 revision을 추가한다.
  - 아직 외부 배포가 전혀 없는 템플릿이라면 baseline 재생성도 가능하지만 명시적으로 기록한다.
- 빈 DB upgrade, downgrade, 재-upgrade를 자동 검증한다.
- migration 결과를 SQLAlchemy inspector로 읽어 metadata의 테이블·컬럼·핵심 제약조건과 비교한다.
- `alembic check` 또는 autogenerate diff가 비어 있는지 CI에서 확인한다.

#### 대상 파일

- `migrations/versions/`
- `migrations/env.py`
- `tests/core/test_alembic_metadata.py`
- 신규 migration 통합 테스트
- `.github/workflows/ci.yml`

#### 완료 조건

- 빈 DB에 `alembic upgrade head` 후 등록 모델 5개의 테이블이 모두 존재한다.
- migration head와 `Base.metadata` 사이에 예상하지 않은 diff가 없다.
- `DEBUG=False` 상태에서 전체 CRUD smoke test가 통과한다.

### Phase 3. Registry 오류 처리 강화

#### 작업

- 각 선택 모듈의 전체 이름을 먼저 계산한다.
- `ModuleNotFoundError.name`이 선택 모듈 자체 또는 없는 상위 선택 패키지와 일치할 때만 선택 기능 부재로 처리한다.
- 내부 의존성 import 실패는 다시 발생시킨다.
- 잘못된 `INSTALLED_APPS` 항목은 앱 이름과 예상 package를 포함한 명시적 오류로 변환한다.
- 등록 순서와 중복 앱 처리 정책을 정의하고 검증한다.

#### 테스트 사례

- router 모듈이 실제로 없으면 앱은 정상 로드된다.
- router 모듈 내부에서 존재하지 않는 패키지를 import하면 시작이 실패한다.
- models와 admin에도 동일한 동작이 적용된다.
- 잘못된 앱 이름은 조용히 무시되지 않는다.

#### 대상 파일

- `app/core/registry.py`
- `tests/core/test_registry.py` 또는 대응 Registry 테스트

#### 완료 조건

- 선택 컴포넌트 부재와 구현 오류가 명확히 구분된다.
- 기존 passive 등록 순서와 컨벤션 결선 동작은 유지된다.

### Phase 4. 접근 로그 개인정보·신뢰 프록시 정책 구현

#### 작업

- 신뢰 프록시 CIDR 또는 신뢰 hop 수 설정을 추가한다.
- 신뢰되지 않은 직접 요청의 전달 헤더는 클라이언트 IP 결정에 사용하지 않는다.
- IP 문자열을 표준 라이브러리로 검증·정규화한다.
- query parameter redaction 목록을 설정한다.
- `token`, `access_token`, `api_key`, `password`, `secret`, `code` 등 기본 민감 키를 마스킹한다.
- session ID 원문 저장을 제거하거나 keyed hash로 대체한다.
- 접근 로그 보존 일수와 삭제 작업을 구현한다.
- 저장 실패, 삭제량, drain timeout을 관측 가능한 로그 또는 metric으로 남긴다.

#### 대상 파일

- `config.py`
- `app/core/middlewares/user_info_middleware.py`
- `app/features/home/models/models.py`
- `app/features/home/repositories/`
- `app/features/home/services/`
- Celery task 또는 별도 maintenance task
- 관련 테스트와 문서

#### 완료 조건

- 신뢰 프록시를 통과하지 않은 XFF 위조 테스트가 실패하지 않고 실제 peer 주소를 사용한다.
- 민감 query와 session ID 원문이 DB에 저장되지 않는다.
- 설정된 보존 기간보다 오래된 로그를 반복 실행 가능하게 삭제한다.

### Phase 5. 신규 앱 생성 경험 정합성 개선

#### 기본안

생성기가 설정 파일을 자동 수정하지 않고, 다음 수동 단계를 정확히 출력한다.

```python
INSTALLED_APPS = [
    # ...
    "new_app",
]
```

#### 선택 확장안

`--register` 옵션을 제공해 다음 조건에서만 자동 등록한다.

- 기존 항목과 중복되지 않는다.
- 기존 순서를 보존한다.
- Python 소스가 예상 구조가 아니면 파일을 변경하지 않고 명시적으로 실패한다.
- `--dry-run`으로 변경 예정 내용을 확인할 수 있다.

#### 작업

- 자동 발견을 주장하는 module docstring, dependency 설명, 완료 메시지를 제거한다.
- passive-style과 active-style 용어를 README 및 Architecture 문서와 통일한다.
- 생성 후 Registry에서 실제로 발견되는지 통합 테스트를 추가한다.

#### 대상 파일

- `scripts/new_app.py`
- `tests/scripts/` 또는 기존 generator 테스트
- `README.md`
- `docs/ARCHITECTURE.md`

#### 완료 조건

- 안내대로 실행한 신규 앱이 `INSTALLED_APPS`를 통해 결선된다.
- “중앙 파일 수정 불필요”와 같은 잘못된 문구가 남지 않는다.

### Phase 6. 설정 및 종료 수명주기 보강

#### 작업 1: CORS 검증

- `CORSSettings`에 validator를 추가한다.
- credentials가 활성화된 경우 wildcard Origin을 거부한다.
- production wildcard 정책을 명시적으로 설정한다.

#### 작업 2: background drain

- 타임아웃된 task를 취소한다.
- `asyncio.gather(..., return_exceptions=True)`로 취소와 예외를 회수한다.
- 모든 task 정리 후 DB engine을 dispose한다.
- 정상 완료, timeout, task 예외, 빈 task 집합 테스트를 추가한다.

#### 대상 파일

- `config.py`
- `app/core/middlewares/cors_middleware.py`
- `app/core/middlewares/background_tasks.py`
- `app/core/bootstrap.py`
- 관련 `tests/core/`

#### 완료 조건

- 잘못된 CORS 조합은 설정 로드 시 즉시 실패한다.
- drain 반환 시 runner가 추적하는 미완료 task가 없다.
- engine dispose 이후 로그 task가 DB를 사용하지 않는다.

### Phase 7. CI와 문서 완료

#### 작업

- coverage 파일을 실행 전 정리하고 branch coverage 형식을 일관되게 사용한다.
- 현재 수치를 기준으로 달성 가능한 `fail_under`를 정한 뒤 단계적으로 상향한다.
- CI 순서를 `Ruff → format → MyPy → Bandit → unit/integration → migration check`로 명확히 한다.
- production 배포 체크리스트를 문서화한다.
- Admin 인증, migration, 접근 로그 개인정보, 신뢰 프록시 설정 예시를 README 또는 별도 운영 문서에 반영한다.
- Registry와 bootstrap에 남아 있는 “자동 발견” 표현을 “수동 등록 목록의 컨벤션 결선”으로 정정한다.

#### 완료 조건

- 로컬과 CI에서 동일한 검사 명령이 성공한다.
- coverage 하락과 migration diff가 CI 실패로 연결된다.
- 운영자가 문서만으로 필수 보안 설정과 migration 절차를 수행할 수 있다.

## 6. 권장 작업 순서와 의존 관계

```text
Phase 0: 회귀 테스트 기반
   ├─ Phase 1: Admin/API 인증 ───────────┐
   ├─ Phase 2: Alembic 완전성 ──────────┤
   └─ Phase 3: Registry 오류 처리 ──────┤
                                         ├─ Phase 7: CI·문서·최종 검증
Phase 4: 로그 개인정보·프록시 ──────────┤
Phase 5: 생성기 정합성 ─────────────────┤
Phase 6: CORS·종료 수명주기 ────────────┘
```

- Phase 1과 Phase 2는 배포 차단 항목이므로 가장 먼저 완료한다.
- Phase 3은 migration 및 앱 로딩 실패를 정확히 드러내므로 Phase 2와 가까운 시점에 수행한다.
- Phase 4는 접근 로그 API 인증이 완료된 뒤 데이터 최소화 정책까지 확장한다.
- Phase 5와 Phase 6은 서로 독립적으로 진행할 수 있다.

## 7. 권장 커밋 단위

1. `test: add production security and migration contract tests`
2. `security: disable unauthenticated admin by default`
3. `security: protect access log APIs with admin authorization`
4. `migration: add missing feature tables and schema parity tests`
5. `fix: distinguish optional modules from registry import failures`
6. `security: harden proxy and access log data handling`
7. `fix: align new app generator with passive registration`
8. `fix: validate cors settings and drain timed-out tasks`
9. `ci: enforce migration checks and coverage threshold`
10. `docs: document secure deployment and passive app registration`

각 커밋은 해당 범위의 테스트를 함께 포함하며, migration과 보안 변경을 하나의 대형 커밋으로 합치지 않는다.

## 8. 검증 계획

### 정적 검사

```powershell
uv run ruff check
uv run ruff format --check
uv run mypy .
uv run bandit -r app config.py main.py -x '*/tests/*' -q
```

### 단위 및 통합 테스트

```powershell
uv run pytest
```

필수 추가 검증 범위:

- Admin 비활성 기본값과 인증 성공·실패
- 접근 로그 endpoint 역할별 `200/401/403`
- Registry 선택 모듈 부재와 내부 import 실패 구분
- CORS 잘못된 조합의 설정 실패
- 신뢰되지 않은 프록시 헤더 무시
- 민감 query 및 session ID 마스킹
- drain 정상·timeout·예외 처리

### Migration 검증

1. 임시 빈 DB 생성
2. `alembic upgrade head`
3. SQLAlchemy inspector로 테이블·컬럼·제약조건 비교
4. `alembic downgrade base`
5. 다시 `alembic upgrade head`
6. `DEBUG=False` 애플리케이션 CRUD smoke test
7. autogenerate diff가 비어 있는지 확인

### 최종 운영 준비 승인 조건

다음 조건을 모두 만족해야 운영 준비 완료로 판정한다.

- [ ] 인증 없는 사용자가 SQLAdmin을 열거나 변경 작업을 수행할 수 없다.
- [ ] 접근 로그 API는 관리자 권한 없이는 조회할 수 없다.
- [ ] 빈 DB migration 후 모든 등록 앱 테이블이 존재한다.
- [ ] Registry가 내부 import 오류를 숨기지 않는다.
- [ ] 접근 로그에 민감 query와 session ID 원문이 저장되지 않는다.
- [ ] 신뢰되지 않은 전달 헤더로 감사 IP를 위조할 수 없다.
- [ ] 신규 앱 생성 안내와 `INSTALLED_APPS` 등록 절차가 일치한다.
- [ ] 잘못된 CORS 설정이 시작 시 거부된다.
- [ ] 종료 후 추적되지 않은 background task가 남지 않는다.
- [ ] Ruff, format, MyPy, Bandit, 전체 테스트, migration check, coverage gate가 CI에서 통과한다.

## 9. 범위 밖 항목

다음은 이번 운영 준비 작업과 분리한다.

- 디렉터리 스캔 기반 active-style 등록으로 변경
- UnitOfWork 패턴 도입
- 기능 간 FK 및 relationship 재설계
- 전체 인증 제품 기능(회원가입, 비밀번호 복구, OAuth 공급자 연동)
- 모니터링 플랫폼 또는 특정 클라우드 공급자 도입

단, Admin과 접근 로그를 보호하는 최소 인증·인가 기반은 이번 범위에 포함한다.

## 10. 예상 결과

계획 완료 후 프로젝트는 다음 특성을 갖는다.

- Django식 수동 앱 등록의 명시성, 순서 제어 및 탈착성을 유지한다.
- 앱 내부 컴포넌트는 기존 컨벤션으로 자동 결선된다.
- 운영 배포 시 인증, migration, 개인정보 및 설정 오류가 안전하게 통제된다.
- 구조적 규칙과 운영 불변 조건이 CI 테스트로 고정된다.
- 신규 기능 앱을 추가할 때 따라야 할 절차가 코드·도구·문서에서 일치한다.
