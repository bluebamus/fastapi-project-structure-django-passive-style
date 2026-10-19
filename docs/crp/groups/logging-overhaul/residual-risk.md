# Residual Risk — logging-overhaul (잔여 위험 등록부)

> **재기 금지 목록.** 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | uvicorn `--workers` ≥ 2·Celery prefork(`--concurrency` > 1)에서 파일 로그를 켜면 여러 프로세스가 같은 파일을 회전시킨다(회전 유실·중복) | MED | ADR-009 — 워커 수를 앱이 믿을 만하게 알 수 없어 감지하지 않는다. README "로깅" 절·운영 배포 체크리스트·ARCHITECTURE §5 에 "여러 워커 = 콘솔 + 수집기, 파일 로그 끔" 을 적었다 | 2026-10-19 | 프로세스 관리자가 워커 수를 넘겨주는 배포가 정해지면 기동 WARNING 을 넣는다 |
| R-002 | `uvicorn --reload`·`fastapi dev` 의 **감시 프로세스** 줄(`Will watch for changes`·`Uvicorn running on`·`Started reloader process`)은 uvicorn 기본 형식(stderr)이다 | LOW | 그 프로세스는 앱을 import 하지 않아 `configure_logging()` 이 돌지 않는다. 실측(run-log Round 1): 3줄. 요청을 받는 자식 프로세스는 프로젝트 형식이다. 개발 전용 경로다 | 2026-10-19 | 운영에서 reload 를 쓰거나 이 줄도 수집해야 하면 `--log-config` 용 JSON 을 `build_dictconfig()` 로 만들어 둔다 |
| R-003 | Celery 워커 `--loglevel`(기본 WARNING)이 워커 root 레벨이라 `LOG_APP_LEVELS` 의 더 낮은 레벨은 워커에서 그 아래로 내려가지 않는다 | LOW | 기존 동작(config-cleanup ADR-009) 유지 — CLI 인자가 명시한 값이다. README 키 표·ARCHITECTURE §5 에 적었다 | 2026-10-19 | 워커도 `.env` 만 따르게 하자는 결정이 나오면 수신자의 `setLevel` 을 뺀다 |
| R-004 | Celery 를 `celery` 명령이 아닌 방식(코드에서 `worker_main()`·다른 이름의 래퍼)으로 띄우면 `setup_logging` 시그널 전 줄이 웹 파일(`app.log`)로 간다 | LOW | `entry_process()` 는 진입 명령 이름으로 판단한다(ADR-003). 시그널 뒤 줄은 수신자가 `celery` 로 다시 구성한다. 이 저장소의 문서·CI 는 모두 `celery -A app.celery.app` 이다 | 2026-10-19 | 다른 진입 방식을 쓰기로 하면 그 진입점이 `configure_logging(process="celery")` 를 먼저 부른다 |
| R-005 | 가리기 원문 목록은 **기동 시점** 설정 값이다 — 실행 중 비밀값이 바뀌거나, 설정 밖에서 들어온 비밀(요청 본문 등)은 원문 일치 대상이 아니다 | LOW | ADR-007 — 형식 규칙(log-redaction-fixes ADR-001)이 그 밖을 맡는다. 비밀을 로그에 싣지 않는 것이 1차 방어다 | 2026-10-19 | 비밀값 회전을 무중단으로 하게 되면 회전 지점에서 `redactor.set_literals()` 를 다시 부른다 |
| R-006 | 예전 `{date}_app.log`·`{date}_error.log` 파일은 새 보관 규칙의 대상이 아니라 자동으로 지워지지 않는다 | LOW | 이름 형식이 달라 새 핸들러가 자기 파일로 알아보지 않는다(다른 파일을 지우지 않는 것이 안전). README 업그레이드 노트에 "손으로 정리" 를 적었다 | 2026-10-19 | — |

## 최종 상태 (2026-10-19, Round 1 · 그룹 CONVERGED)

수용 항목은 R-001~R-006 이다. R-001 은 문서 안내로, 나머지는 개발 전용 경로·기존 결정·형식 기반 가리기에 근거한 의도적 수용이다.
