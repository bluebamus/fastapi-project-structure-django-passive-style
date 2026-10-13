# Residual Risk — access-policy (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 가드는 "선언했는가" 만 본다 — 슈퍼유저여야 할 뷰에 `LoginRequired` 를 적는 식의 **정책 오판**은 막지 못한다 | LOW | charter 2-1 — 어떤 수준이 옳은지는 사람의 판단이다. 예시 정책은 `tests/test_authorization_policy.py` 회귀 표가 고정하고, 새 기능은 리뷰가 본다 | 2026-10-13 | 역할·권한 모델을 도입하면 |
| R-002 | WebSocket 라우트(`APIWebSocketRoute`)는 검사 대상이 아니다 | LOW | 현재 WebSocket 라우트가 없다. charter 2-1 | 2026-10-13 | 첫 WebSocket 라우트를 추가할 때 가드 대상에 넣는다 |
| R-003 | 판정은 의존성 함수의 **동일성**으로 한다 — 같은 일을 하는 다른 함수(예: 기능이 만든 자체 인증 의존성)는 선언으로 인정되지 않는다 | LOW | ADR-001 — 인증 경로는 core 하나다(service-hardening C-11). 자체 의존성은 안에서 `get_current_principal` 을 쓰면 트리로 인정된다(auth `get_current_user` 가 그 예) | 2026-10-13 | 별도 인증 체계를 들이면 |
| R-004 | 가드는 `create_app()` 경로에만 있다 — `FastAPI()` 를 직접 만들어 라우터를 붙이는 테스트용 앱은 검사하지 않는다 | LOW | ADR-002 — 서빙되는 앱의 조립 지점은 하나다(`main.py` → `create_app()`) | 2026-10-13 | 다른 진입점이 생기면 그 조립부에서도 `verify` 를 부른다 |

## 최종 상태 (2026-10-13, Round 1 · 그룹 CONVERGED)

수용 항목은 R-001~R-004 — 모두 가드의 의도된 경계다.
