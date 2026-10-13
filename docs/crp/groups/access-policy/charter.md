# Charter — access-policy  (Charter v0.1 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 REQ-001·C-1~C-4 와 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 접근 수준·가드 | `app/core/security/access.py` (신규) | 소스 | `Public`·`PublicWrite`·`LoginRequired`·`SuperuserRequired`·`AccessLevel`·`AccessPolicyGuard` |
| 조립 | `app/core/bootstrap.py` | 소스 | health·ready·docs 에 `Public`, 마지막 단계 `verify(app)` |
| 예시 뷰 | `app/features/{auth,blog,sns,reply,catalog,user,home,reports}/api/routers/v1/*.py` | 소스 | 뷰 단위 선언 |
| 스캐폴드 | `scripts/new_app.py` | 소스 | `/ping` 에 `Public` + 템플릿 주석 |
| docstring | `app/core/security/dependencies.py` | 소스 | 선언 예시 갱신 |
| 테스트 | `tests/core/security/test_access_policy.py`(신규), `tests/test_authorization_policy.py`, `tests/scripts/test_new_app.py` | 테스트 | 가드 단위·앱 단위·회귀 |
| 문서 | `README.md`, `docs/guides/{ARCHITECTURE,DEVELOPMENT}.md`, `docs/guides/{admin-auth-guide,feature-development-guide}.html` | 문서 | 권한 절·체크리스트·감싸는 데코레이터를 쓰지 않는 이유 |

- 착수 기준선 커밋: `e78f7cb` (main)
- 마이그레이션: 변경 없음

## 2. 계약

### 2-1. 위협 모델
- 방어한다: 접근 수준을 선언하지 않은 새 API 라우트가 공개로 배포되는 것, 쓰기 엔드포인트가 실수로 `Public` 으로 열리는 것, 서로 모순된 선언.
- 방어하지 않는다: 선언은 맞지만 정책이 틀린 경우(예: 슈퍼유저여야 할 뷰에 `LoginRequired`) — 사람이 고른 수준이 옳은지는 리뷰와 예시 회귀 표의 몫이다(R-001).
  WebSocket 라우트(현재 없음, R-002). `/admin` 마운트(자체 세션 인증).

### 2-2. 불변식
- INV-1: `create_app()` 이 만든 앱에서 `AccessPolicyGuard().violations(app) == []` 이고, 위반이 있으면 `create_app()` 이 `ImproperlyConfigured` 로 실패한다.
- INV-2: 판정은 의존성 트리 전체(라우터 단위·인자·중첩 include)를 본다.
- INV-3: 예시 정책(README 권한 표)과 응답 코드·OpenAPI `security` 는 이전과 같다.

### 2-3. 비목표
- 역할(role)·권한(permission) 세분화, 감싸는 데코레이터, 전역 인증 미들웨어.

## 3. 합격 기준
- 가드 단위 테스트(선언 없음·이중·쓰기+Public·안전+PublicWrite·인자·라우터 단위·숨김 경로·문서/Mount 제외·중첩·전체 보고) 통과 + fail-on-revert.
- 앱 단위: 실제 앱 통과, 조립 경로에서 가드가 실제로 불림(선언 없는 라우트로 `create_app()` 실패).
- 기존 401/403·OpenAPI 계약·라우트 골든 테스트 통과. ruff·mypy·인프라 제외 pytest(`.env` 없는 사본) 통과.
