# Residual Risk — config-cleanup (잔여 위험 등록부)

> **재기 금지 목록.** 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 은 여전히 읽는 곳이 없다(계약 테스트 `UNREAD_ALLOWED`) | LOW | 사용자 결정(REQ-001)은 SMTP·UPLOAD·SESSION_EXPIRE 세 묶음만 지운다. 문서(ARCHITECTURE §3.2·§11.3)가 이미 미사용이라 밝힌다 | 2026-10-19 | 사용자가 삭제·구현을 정하면 — 목록에서 빼면 계약 테스트가 나머지를 강제한다 |
| R-002 | 지운 키가 운영 `.env` 에 남아 있어도 알리지 않는다(조용히 무시) | LOW | ADR-001 — 효과 없는 값이라 보안 위험이 아니다. README 업그레이드 노트로 안내한다 | 2026-10-19 | 지운 키가 다른 뜻으로 다시 쓰이게 되면 `REMOVED_SETTINGS` 로 감지한다 |
| R-003 | 계약 테스트는 속성 이름만 본다 — 다른 클래스의 같은 이름 속성 접근도 "읽힘" 으로 센다 | LOW | ADR-002 — 설정 필드 이름은 대문자 고유 이름이라 충돌 위험이 낮다 | 2026-10-19 | 오탐으로 미사용 필드가 통과한 사례가 나오면 `xxx_settings.FIELD` 수신자까지 본다 |

## 최종 상태 (2026-10-19, Round 1 · 그룹 CONVERGED)

수용 항목은 R-001~R-003 이다.
