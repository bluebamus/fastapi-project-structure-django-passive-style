# Residual Risk — orm-raw-repository (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로*
> 결정된 것이다. 다음 라운드에서 새 finding 으로 올리지 않는다 — 결함이 아니라 계약 선택이다.

| ID | 내용 | 수용 근거 | 상태 |
|---|---|---|---|
| R-001 | `/admin` 에 인증 백엔드가 없다 | 영구 비목표(확정). 대신 production/staging 은 `ADMIN_UNAUTHENTICATED_ACK` 미승인 시 기동 거부(F-007) | Accepted |
| R-002 | 개발 기본값 `ADMIN=true` 를 유지한다 | 2026-08-12 결정 — 받자마자 DB 를 들여다볼 수 있는 레퍼런스 구조 | Accepted |
| R-003 | Queue logging 을 도입하지 않는다 | ADR-003 — ADR-019(console + RotatingFileHandler) 유지. 후속 ADR 과제 | Accepted |
| R-004 | SQLite 단위 테스트는 MySQL 방언 정확성의 근거가 아니다 | ADR-004 — 방언은 `pytest -m mysql` 로만 승인 | Accepted |
| R-005 | `mysql_session_maker`(create_all) 실행 후 곧바로 `alembic upgrade head` 를 돌리면 1050 으로 깨진다 | 두 경로가 같은 스키마를 다른 방식으로 만든다. CI 는 alembic → pytest 순서로 고정했고, 수동 실행 시 `drop_all_tables_sync()` 로 초기화한다 | Accepted |
| R-007 | `user_access_logs` 의 인덱스 **나열 순서**가 Phase 2 전후로 다르다 | 인덱스 집합·컬럼·이름은 동일하고 순서만 다르다. `Table.indexes` 가 `set` 이라 생성 순번에 따라 emit 순서가 바뀐다. MySQL 질의 계획에 영향이 없고 `alembic check` 도 이름으로 비교한다 — 컬럼 순서와 달리 실질 영향이 없어 고치지 않는다 | Accepted |
| R-008 | WSL 의 MySQL 테스트 컨테이너가 healthy 직후 1~2분 뒤 종료 코드 255 로 죽는 일이 반복된다 | 종료 로그가 남지 않고 OOM 도 아니다(여유 13Gi). 원인을 특정하지 못했다. 현재는 **컨테이너 기동 직후 짧은 창에서 명령을 끝내는** 방식으로 우회한다. Phase 5 는 MySQL 통합이 본체라 이 우회로는 부족하다 — **사용자 확인 필요** | Open |
| R-009 | Raw SQL 의 **MySQL 방언 정확성**은 아직 검증되지 않았다 | Phase 4 는 SQLite 로 Base 계약만 확인했다(ADR-004). 실제 SQL·집계는 Phase 5 의 `pytest -m mysql` 이 담당한다 | **해소** (Round 8 — 집계 타입·경계·DDL 실측) |
| R-010 | `text()` 보간 금지를 **전면 금지**로 잠갔다 | requirements RAW-REP-004 는 정렬 컬럼 같은 식별자를 allowlist 상수로 f-string 구성하는 것을 허용한다. 지금은 그런 호출부가 없으므로 가장 좁은 규칙을 택했다. 필요해지면 ADR 로 예외를 열고 검사기에 allowlist 판정을 넣는다 | Accepted |
| R-006 | 잡히지 않은 예외의 traceback 로그에 DB 예외 메시지(SQL·bind 값)가 남는다 | ADR-010 — traceback 을 끄면 운영 장애 추적 수단이 사라진다. 올바른 차단 지점은 출력이 아니라 예외 생성부이며 Phase 3 의 공통 안전 변환기가 담당한다. **Phase 3 까지 한시 수용**(ledger F-015 Open) | **해소** (Round 5, F-015 Fixed) |

## 검사하지 않은 것 (Round 10 기준 · 최종)

이 라운드가 그린이라는 것은 **계약으로 정한 검사들이 전부 통과했다**는 뜻이지, 결함이
없다는 뜻이 아니다. 아래는 이번에 **돌리지 않은** 범위다.

1. 부하·성능 — 커넥션 풀 고갈, 동시성 한계
2. 복제 실환경 — replica lag, failover 동작
3. Celery worker 실제 기동
4. ~~Scalar UI 실렌더링~~ — **해소**(2026-08-19). Playwright + Chromium 으로 실제 `/docs` 를
   연다(`tests/browser/`, `pytest -m browser`, 7건). 태그 9개 렌더링, Markdown 표가 실제
   `<table>` 로 그려지는지, 예제 DTO 의 예시(`SKU-1001`·`129000.00`)가 화면에 나타나는지를
   본다. 외부(`api.scalar.com`) 404 는 세지 않는다 — 통제할 수 없고 렌더링에 영향이 없다.
5. ~~CI workflow 의 실제 실행~~ — **해소**(2026-08-19). push 후 두 job 모두 success. 첫 실행에서 워크플로 결함 3건이 드러나 고쳤다(completion-report §8)
6. `docs/crp/groups/orm-raw-repository/baseline/openapi.json` 은 **저장만** 했다. 이것을
   깨뜨리면 실패하는 snapshot 테스트는 Phase 6 에서 붙인다 — 지금은 비교 기준일 뿐이다
7. Raw Base 의 **MySQL 실행** — `RowMapping` 컬럼 alias, `Decimal`/`date` 타입 매핑,
   `FOR UPDATE` 의 실제 잠금 동작은 SQLite 로 확인할 수 없다. Phase 5 범위다.
8. Raw 집계 쿼리의 **실행 계획**(`EXPLAIN`) — `ordered_at` 인덱스를 실제로 타는지는
   확인하지 않았다. 소량 데이터에서는 옵티마이저가 전체 스캔을 고르는 것이 정상이라,
   의미 있는 검증에는 데이터 규모가 필요하다.
9. **실제 replica 를 붙인 라우팅** — 이번 라운드의 writer/reader 는 둘 다 로컬 SQLite
   엔진이다. 어느 엔진이 처리했는지는 증명했지만, 복제 지연 자체는 재현하지 않았다.
10. 예제 API 의 **인증·인가** — `catalog`/`reports` 는 무인증 참조 예제다(NFR-011).
    실제 업무 기능으로 승격할 때 위협 모델을 다시 본다.
11. ~~`.gitattributes` 부재로 인한 줄바꿈 churn~~ — **해소**(2026-08-19).
    `* text=auto eol=lf` 로 고정하고 blob(5개)·작업트리(30개)를 LF 로 정규화했다.
    `.bat`/`.cmd` 는 CRLF 유지, 바이너리는 제외.

> 최종 정리는 `completion-report.md` §4~5 를 본다 — 실행하지 않은 검증 7항목과
> 수용한 잔여 위험을 한 곳에 모았다.
