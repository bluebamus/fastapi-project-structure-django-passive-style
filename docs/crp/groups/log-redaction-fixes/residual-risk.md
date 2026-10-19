# Residual Risk — log-redaction-fixes (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은 "새 결함"이
> 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 접속 로그 DB 행에 `session_id` 쿠키·Referer·`X-Forwarded-For`·`X-Real-IP` 가 원문 그대로 저장된다(`app/core/middlewares/user_info_middleware.py`) | LOW | **결정으로 수용** — 사용자 결정(ADR-002, REQ-001 원문 "그대로 유지해줘"). service-hardening R-007 의 `forwarded_for`·`real_ip` 원문 서술과 같은 축이다 | 2026-10-13 | 사용자가 저장 필드 축소·해시·보존 기간을 요청하면 — **(2026-10-19)** 보존 기간은 생겼다: `ACCESS_LOG_RETENTION_DAYS`(기본 365일) 매일 삭제(security-ops-hardening ADR-002). 원문 저장 결정은 그대로 |
| R-002 | 가리기는 형식 기반이다 — 키 이름(`password=` 등)·URL userinfo·Bearer·JWT 형태가 없는 자유 텍스트 비밀값(예: "비밀번호는 abc")이나 `repr()` 된 객체 안의 다른 이름 필드는 가려지지 않는다 | LOW | ADR-001 — 값만 보고 비밀인지 판정할 수 없다. 비밀을 다루는 코드는 애초에 로그에 싣지 않는다(service-hardening C-12·admin-login C-5) | 2026-10-13 | 새 비밀 형식(다른 토큰 형식 등)이 도입되면 규칙에 더한다 |
| R-003 | `configure_logging()` 이 불리기 전에 만들어진 레코드(uvicorn CLI 의 `Started server process` 같은 앱 import 이전 줄)와, `record.exc_info` 를 직접 읽어 자기 방식으로 포맷하는 외부 핸들러(예: 에러 수집 SDK)는 가리기를 거치지 않는다 | LOW | ADR-001 — factory 는 레코드 생성 시점에 걸리고, 포매터는 `exc_text` 가 있으면 그것을 쓴다(표준 `logging.Formatter` 계약). 앱 import 이전 줄에는 앱 비밀값이 없다. 외부 SDK 는 현재 쓰지 않는다 | 2026-10-13 | 에러 수집 SDK 를 들이면 그 SDK 의 before-send 훅에 `redactor.redact` 를 건다 |
| R-004 | `INFO` 를 막아 둔 관리형 Redis(명령 이름 변경·ACL)는 버전을 확인하지 못하고 WARNING 만 남기고 기동한다 — 7.0 미만이면 레이트 리밋 첫 요청이 500 이 된다 | LOW | ADR-004 — 기동 실패로 만들면 정상인 관리형 배포를 막는다. README·ARCHITECTURE §11.1 #6 에 "직접 확인" 을 배포자 확인 항목으로 적었다 | 2026-10-13 | 관리형 Redis 에서 버전을 알 다른 수단(HELLO 응답 등)을 쓰기로 하면 |
| R-005 | traceback 의 소스 줄이 `token = …`·`password = …` 꼴이면 그 줄의 오른쪽도 `***` 로 바뀐다 — 진단 정보가 조금 줄어든다(파일·줄 번호·함수 이름은 남는다) | LOW | ADR-001 — 소스 줄과 예외 메시지를 구분해 가리면 규칙이 둘이 된다. 파일·줄로 원문을 볼 수 있다 | 2026-10-13 | 진단에 실제로 방해가 된 사례가 나오면 |
| R-006 | 커버리지 하한이 0 이라 커버리지가 떨어져도 게이트·CI 가 막지 않는다(측정·출력은 한다) | LOW | **결정으로 수용** — 사용자 결정(ADR-005, REQ-002) | 2026-10-13 | 사용자가 하한을 정하면 `fail_under` 한 곳만 올린다 |

## 최종 상태 (2026-10-13, Round 2 · 그룹 CONVERGED)

수용 항목은 R-001~R-006 이고, R-001·R-006 은 사용자 결정, 나머지는 형식 기반 가리기와 관리형 Redis 에 근거한 의도적 수용이다.
