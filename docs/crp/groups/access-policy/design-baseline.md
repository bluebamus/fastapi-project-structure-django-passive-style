# Design Baseline — access-policy (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다. 이 그룹의 ID(REQ·ADR·C·F·R)는 그룹 안에서만 유효하다. 다른 그룹의 ID 는
> `service-hardening ADR-017` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] 적극(Thorough)
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] 간략(Lean)

선택: **보통** · 선택일: 2026-10-13 · 변경 이력: (없음)

> 핵심 갈림길(데코레이터의 의미, 기본 정책, 예시 정책 유지)은 감독자가 사용자에게 설명하고 정했다 — REQ-001 해석 참고.

## 1. 목적 / 배경

예시 뷰들의 인증 적용 범위와 기본 정책을 정한다. 지금까지는 core provider 를 경로마다 다는 방식이라 **기본값이 공개**였고,
선언을 잊은 새 라우트는 회귀 표 테스트(`test_policy_table_covers_every_operation`)가 있어야만 잡혔다
(log-redaction-fixes run-log Round 1 의 조사). 스캐폴드가 만드는 `GET /ping` 도 아무 선언이 없었다.

## 2. 요구사항

| ID | 날짜 | 원문 | 해석 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "현재 프로젝트의 view들은 예시들이다. 때문에 적절하게 판단하여 인증 적용 범위와 기본 정책을 설정해줘. 이는 데코레이터로 충분히 적용할 수 있는 것으로 알고 있다. 뷰 단위 설정으로 고려해줘." | ① 뷰마다 경로 데코레이터의 `dependencies=[...]` 에 접근 수준을 선언한다(함수를 감싸는 데코레이터는 만들지 않는다). ② 선언 없는 뷰가 있으면 기동을 거부한다(기본 거부). ③ 예시 정책은 현재 동작을 유지한다. ④ 라우터 단위 선언은 뷰 단위로 옮긴다. ⑤ 스캐폴드도 선언한다 | Active |

## 3. 설계 결정 (ADR)

### ADR-001 접근 수준은 `Depends` 객체 4개로 공개한다
- `Public`·`PublicWrite` 는 아무것도 하지 않는 `async` 표식 의존성(각각 고유 함수), `LoginRequired = Depends(get_current_principal)`,
  `SuperuserRequired = Depends(require_superuser)`. 위치는 `app/core/security/access.py`.
- 인자 `CurrentPrincipal`·`SuperuserPrincipal` 은 같은 의존성 함수이므로 별도 장치 없이 선언으로 인정된다.
- **함수를 감싸는 데코레이터를 쓰지 않는다.** FastAPI 는 시그니처로 주입·검증·OpenAPI 를 만든다 — 감싸면 깨진다.
- 표식이 `async def` 인 이유: 동기 함수는 스레드 풀로 돌아 요청마다 비용이 생긴다.

### ADR-002 기본 거부는 `create_app()` 의 마지막 단계에서 검사한다
- `AccessPolicyGuard().verify(app)` 가 서빙되는 모든 `APIRoute` 의 의존성 트리를 재귀로 훑는다. FastAPI 0.141 의 `_IncludedRouter`
  는 `effective_route_contexts()` 로 펼친다(라우터 단위 `dependencies`·prefix 가 합쳐진 모습).
- 위반: 선언 없음 · 서로 다른 수준 둘 이상 · 쓰기 메서드에 `Public` · 안전한 메서드에만 걸린 `PublicWrite`. 위반 전체를 한 번에
  `ImproperlyConfigured`(저장소의 설정 오류 예외, `app/core/apps/exceptions.py`)로 보고한다.
- 대상에서 빼는 것: Starlette `Route`(FastAPI 기본 문서 경로·`/openapi.json`)와 `Mount`(`/admin` — 자체 세션 인증, admin-login ADR-001).
  앱이 직접 등록한 Scalar `/docs` 는 `APIRoute` 이므로 `Public` 을 선언한다. `include_in_schema=False` 도 대상이다.
- 위치: 라우터·health·docs·admin 설치가 모두 끝난 뒤(조립 순서 8단계). 그래야 빠짐없이 본다.
- `require_superuser` 는 내부에 `get_current_principal` 을 품으므로 슈퍼유저가 있으면 로그인을 지우고 슈퍼유저 하나로 본다.

### ADR-003 정본은 뷰 선언, 테스트 표는 예시 정책 회귀용 하나
- `test_policy_table_covers_every_operation`(표 ↔ OpenAPI 집합)은 기동 검사와 중복이라 없앴다. 대신
  `test_example_views_declare_the_intended_access_level` 이 같은 표와 **가드의 판정 함수**(`levels`)를 대조한다. 표는 한 벌이다.
- OpenAPI `security` 교차 확인과 401/403 실요청 테스트는 그대로 둔다.

### ADR-004 예시는 뷰 단위로 통일한다
- home·reports 의 `APIRouter(dependencies=[Depends(require_superuser)])` 와 catalog·user 의 `_ADMIN_ONLY` 를 뷰마다
  `dependencies=[SuperuserRequired]` 로 옮겼다. 라우터 단위 401/403 `responses` 문서는 라우터에 남긴다(문서만, 판정과 무관).
- 사용자 정보가 필요한 뷰(blog·sns·reply 쓰기, user 단건 GET·PATCH, auth `/me`)는 인자로 받은 것이 선언이다 — 데코레이터에 중복으로 적지 않는다.

## 4. 불가침 제약

- C-1: 응답 코드·OpenAPI `security` 표시는 바뀌지 않는다(기존 401/403·골든·계약 테스트 통과).
- C-2: 선언 없는 API 라우트가 있는 앱은 `create_app()` 이 만들어지지 않는다.
- C-3: 감싸는 데코레이터를 만들지 않는다.
- C-4: 마이그레이션 변경 없음.
