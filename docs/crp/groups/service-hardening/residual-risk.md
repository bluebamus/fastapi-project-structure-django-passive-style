# Residual Risk — service-hardening (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은 "새 결함"이
> 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | `/admin` 에 인증 백엔드가 없다 | MED | 영구 비목표(ADR-020, charter §2-4). 배포 환경은 `ADMIN_UNAUTHENTICATED_ACK` 확인과 기동 WARNING 으로 막는다 | 2026-10-12 | 관리 화면 인증이 별도 요청으로 들어오면 |
| R-002 | access 토큰은 만료 전에 즉시 폐기할 수 없다 | LOW | 비목표(charter §2-4). 만료 15분 + refresh 폐기로 대신한다 | 2026-10-12 | 즉시 차단이 필요한 운영 사고 요구가 생기면 |
| R-003 | 레이트 리밋은 고정 창이라 창 경계에서 순간적으로 한도의 2배까지 허용된다 | LOW | ADR-016 — 단순성 우선. 크리덴셜 스터핑의 규모를 막는 데는 충분하다 | 2026-10-12 | 슬라이딩 창 정밀도가 요구되면 |
| R-004 | `get_all` 의 보조 정렬 키 `id` 는 랜덤 UUID 라 동률 행의 순서는 결정적이지만 시간순은 아니다 | LOW | ADR-004 — 페이지 안정성이 목적이다. 시간 정밀도는 단계 D(마이크로초 저장)가 줄인다 | 2026-10-12 | 정렬 의미가 계약에 들어오면 |
| R-005 | `auth` → `user` 기능 의존이 `AppConfig` 에 선언되지 않았다(리뷰 R-17) | MED | REQ-001 의 단계 A~F2 범위 밖이다. 계층 검사는 이 의존을 문서화된 예외로 허용한다 | 2026-10-12 | 앱 간 의존 선언(`requires`) 요청이 들어오면 |
| R-006 | 슈퍼유저/일반 2단계 밖의 세분 권한이 없다 | LOW | 비목표(ADR-019, charter §2-4) | 2026-10-12 | 역할 기반 권한 요구가 생기면 |
| R-007 | 접속 로그 `ip_address` 는 `TRUSTED_PROXY_HOPS` 가 실제 프록시 홉 수와 같을 때만 정확하다. 크게 잡으면 위조된 XFF 값을, 작게 잡으면 프록시 주소를 기록한다. `forwarded_for`·`real_ip` 열은 헤더 원문이다 | LOW | ADR-005·ADR-023 — 홉 수는 배포 사실이라 코드가 알 수 없다. 기본값 0 은 위조를 막는 쪽이다 | 2026-10-12 | 신뢰 프록시를 CIDR 로 지정하는 요구가 생기면 |
| R-008 | SQLite 의 외래 키 위반은 부모 삭제(MySQL 1451 → 409)와 자식 참조 없음(1452 → 422)을 구분하지 못해 모두 422 로 답한다 | LOW | ADR-024 — SQLite 는 확장 코드 하나(`SQLITE_CONSTRAINT_FOREIGNKEY`)만 준다. 방언 정확성은 MySQL 이 기준이다(SQLite 는 단위 테스트용) | 2026-10-12 | SQLite 를 운영 DB 로 쓰는 요구가 생기면 |
| R-009 | ~~`scripts/review_gate.py` 의 pytest 단계가 커버리지 리포트의 "files skipped due to complete coverage" 문구를 테스트 skip 으로 읽어 로컬 게이트가 빨개진다(테스트 skip 은 0건). CI 의 skip 검사 정규식(`[1-9][0-9]* (skipped|xfailed|xpassed)`)은 "83 files skipped" 에도 걸리지만 CI 는 `skip-covered` 리포트를 쓰지 않아 해당 줄이 없다~~ **해소 (2026-10-12, F-026 Fixed)** | LOW | 단계 C 범위 밖(F-026). 실제 skip 여부는 pytest 요약 줄로 확인한다 | 2026-10-12 | 게이트 정비 요청이 들어오면 — 요약 줄(`=== … ===`)만 보도록 고친다 |
| R-010 | 시각 정책의 고정 오프셋 전제: ① 리포트 일자 버킷은 조회 시작일 0시의 오프셋 하나로 옮긴다 — DST 가 있는 `TIME_ZONE` 이면 전환일 전후 버킷이 한 시간 어긋난다. ② 리비전 `e5a7c2d9f310` 은 기존 값을 `+09:00` 벽시계로 보고 UTC 로 옮긴다 — 다른 `TIME_ZONE` 으로 운영하던 DB 는 오프셋을 바꾼 뒤 올려야 한다. ③ MySQL `CONVERT_TZ` 는 TIMESTAMP 범위(1970-01-01 ~ 3001-01-18 UTC) 밖의 값을 바꾸지 않는다 — 그 밖의 주문은 버킷이, 그 밖의 기존 값은 변환이 빠진다. ④ 기본 정렬 `created_at` 의 동률은 마이크로초 저장으로 줄었지만 같은 값의 일괄 삽입에서는 남는다(R-004 의 보조 키가 처리) | LOW | ADR-010·ADR-027 — 기본값 Asia/Seoul 은 1988년 이후 DST 가 없다. 시간대 이름 변환은 MySQL 시간대 테이블 적재가 운영 전제가 되므로 골격에 넣지 않는다(코드의 `ponytail:` 주석에 업그레이드 경로) | 2026-10-12 | DST 가 있는 시간대로 운영하거나 1970 년 이전·3001 년 이후 시각을 다뤄야 하면 |
| R-011 | 기능 `tasks.py` 내부의 import 오류는 API 기동이 아니라 Celery 워커가 include 를 import 할 때 드러난다(router·models·admin 은 기동 시 실패) | LOW | ADR-028 — 발견 단계에서 import 하면 `celery_app` 과 순환 import 다. 존재 판정만 `find_spec` 으로 한다. `tests/core/test_celery_app.py::test_including_the_task_modules_registers_the_tasks` 가 프로젝트의 include 를 실제로 import 해 CI 에서 잡는다 | 2026-10-12 | 워커 없이 배포되는 태스크 module 이 생기거나, 기동 시점 검증이 요구되면 |
